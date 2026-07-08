"""RunAnalysisUseCase — triggers or re-triggers the analysis pipeline for a dataset."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.application.commands.run_analysis_command import RunAnalysisCommand
from backend.domain.dataset.exceptions import DatasetNotFoundError
from backend.shared.utils.uuid_factory import new_uuid

if TYPE_CHECKING:
    from backend.application.ports.job_port import IJobService
    from backend.domain.analytics.repositories.session_repository import SessionRepository
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository

logger = structlog.get_logger(__name__)


class RunAnalysisUseCase:
    """Validates the dataset state and enqueues the analytics pipeline.

    Used for:
    - Manual re-analysis after the user edits the schema
    - Retry after a pipeline failure
    - Admin-triggered bulk re-analysis

    Guards:
    - Dataset must exist and not be soft-deleted
    - If dataset is READY and force_rerun=False, returns the existing session
    - Creates a new AnalysisSession aggregate for each run
    """

    def __init__(
        self,
        dataset_repo: DatasetRepository,
        session_repo: SessionRepository,
        job_service: IJobService,
    ) -> None:
        self._dataset_repo = dataset_repo
        self._session_repo = session_repo
        self._job_service = job_service

    async def execute(self, cmd: RunAnalysisCommand) -> dict:
        dataset = await self._dataset_repo.get_by_id(cmd.dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(cmd.dataset_id)

        if dataset.is_ready and not cmd.force_rerun:
            # Return the latest existing session rather than re-running
            session = await self._session_repo.get_latest_by_dataset_id(cmd.dataset_id)
            return {
                "dataset_id": cmd.dataset_id,
                "session_id": session.id if session else None,
                "status": "already_complete",
            }

        # Create a new analysis session
        from backend.domain.analytics.entities.analysis_session import AnalysisSession

        session = AnalysisSession.create(
            session_id=new_uuid(),
            dataset_id=cmd.dataset_id,
            correlation_id=cmd.correlation_id,
        )
        await self._session_repo.save(session)

        job_id = self._job_service.enqueue_analysis(
            dataset_id=cmd.dataset_id,
            storage_key=dataset.storage_key,
            correlation_id=cmd.correlation_id,
        )
        logger.info("analysis_enqueued", dataset_id=cmd.dataset_id, job_id=job_id)
        return {"dataset_id": cmd.dataset_id, "session_id": session.id, "job_id": job_id}
