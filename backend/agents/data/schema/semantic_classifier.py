"""SemanticClassifier — LLM-backed disambiguation for ambiguous columns.

Real-time design:
    Only called for columns where TypeInferencer sets ``needs_llm=True``
    (i.e. free_text or unknown types). For a 20-column dataset, typically
    2-4 columns need LLM disambiguation. These are batched into a single
    Haiku call rather than one call per column to minimise latency.

    The classifier emits a ``schema:column_classified`` Socket.IO event for
    each resolved column so the frontend can update the schema table live as
    each ambiguous column is resolved.

Batching:
    ``classify_batch()`` builds a single JSON prompt listing all ambiguous
    columns, sends one Haiku request, and parses the JSON array response.
    At ~200ms per Haiku call this processes 10 ambiguous columns in the
    same time as one.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from backend.agents.data.schema.type_inferencer import TypeInference
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

VALID_SEMANTIC_TYPES = frozenset({
    "identifier", "currency", "percentage", "date", "datetime",
    "categorical", "free_text", "email", "phone",
    "numeric_measure", "numeric_count", "boolean", "unknown",
})

_SYSTEM = (
    "You are a data schema classifier. "
    "Return ONLY valid JSON. No explanation. No markdown."
)


class SemanticClassifier:
    """LLM-backed classifier for columns TypeInferencer marked needs_llm=True.

    Args:
        llm_client: Async LLM client (Claude Haiku for low latency).
                    When None, all ambiguous columns remain 'unknown'.
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    async def classify_batch(
        self,
        inferences: list[TypeInference],
        sio=None,
        dataset_id: str = "",
    ) -> dict[str, str]:
        """Classify all ambiguous columns in a single LLM call.

        Args:
            inferences: List of TypeInference objects where needs_llm=True.
            sio:        Socket.IO server for real-time ``schema:column_classified`` events.
            dataset_id: Dataset UUID for Socket.IO room targeting.

        Returns:
            Dict mapping column_name → resolved semantic_type string.
        """
        if not inferences or not self._llm:
            return {}

        prompt = self._build_batch_prompt(inferences)

        try:
            raw = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("schema"),
                max_tokens=800,
            )
            results = self._parse_batch_response(raw, inferences)
        except Exception as exc:
            logger.warning("semantic_classifier_batch_failed", error=str(exc))
            results = {inf.column_name: "unknown" for inf in inferences}

        # Emit real-time Socket.IO events for each resolved column
        if sio and dataset_id:
            for col_name, semantic_type in results.items():
                try:
                    await sio.emit(
                        "schema:column_classified",
                        {
                            "dataset_id":    dataset_id,
                            "column_name":   col_name,
                            "semantic_type": semantic_type,
                            "source":        "llm",
                        },
                        room=f"dataset:{dataset_id}",
                    )
                except Exception:
                    pass

        logger.info(
            "semantic_batch_classified",
            columns=len(results),
            resolved={k: v for k, v in results.items() if v != "unknown"},
        )
        return results

    async def classify_single(
        self,
        inference: TypeInference,
    ) -> str:
        """Classify one ambiguous column. Falls back to 'unknown' on failure."""
        if not self._llm:
            return "unknown"

        prompt = (
            f"Classify this dataset column's semantic type.\n\n"
            f"Column name: {inference.column_name}\n"
            f"Data type: {inference.data_type}\n"
            f"Sample values: {inference.sample_values[:8]}\n"
            f"Null rate: {inference.null_rate * 100:.1f}%\n"
            f"Unique values: {inference.unique_count}\n\n"
            f"Valid types: {', '.join(sorted(VALID_SEMANTIC_TYPES))}\n\n"
            "Return ONLY the type string, nothing else."
        )
        try:
            raw = await self._llm.complete(
                prompt=prompt,
                system="Return only the semantic type string.",
                model_id=get_model_id("schema"),
                max_tokens=20,
            )
            resolved = raw.strip().lower().replace('"', "").replace("'", "").split()[0]
            return resolved if resolved in VALID_SEMANTIC_TYPES else "unknown"
        except Exception as exc:
            logger.debug("semantic_single_failed", col=inference.column_name, error=str(exc))
            return "unknown"

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_batch_prompt(inferences: list[TypeInference]) -> str:
        cols_json = json.dumps([
            {
                "name":          inf.column_name,
                "data_type":     inf.data_type,
                "sample_values": inf.sample_values[:5],
                "null_rate_pct": round(inf.null_rate * 100, 1),
                "unique_count":  inf.unique_count,
            }
            for inf in inferences
        ], indent=2)

        return (
            f"Classify the semantic type of each dataset column.\n\n"
            f"COLUMNS:\n{cols_json}\n\n"
            f"VALID TYPES: {', '.join(sorted(VALID_SEMANTIC_TYPES))}\n\n"
            "Return ONLY a JSON array matching this format:\n"
            '[{"name": "col_name", "semantic_type": "type"}, ...]'
        )

    @staticmethod
    def _parse_batch_response(
        raw: str,
        inferences: list[TypeInference],
    ) -> dict[str, str]:
        """Parse the LLM batch response into a column → type dict."""
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(l for l in text.splitlines() if not l.startswith("```")).strip()

        # Build fallback using current (pre-LLM) types
        fallback = {inf.column_name: inf.semantic_type for inf in inferences}

        try:
            data = json.loads(text)
            if not isinstance(data, list):
                return fallback

            results = dict(fallback)
            for item in data:
                name  = item.get("name", "")
                stype = item.get("semantic_type", "unknown")
                if name in results and stype in VALID_SEMANTIC_TYPES:
                    results[name] = stype
            return results

        except (json.JSONDecodeError, AttributeError):
            logger.debug("semantic_batch_parse_failed", raw_preview=text[:200])
            return fallback
