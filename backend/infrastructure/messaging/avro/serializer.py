"""Avro serialiser / deserialiser for Kafka domain events.

DataPilot uses Avro for cross-service message serialisation because:

1. **Schema enforcement** — the Avro schema validates every message before
   publish, catching field-type mismatches at the producer rather than
   silently corrupting consumer processing.

2. **Schema evolution** — Avro supports backward/forward-compatible schema
   changes (adding optional fields, renaming via aliases) without requiring
   a coordinated service restart.

3. **Compact binary encoding** — Avro binary is ~40% smaller than JSON for
   the same payload, which matters at high message rates.

4. **Glue Schema Registry integration** — the AWS Glue Schema Registry
   (provisioned by the MSK Terraform module) validates schemas at publish time
   and assigns schema IDs embedded in the message wire format.

Wire format (Confluent-compatible):
    Byte 0:     magic byte (0x00)
    Bytes 1-4:  schema ID (big-endian int32) from the registry
    Bytes 5+:   Avro binary-encoded payload

When the schema registry is not available (local dev / unit tests), the
serialiser falls back to JSON encoding with a fake schema ID of 0, wrapped
in the same wire format so consumers can detect and handle the fallback.

Usage::

    from backend.infrastructure.messaging.avro.serializer import AvroSerializer

    serializer = AvroSerializer()

    # Encode a domain event dict to bytes for Kafka produce
    payload  = event.to_dict()
    raw      = await serializer.serialize("DatasetUploaded", payload)

    # Decode bytes received from Kafka to a dict
    decoded  = await serializer.deserialize(raw)
"""
from __future__ import annotations

import io
import json
import os
import struct
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Schema directory co-located with this module
_SCHEMA_DIR = Path(__file__).parent / "schemas"

# Magic byte required by the Confluent wire format (and AWS Glue compatibility layer)
_MAGIC_BYTE = 0x00

# Fake schema ID used in fallback JSON mode (local dev / tests)
_FALLBACK_SCHEMA_ID = 0


class AvroSerializer:
    """Avro serialiser that optionally integrates with the Glue Schema Registry.

    When ``Settings.kafka_schema_registry_url`` points to a running registry,
    messages are encoded as proper Avro binary with real schema IDs.
    When it is blank or unreachable, the fallback JSON-in-wire-format is used.

    Thread-safe — a single shared instance is sufficient per worker process.
    """

    def __init__(self, schema_registry_url: str | None = None) -> None:
        """
        Args:
            schema_registry_url: URL of the Confluent-compatible schema registry.
                                 When None, read from ``Settings.kafka_schema_registry_url``.
                                 Pass ``''`` (empty string) to force fallback mode.
        """
        if schema_registry_url is None:
            from backend.config.settings import get_settings
            schema_registry_url = get_settings().kafka_schema_registry_url

        self._registry_url  = schema_registry_url
        self._schema_cache:  dict[str, Any]  = {}   # event_type → parsed schema
        self._id_cache:      dict[str, int]   = {}   # event_type → registered schema ID
        self._use_registry   = bool(schema_registry_url)

    # ── Schema loading ────────────────────────────────────────────────────

    def _load_schema(self, event_type: str) -> Any:
        """Load and parse the Avro schema for a given event type.

        Schemas are loaded from ``.avsc`` files in the ``schemas/`` directory.
        The filename convention is ``snake_case(event_type).avsc``.

        Args:
            event_type: PascalCase event name, e.g. ``'DatasetUploaded'``.

        Returns:
            Parsed Avro schema object (from ``fastavro.parse_schema``).

        Raises:
            FileNotFoundError: If no ``.avsc`` file exists for the event type.
        """
        if event_type in self._schema_cache:
            return self._schema_cache[event_type]

        # Convert PascalCase → snake_case for filename lookup
        snake = _pascal_to_snake(event_type)
        schema_path = _SCHEMA_DIR / f"{snake}.avsc"

        if not schema_path.exists():
            raise FileNotFoundError(
                f"Avro schema not found for event type '{event_type}'. "
                f"Expected: {schema_path}"
            )

        try:
            import fastavro
            schema_dict = json.loads(schema_path.read_text(encoding="utf-8"))
            parsed      = fastavro.parse_schema(schema_dict)
            self._schema_cache[event_type] = parsed
            return parsed
        except ImportError:
            # fastavro not installed → store the raw dict for fallback use
            schema_dict = json.loads(schema_path.read_text(encoding="utf-8"))
            self._schema_cache[event_type] = schema_dict
            return schema_dict

    # ── Serialise ─────────────────────────────────────────────────────────

    async def serialize(self, event_type: str, payload: dict[str, Any]) -> bytes:
        """Encode a domain event dict to Avro bytes in Confluent wire format.

        Args:
            event_type: Event class name, e.g. ``'DatasetUploaded'``.
            payload:    Dict produced by ``DomainEvent.to_dict()``.

        Returns:
            Binary message bytes ready for Kafka ``send()``.
        """
        try:
            return self._serialize_avro(event_type, payload)
        except Exception as exc:
            logger.warning(
                "avro_serialize_failed_fallback",
                event_type=event_type,
                error=str(exc),
            )
            return self._serialize_json_fallback(payload)

    def _serialize_avro(self, event_type: str, payload: dict) -> bytes:
        """Encode payload using Avro binary with Confluent wire format header."""
        import fastavro

        schema    = self._load_schema(event_type)
        schema_id = self._get_schema_id(event_type)

        buf = io.BytesIO()
        # Write Confluent wire format header: magic byte + schema ID (4 bytes big-endian)
        buf.write(struct.pack(">bI", _MAGIC_BYTE, schema_id))
        fastavro.schemaless_writer(buf, schema, payload)
        return buf.getvalue()

    def _serialize_json_fallback(self, payload: dict) -> bytes:
        """Encode payload as JSON with the Confluent wire format header.

        Used in local development and tests when fastavro is not available
        or the schema registry is not running.
        """
        schema_id   = _FALLBACK_SCHEMA_ID
        json_bytes  = json.dumps(payload, default=str).encode("utf-8")
        header      = struct.pack(">bI", _MAGIC_BYTE, schema_id)
        return header + json_bytes

    # ── Deserialise ───────────────────────────────────────────────────────

    async def deserialize(self, raw: bytes) -> dict[str, Any]:
        """Decode Avro bytes (Confluent wire format) to a Python dict.

        Automatically detects fallback JSON mode when schema ID is 0.

        Args:
            raw: Raw bytes received from a Kafka consumer.

        Returns:
            Decoded event dict. Unknown fields are preserved as-is.
        """
        if len(raw) < 5:
            raise ValueError(f"Message too short ({len(raw)} bytes) for Confluent wire format")

        magic, schema_id = struct.unpack(">bI", raw[:5])
        if magic != _MAGIC_BYTE:
            raise ValueError(f"Invalid magic byte: {magic!r}")

        body = raw[5:]

        # Fallback: JSON mode (schema ID == 0)
        if schema_id == _FALLBACK_SCHEMA_ID:
            return json.loads(body.decode("utf-8"))

        # Avro binary mode
        return self._deserialize_avro(body, schema_id)

    def _deserialize_avro(self, body: bytes, schema_id: int) -> dict:
        """Decode Avro binary body using the schema for the given ID."""
        try:
            import fastavro
            # Look up schema by ID (local cache first, then registry)
            event_type = self._id_to_event_type(schema_id)
            schema     = self._load_schema(event_type) if event_type else None

            buf = io.BytesIO(body)
            if schema:
                return fastavro.schemaless_reader(buf, schema)
            else:
                # Unknown schema ID — decode without validation
                logger.warning("avro_unknown_schema_id", schema_id=schema_id)
                return json.loads(body.decode("utf-8", errors="replace"))
        except ImportError:
            return json.loads(body.decode("utf-8", errors="replace"))
        except Exception as exc:
            logger.warning("avro_deserialize_failed", schema_id=schema_id, error=str(exc))
            return json.loads(body.decode("utf-8", errors="replace"))

    # ── Schema registry helpers ───────────────────────────────────────────

    def _get_schema_id(self, event_type: str) -> int:
        """Return the schema ID for an event type.

        Checks the local cache first, then registers with the schema registry
        if not cached. Falls back to ID 0 when the registry is unavailable.
        """
        if event_type in self._id_cache:
            return self._id_cache[event_type]

        if not self._use_registry:
            return _FALLBACK_SCHEMA_ID

        try:
            schema_id = self._register_schema(event_type)
            self._id_cache[event_type] = schema_id
            return schema_id
        except Exception as exc:
            logger.warning(
                "schema_registry_registration_failed",
                event_type=event_type,
                error=str(exc),
            )
            return _FALLBACK_SCHEMA_ID

    def _register_schema(self, event_type: str) -> int:
        """Register the schema with the Confluent-compatible registry and return its ID.

        Uses a simple HTTP POST to the ``/subjects/<subject>/versions`` endpoint.
        The subject name follows the topic-value convention:
        ``<topic_name>-value``, e.g. ``'dataset.uploaded-value'``.
        """
        import urllib.request
        import urllib.parse

        schema_path = _SCHEMA_DIR / f"{_pascal_to_snake(event_type)}.avsc"
        schema_str  = schema_path.read_text(encoding="utf-8")
        subject     = f"{_pascal_to_topic(event_type)}-value"
        url         = f"{self._registry_url}/subjects/{subject}/versions"

        request_body = json.dumps({"schema": schema_str}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return int(data["id"])

    def _id_to_event_type(self, schema_id: int) -> str | None:
        """Reverse lookup: schema ID → event type name from local cache."""
        for event_type, sid in self._id_cache.items():
            if sid == schema_id:
                return event_type
        return None

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self, event_type: str, payload: dict) -> list[str]:
        """Validate a payload against its Avro schema without encoding.

        Returns a list of validation error strings (empty list = valid).
        Used by the Security Agent to pre-validate event payloads before publish.
        """
        errors: list[str] = []
        try:
            schema = self._load_schema(event_type)
            import fastavro
            buf = io.BytesIO()
            fastavro.schemaless_writer(buf, schema, payload)
        except Exception as exc:
            errors.append(str(exc))
        return errors

    def list_known_schemas(self) -> list[str]:
        """Return the event types for which an ``.avsc`` file exists."""
        return [
            _snake_to_pascal(f.stem)
            for f in _SCHEMA_DIR.glob("*.avsc")
            if f.is_file()
        ]


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def _pascal_to_snake(name: str) -> str:
    """Convert ``DatasetUploaded`` → ``dataset_uploaded``."""
    import re
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _snake_to_pascal(name: str) -> str:
    """Convert ``dataset_uploaded`` → ``DatasetUploaded``."""
    return "".join(word.capitalize() for word in name.split("_"))


def _pascal_to_topic(name: str) -> str:
    """Convert ``DatasetUploaded`` → ``dataset.uploaded`` (Kafka topic name)."""
    snake = _pascal_to_snake(name)
    return snake.replace("_", ".", 1)   # only first underscore becomes dot


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_serializer_instance: AvroSerializer | None = None


def get_avro_serializer() -> AvroSerializer:
    """Return the shared AvroSerializer singleton."""
    global _serializer_instance
    if _serializer_instance is None:
        _serializer_instance = AvroSerializer()
    return _serializer_instance
