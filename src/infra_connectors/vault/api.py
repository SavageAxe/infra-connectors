"""Low level client for interacting with HashiCorp Vault."""

from __future__ import annotations

from typing import Dict

from ..base import BaseAPI
from ..errors import VaultError

__all__ = ["VaultAPI"]


def _safe_json(response) -> Dict:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _handle_response(response_json: Dict, status_code: int) -> None:
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
        self.api = BaseAPI(base_url.rstrip("/"), headers=headers)

    async def read_secret(self, path: str) -> Dict:
        secret_path = _generate_secret_path(path)
        response = await self.api.get(f"/v1/{secret_path}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return response_json

    async def write_secret(self, path: str, data: Dict) -> None:
        secret_path = _generate_secret_path(path)
        response = await self.api.post(f"/v1/{secret_path}", json={"data": data})
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)

    async def delete_secret(self, path: str) -> None:
        metadata_path = _generate_metadata_path(path)
        response = await self.api.delete(f"/v1/{metadata_path}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
