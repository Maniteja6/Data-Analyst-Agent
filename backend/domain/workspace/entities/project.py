"""Project entity — a named workspace grouping related datasets and conversations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.shared.entity import Entity
from backend.domain.workspace.exceptions import ProjectDatasetLimitError

MAX_DATASETS_PER_PROJECT = 50


@dataclass
class Project(Entity):
    """A named workspace project that groups related datasets and conversations.

    Projects are the top-level organisational unit in DataPilot. A single
    team or use-case (e.g. "Q4 Sales Analysis") can own multiple datasets
    and share the context between conversations.

    Currently a lightweight grouping entity — future versions will add:
    - Multi-user collaboration (project members)
    - Shared memory across conversations
    - Project-level KPI dashboards

    Attributes:
        name:            Display name shown in the sidebar.
        description:     Optional one-sentence description.
        owner_id:        User or org ID that owns the project.
        dataset_ids:     Ordered list of dataset UUIDs belonging to this project.
        conversation_ids: Ordered list of conversation UUIDs in this project.
        is_archived:     True when the project is hidden from the active list.
        created_at:      UTC creation timestamp.
        updated_at:      UTC last-modified timestamp.
    """

    name:             str
    description:      str            = ""
    owner_id:         str | None     = None
    dataset_ids:      list[str]      = field(default_factory=list)
    conversation_ids: list[str]      = field(default_factory=list)
    is_archived:      bool           = False
    created_at:       datetime | None = None
    updated_at:       datetime | None = None

    # ── Domain methods ────────────────────────────────────────────────────

    def add_dataset(self, dataset_id: str) -> None:
        """Add a dataset to the project.

        Raises:
            ProjectDatasetLimitError: When ``MAX_DATASETS_PER_PROJECT`` is reached.
        """
        if len(self.dataset_ids) >= MAX_DATASETS_PER_PROJECT:
            raise ProjectDatasetLimitError(self.id, MAX_DATASETS_PER_PROJECT)
        if dataset_id not in self.dataset_ids:
            self.dataset_ids.append(dataset_id)
            self.updated_at = datetime.now(timezone.utc)

    def remove_dataset(self, dataset_id: str) -> None:
        """Remove a dataset from the project (does not delete the dataset)."""
        if dataset_id in self.dataset_ids:
            self.dataset_ids.remove(dataset_id)
            self.updated_at = datetime.now(timezone.utc)

    def add_conversation(self, conversation_id: str) -> None:
        if conversation_id not in self.conversation_ids:
            self.conversation_ids.append(conversation_id)
            self.updated_at = datetime.now(timezone.utc)

    def remove_conversation(self, conversation_id: str) -> None:
        if conversation_id in self.conversation_ids:
            self.conversation_ids.remove(conversation_id)
            self.updated_at = datetime.now(timezone.utc)

    def archive(self) -> None:
        """Soft-archive the project — hides it from the active list."""
        self.is_archived = True
        self.updated_at  = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore an archived project to the active list."""
        self.is_archived = False
        self.updated_at  = datetime.now(timezone.utc)

    def rename(self, name: str) -> None:
        if not name.strip():
            raise ValueError("Project name must not be blank")
        self.name       = name.strip()[:200]
        self.updated_at = datetime.now(timezone.utc)

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def dataset_count(self) -> int:
        return len(self.dataset_ids)

    @property
    def conversation_count(self) -> int:
        return len(self.conversation_ids)

    @property
    def is_at_dataset_limit(self) -> bool:
        return len(self.dataset_ids) >= MAX_DATASETS_PER_PROJECT

    @property
    def is_empty(self) -> bool:
        return self.dataset_count == 0 and self.conversation_count == 0

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        name: str,
        owner_id: str | None = None,
        description: str = "",
    ) -> "Project":
        from backend.shared.utils.datetime_utils import utcnow
        from backend.shared.utils.uuid_factory import new_uuid
        now = utcnow()
        return cls(
            id=new_uuid(),
            name=name.strip()[:200],
            description=description,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "name":             self.name,
            "description":      self.description,
            "owner_id":         self.owner_id,
            "dataset_count":    self.dataset_count,
            "conversation_count": self.conversation_count,
            "is_archived":      self.is_archived,
            "is_empty":         self.is_empty,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "updated_at":       self.updated_at.isoformat() if self.updated_at else None,
        }
