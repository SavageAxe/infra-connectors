"""Typed models that represent Argo CD application payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field, ConfigDict

__all__ = [
    "ArgoSyncInfo",
    "ArgoHealthInfo",
    "ArgoOperationState",
    "ArgoHistoryEntry",
    "ArgoApplicationStatus",
    "ArgoHelmSource",
    "ArgoApplicationSource",
    "ArgoApplicationSpec",
    "ArgoApplication",
    "ArgoApplicationEvaluation",
]


class ArgoSyncInfo(BaseModel):
    """Subset of the sync section reported by Argo CD."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    revision: Optional[str] = None


class ArgoHealthInfo(BaseModel):
    """Simplified view of the health section."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None


class ArgoOperationState(BaseModel):
    """State of an Argo CD operation."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    phase: Optional[str] = None
    message: Optional[str] = None
    finished_at: Optional[str] = Field(default=None, alias="finishedAt")


class ArgoHistoryEntry(BaseModel):
    """Entry describing a historic deployment."""

    model_config = ConfigDict(extra="allow")

    revision: Optional[str] = None


class ArgoApplicationStatus(BaseModel):
    """Aggregated status information for an Argo CD application."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    sync: Optional[ArgoSyncInfo] = None
    reconciled_at: Optional[str] = Field(default=None, alias="reconciledAt")
    operation_state: Optional[ArgoOperationState] = Field(default=None, alias="operationState")
    history: List[ArgoHistoryEntry] = Field(default_factory=list)
    health: Optional[ArgoHealthInfo] = None

    @property
    def reconciledAt(self) -> Optional[str]:  # pragma: no cover - convenience alias
        return self.reconciled_at

    @property
    def operationState(self) -> Optional[ArgoOperationState]:  # pragma: no cover - convenience alias
        return self.operation_state


class ArgoHelmSource(BaseModel):
    """Helm configuration embedded in the application spec."""

    model_config = ConfigDict(extra="allow")

    values: Optional[str] = None


class ArgoApplicationSource(BaseModel):
    """Source configuration for the Argo CD application."""

    model_config = ConfigDict(extra="allow")

    helm: Optional[ArgoHelmSource] = None


class ArgoApplicationSpec(BaseModel):
    """Application spec section."""

    model_config = ConfigDict(extra="allow")

    source: Optional[ArgoApplicationSource] = None


class ArgoApplication(BaseModel):
    """Full Argo CD application payload as returned by the API."""

    model_config = ConfigDict(extra="allow")

    metadata: Optional[Dict[str, Any]] = None
    spec: Optional[ArgoApplicationSpec] = None
    status: Optional[ArgoApplicationStatus] = None


class ArgoApplicationEvaluation(BaseModel):
    """High-level evaluation of an Argo CD application state."""

    model_config = ConfigDict(extra="forbid")

    result: Literal["SUCCESS", "FAILED", "INPROGRESS"]
    message: str
