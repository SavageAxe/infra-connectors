"""Common error hierarchy used by the service clients."""

from __future__ import annotations

from fastapi import HTTPException
from typing import Optional


class ExternalServiceError(HTTPException):
    """Base exception raised when a remote system responds with an error."""

    def __init__(
            self,
            service_name: str,
            status_code: int,
            detail: Optional[str] = None,
    ) -> None:
        self.service_name = service_name
        self.status_code = status_code
        self.detail = detail
        super().__init__(status_code=status_code, detail=self.detail)


class ArgoCDError(ExternalServiceError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(service_name="ArgoCD", status_code=status_code, detail=detail)


class GitError(ExternalServiceError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(service_name="Git", status_code=status_code, detail=detail)


class VaultError(ExternalServiceError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(service_name="Vault", status_code=status_code, detail=detail)
