"""Root test fixtures and configuration for the full test suite.

Provides:
  - ``async_client``     — async httpx test client against the FastAPI app
  - ``sample_df``        — a small polars DataFrame for unit tests
  - ``sample_csv_bytes`` — raw CSV bytes matching sample_df
  - ``mock_llm``         — MockLLMService with common canned responses
  - ``in_memory_cache``  — InMemoryCacheAdapter (no Redis needed)
  - ``local_storage``    — LocalStorageAdapter in a tmp directory
  - ``fake_dataset``     — a Dataset aggregate in UPLOADED status
  - ``fake_profile``     — a DataProfile populated from sample_df

Environment:
  All tests run with ``APP_ENV=test`` so get_settings() returns test defaults.
  Database tests use an in-memory SQLite engine (override DATABASE_URL).
  No real AWS, Kafka, or Qdrant connections are made in unit/integration tests.
"""

from __future__ import annotations

import io
import os
import uuid

import pytest
import pytest_asyncio

# ── Environment setup ─────────────────────────────────────────────────────
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_csv_bytes() -> bytes:
    """Raw CSV bytes for a tiny sales dataset used across all unit tests."""
    return b"""date,region,product,revenue,units,discount_pct
2024-01-01,North,Widget A,1200.50,10,0.05
2024-01-02,South,Widget B,2300.00,20,0.10
2024-01-03,North,Widget C,450.75,5,0.00
2024-01-04,East,Widget A,3100.00,25,0.15
2024-01-05,West,Widget B,800.25,8,0.05
2024-01-06,South,Widget C,-50.00,2,0.00
2024-01-07,North,Widget A,5200.00,40,0.20
2024-01-08,East,Widget B,1100.50,11,0.10
2024-01-09,West,Widget C,0.00,0,0.00
2024-01-10,North,Widget A,4300.75,35,0.12
"""


@pytest.fixture(scope="session")
def sample_df(sample_csv_bytes):
    """Small polars DataFrame for unit tests — avoids repeated CSV parsing."""
    try:
        import polars as pl

        return pl.read_csv(io.BytesIO(sample_csv_bytes))
    except ImportError:
        import pandas as pd

        return pd.read_csv(io.BytesIO(sample_csv_bytes))


@pytest.fixture(scope="session")
def sample_df_with_nulls(sample_csv_bytes):
    """DataFrame with injected null values for missing-value handler tests."""
    try:
        import polars as pl

        df = pl.read_csv(io.BytesIO(sample_csv_bytes))
        # Inject nulls: set revenue=null for rows 2,5,8
        return df.with_columns(
            pl.when(pl.arange(0, pl.len()) % 3 == 2)
            .then(None)
            .otherwise(pl.col("revenue"))
            .alias("revenue")
        )
    except ImportError:
        import pandas as pd

        df = pd.read_csv(io.BytesIO(sample_csv_bytes))
        df.loc[df.index % 3 == 2, "revenue"] = None
        return df


# ---------------------------------------------------------------------------
# Infrastructure stubs
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_cache():
    """InMemoryCacheAdapter — cleared between tests."""
    from backend.infrastructure.cache.in_memory_cache_adapter import InMemoryCacheAdapter

    cache = InMemoryCacheAdapter(default_ttl=3600)
    yield cache
    cache.clear()


@pytest.fixture
def local_storage(tmp_path):
    """LocalStorageAdapter backed by a pytest tmp_path directory."""
    from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter

    adapter = LocalStorageAdapter(base_path=str(tmp_path / "storage"))
    yield adapter
    adapter.clear()


@pytest.fixture
def mock_llm():
    """MockLLMService pre-loaded with standard canned responses."""
    from backend.infrastructure.llm.llm_port import MockLLMService

    llm = MockLLMService(default_response='{"result": "mock_response"}')
    llm.set_response("schema", '{"columns": [{"name": "revenue", "semantic_type": "currency"}]}')
    llm.set_response(
        "insight", '{"insights": [], "executive_summary": "Test summary.", "kpis": []}'
    )
    llm.set_response("SQL", "SELECT SUM(revenue) FROM df")
    llm.set_response(
        "intent", '{"intent": "statistical_question", "confidence": 0.95, "requires_sql": true}'
    )
    llm.set_response("critic", '{"approved": true, "issues": []}')
    yield llm
    llm.reset()


@pytest.fixture
def null_job_service():
    """NullJobAdapter — no Celery broker required."""
    from backend.infrastructure.job_queue.celery_job_adapter import NullJobAdapter

    return NullJobAdapter(fake_task_id=str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Domain entity fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_dataset_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def fake_dataset(fake_dataset_id):
    """Dataset aggregate in UPLOADED status."""
    from backend.domain.dataset.entities.dataset import Dataset

    ds = Dataset.create(
        id=fake_dataset_id,
        project_id=None,
        original_name="sample_sales.csv",
        storage_key=f"datasets/{fake_dataset_id}/sample_sales.csv",
        size_bytes=1024,
        mime_type="text/csv",
        checksum_sha256="abc123def456" * 4,
    )
    ds.pull_domain_events()  # consume the DatasetUploaded event
    return ds


@pytest.fixture
def fake_session_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def fake_profile(sample_df, fake_session_id, fake_dataset_id):
    """DataProfile produced from sample_df."""
    import asyncio

    from backend.analytics_engine.profiling.data_profiler import DataProfiler

    profiler = DataProfiler()
    profile = asyncio.get_event_loop().run_until_complete(
        profiler.profile(sample_df, session_id=fake_session_id, dataset_id=fake_dataset_id)
    )
    return profile


@pytest.fixture
def fake_conversation(fake_dataset_id):
    """Conversation aggregate with no messages."""
    from backend.domain.workspace.entities.conversation import Conversation

    conv = Conversation.create(
        conversation_id=str(uuid.uuid4()),
        dataset_id=fake_dataset_id,
        title="Test conversation",
    )
    conv.pull_domain_events()
    return conv


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client(in_memory_cache, local_storage, null_job_service):
    """Async httpx client wired to the FastAPI app with stubbed infrastructure."""
    import httpx

    # Patch the dependency factories before importing the app
    from backend.api import dependencies

    dependencies._cache_override = in_memory_cache
    dependencies._storage_override = local_storage
    dependencies._job_override = null_job_service

    from backend.api.main import app

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Pytest configuration
# ---------------------------------------------------------------------------


def pytest_configure(config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: fast unit tests with no I/O")
    config.addinivalue_line("markers", "integration: requires Postgres + Redis")
    config.addinivalue_line("markers", "e2e: full end-to-end with real services")
    config.addinivalue_line("markers", "slow: tests that take > 10 seconds")
    config.addinivalue_line("markers", "bedrock: requires real AWS Bedrock credentials")
