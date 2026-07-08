"""RunAnalysisCommand — triggers a new analysis pipeline run for an existing dataset."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunAnalysisCommand:
    """Triggers (or re-triggers) the full analytics + agent pipeline for a dataset.

    Attributes:
        dataset_id:     UUID of the target Dataset aggregate.
        force_rerun:    When True, re-run even if the dataset is already READY.
        correlation_id: Request-scoped tracing ID.
    """

    dataset_id: str
    force_rerun: bool = False
    correlation_id: str = ""
