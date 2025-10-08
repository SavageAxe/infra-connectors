"""Low level client for interacting with HashiCorp Vault."""

from __future__ import annotations

from typing import Any, Mapping, Union

from pydantic import BaseModel

from horizon_fastapi_template.utils import BaseAPI
from ..errors import VaultError
from .models import VaultSecretPayload, VaultSecretResponse

__all__ = ["VaultAPI"]


def _safe_json(response) -> Mapping[str, Any]:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _handle_response(response_json: Mapping[str, Any], status_code: int) -> None:
    if status_code // 100 != 2:
        errors = response_json.get("errors")
        detail = f"Vault message: {errors}" if errors else "Vault request failed"
        raise VaultError(status_code=status_code, detail=detail)


def _generate_secret_path(path: str) -> str:
    parts = path.lstrip("/").split("/")
    return f"{parts[0]}/data/{'/'.join(parts[1:])}" if len(parts) > 1 else f"{parts[0]}/data"


def _generate_metadata_path(path: str) -> str:
    parts = path.lstrip("/").split("/")
    return f"{parts[0]}/metadata/{'/'.join(parts[1:])}" if len(parts) > 1 else f"{parts[0]}/metadata"


class VaultAPI:
    def __init__(self, base_url: str, token: str) -> None:
        headers = {"X-Vault-Token": token, "Content-Type": "application/json"}
        self.api = BaseAPI(base_url.rstrip("/"), headers=headers).client

    async def read_secret(self, path: str) -> VaultSecretResponse:
        secret_path = _generate_secret_path(path)
        response = await self.api.get(f"/v1/{secret_path}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return VaultSecretResponse.model_validate(response_json)

    async def write_secret(
        self,
        path: str,
        data: Union[VaultSecretPayload, Mapping[str, Any], BaseModel],
    ) -> None:
        secret_path = _generate_secret_path(path)
        if isinstance(data, VaultSecretPayload):
            payload = data
        elif isinstance(data, BaseModel):
            payload = VaultSecretPayload(data=data.model_dump(exclude_none=True))
        else:
            payload = VaultSecretPayload(data=dict(data))
        response = await self.api.post(f"/v1/{secret_path}", json=payload.model_dump(exclude_none=True))
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)

    async def delete_secret(self, path: str) -> None:
        metadata_path = _generate_metadata_path(path)
        response = await self.api.delete(f"/v1/{metadata_path}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
