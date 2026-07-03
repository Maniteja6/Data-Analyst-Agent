"""GetConversationQuery — query DTO for retrieving a Conversation."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class GetConversationQuery:
    conversation_id: str
    include_messages: bool = True


@dataclass(frozen=True)
class ListConversationsQuery:
    dataset_id: str
    limit:      int  = 20
    offset:     int  = 0
