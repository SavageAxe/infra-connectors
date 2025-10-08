"""Pydantic models for Git provider payloads."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict

__all__ = ["GitFileContent", "GitDirectoryEntry", "GitChangedFile"]


class GitFileContent(BaseModel):
    """Metadata and base64 encoded content for a Git file."""

    model_config = ConfigDict(extra="allow")

    type: Optional[str] = None
    encoding: Optional[str] = None
    size: Optional[int] = None
    name: Optional[str] = None
    path: Optional[str] = None
    content: Optional[str] = None
    sha: Optional[str] = None
    commit: Optional[Dict[str, Any]] = None


class GitDirectoryEntry(BaseModel):
    """Entry returned when listing repository paths."""

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    path: Optional[str] = None
    type: Optional[str] = None


class GitChangedFile(BaseModel):
    """Diff information for a single file."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    filename: Optional[str] = None
    status: Optional[str] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    changes: Optional[int] = None
    sha: Optional[str] = None
    previous_filename: Optional[str] = Field(default=None, alias="previous_filename")
