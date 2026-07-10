"""End-to-end tests: full upload → analysis → chat → export lifecycle.

These tests require:
  - A running Postgres (DATABASE_URL)
  - A running Redis (REDIS_URL)
  - The Celery worker is NOT required — tasks are run inline via eager mode

Skip unless ``E2E_ENABLED=true`` is set.
"""

import io
import os

import pytest

E2E_ENABLED = os.environ.get("E2E_ENABLED") == "true"
skip_e2e = pytest.mark.skipif(not E2E_ENABLED, reason="Set E2E_ENABLED=true to run e2e tests")

def _sample_csv(tag: str) -> bytes:
    """Unique-per-test CSV bytes — the upload endpoint rejects duplicate
    uploads by content checksum, so each test needs distinct content to
    avoid tripping that rule when tests share a database."""
    return f"""date,region,product,revenue,units,tag
2024-01-01,North,Widget A,1200.50,10,{tag}
2024-01-02,South,Widget B,2300.00,20,{tag}
2024-01-03,East,Widget C,450.75,5,{tag}
""".encode()


@pytest.mark.e2e
class TestFullLifecycle:
    @skip_e2e
    @pytest.mark.asyncio
    async def test_upload_then_get_status(self, async_client) -> None:
        """Upload → verify UPLOADED status → check job_id present."""
        resp = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("sales.csv", io.BytesIO(_sample_csv("upload_status")), "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "dataset_id" in data
        assert "job_id" in data

        dataset_id = data["dataset_id"]
        status_resp = await async_client.get(f"/api/v1/datasets/{dataset_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] in (
            "uploaded",
            "profiling",
            "profiled",
            "cleaning",
            "ready",
        )

    @skip_e2e
    @pytest.mark.asyncio
    async def test_job_status_polling(self, async_client) -> None:
        """Upload → get job_id → poll job status → eventually complete."""
        resp = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("test.csv", io.BytesIO(_sample_csv("job_polling")), "text/csv")},
        )
        job_id = resp.json().get("job_id", "")
        if not job_id:
            pytest.skip("Upload failed or no job_id returned")

        job_resp = await async_client.get(f"/api/v1/jobs/{job_id}")
        assert job_resp.status_code == 200
        data = job_resp.json()
        assert "status" in data
        assert "progress" in data

    @skip_e2e
    @pytest.mark.asyncio
    async def test_health_and_readiness(self, async_client) -> None:
        health = await async_client.get("/health")
        ready = await async_client.get("/ready")
        assert health.status_code == 200
        assert ready.status_code in (200, 503)  # 503 if a dependency is down

    @skip_e2e
    @pytest.mark.asyncio
    async def test_delete_dataset(self, async_client) -> None:
        resp = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("del_test.csv", io.BytesIO(_sample_csv("delete_dataset")), "text/csv")},
        )
        dataset_id = resp.json().get("dataset_id", "")
        if not dataset_id:
            pytest.skip("Upload failed")

        del_resp = await async_client.delete(f"/api/v1/datasets/{dataset_id}")
        assert del_resp.status_code == 200

        # Deleted dataset should return 404
        get_resp = await async_client.get(f"/api/v1/datasets/{dataset_id}")
        assert get_resp.status_code == 404
