"""Common Pydantic response models shared across routers."""
from __future__ import annotations
from pydantic import BaseModel
from typing import Any


class ErrorResponse(BaseModel):
    error:   str
    message: str
    details: Any = None


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items:  list[Any]
    total:  int
    limit:  int
    offset: int
