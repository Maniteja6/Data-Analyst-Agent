"""DatasetStatus value object — lifecycle states for the Dataset aggregate."""
from __future__ import annotations

from enum import Enum


class DatasetStatus(str, Enum):
    """Ordered lifecycle states of a Dataset aggregate.

    State machine (valid transitions only):
    ┌──────────┐   upload   ┌──────────┐  schema ok  ┌──────────┐
    │  (new)   │───────────▶│ UPLOADED │────────────▶│ PROFILING│
    └──────────┘            └──────────┘             └────┬─────┘
                                                          │ profiling done
                                                          ▼
                                                     ┌──────────┐
                                                     │ PROFILED │
                                                     └────┬─────┘
                                                          │ cleaning starts
                                                          ▼
                                                     ┌──────────┐  success  ┌───────┐
                                                     │ CLEANING │──────────▶│ READY │
                                                     └────┬─────┘           └───────┘
                                                          │ (any stage)
                                                          ▼
                                                      ┌────────┐
                                                      │ FAILED │
                                                      └────────┘

    The READY state is the only terminal success state — it signals to the
    frontend that the dataset is available for chat queries and insight viewing.
    FAILED is the only terminal failure state.
    """

    UPLOADED  = "uploaded"
    """File stored in S3; schema inference has not started yet."""

    PROFILING = "profiling"
    """DataProfiler is currently analysing the column statistics."""

    PROFILED  = "profiled"
    """Statistical profiling is complete; cleaning pipeline is next."""

    CLEANING  = "cleaning"
    """DataCleaner is removing duplicates, imputing nulls, coercing types."""

    READY     = "ready"
    """Dataset is fully processed and available for AI analysis and chat."""

    FAILED    = "failed"
    """Processing failed at some stage; error_message contains the reason."""

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_terminal(self) -> bool:
        """True for READY and FAILED — no further transitions are possible."""
        return self in (DatasetStatus.READY, DatasetStatus.FAILED)

    @property
    def is_processing(self) -> bool:
        """True while the pipeline is actively running (any non-terminal state)."""
        return not self.is_terminal

    @property
    def is_available(self) -> bool:
        """True only when the dataset is READY for queries and analysis."""
        return self == DatasetStatus.READY

    @property
    def display_label(self) -> str:
        """Human-readable label for the frontend status badge."""
        labels = {
            DatasetStatus.UPLOADED:  "Uploaded",
            DatasetStatus.PROFILING: "Analysing…",
            DatasetStatus.PROFILED:  "Profiled",
            DatasetStatus.CLEANING:  "Cleaning…",
            DatasetStatus.READY:     "Ready",
            DatasetStatus.FAILED:    "Failed",
        }
        return labels[self]

    @property
    def progress_pct(self) -> int:
        """Approximate pipeline completion percentage for the progress bar."""
        pct = {
            DatasetStatus.UPLOADED:  5,
            DatasetStatus.PROFILING: 25,
            DatasetStatus.PROFILED:  50,
            DatasetStatus.CLEANING:  75,
            DatasetStatus.READY:     100,
            DatasetStatus.FAILED:    0,
        }
        return pct[self]
