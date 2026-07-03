"""GetJobStatusQuery — query DTO for job status polling."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class GetJobStatusQuery:
    job_id: str


@dataclass
class JobStatusResult:
    job_id:    str
    status:    str       # pending | running | complete | failed
    progress:  int       # 0–100
    step:      str       # human-readable current step label
    dataset_id: str | None = None
    error:     str | None  = None
