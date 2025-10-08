"""Low level client that wraps the Argo CD REST API."""

from __future__ import annotations

import json
from typing import Any, Mapping, Union

from pydantic import BaseModel

from horizon_fastapi_template.utils import BaseAPI
from ..errors import ArgoCDError
from .models import ArgoApplication

__all__ = ["ArgoCDAPI"]


def _parse_response_message(response_json: Mapping[str, Any]) -> str | None:
    message = response_json.get("message")
    if isinstance(message, Mapping):
        return json.dumps(message)
    if isinstance(message, str):
        return message
    return None


def _handle_response(response_json: Mapping[str, Any], status_code: int) -> None:
    message = _parse_response_message(response_json)

    if status_code == 307:
        raise ArgoCDError(
            status_code=status_code,
            detail="ArgoCD endpoint is redirecting. "
            + (f"ArgoCD message: {message}" if message else ""),
        )

    if status_code == 403:
        raise ArgoCDError(
            status_code=status_code,
            detail="Don't have permission to access this resource, "
            "or this resource doesn't exist."
            + (f" ArgoCD message: {message}" if message else ""),
        )

    if status_code >= 400:
        detail = f"ArgoCD status code: {status_code}."
        if message:
            detail += f" ArgoCD message: {message}"
        raise ArgoCDError(status_code=status_code, detail=detail)


class ArgoCDAPI:
    """Low level client responsible for calling Argo CD endpoints."""

    def __init__(self, base_url: str, api_key: str) -> None:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.api = BaseAPI(base_url.rstrip("/"), headers=headers).client

    async def sync_app(self, app_name: str) -> None:
        uri = f"/api/v1/applications/{app_name}/sync"

        response = await self.api.post(endpoint=uri, data={})
        response_json = response.json()
        _handle_response(response_json, response.status_code)

    async def get_app(self, app_name: str) -> ArgoApplication:
        uri = f"/api/v1/applications/{app_name}"

        response = await self.api.get(endpoint=uri)
        response_json = response.json()
        _handle_response(response_json, response.status_code)
        return ArgoApplication.model_validate(response_json)

    async def patch_app(
        self,
        app_definition: Union[ArgoApplication, Mapping[str, Any], BaseModel],
        app_name: str,
        namespace: str,
        project: str,
    ) -> None:
        uri = f"/api/v1/applications/{app_name}"

        if isinstance(app_definition, BaseModel):
            patch_payload = app_definition.model_dump(exclude_none=True)
        else:
            patch_payload = dict(app_definition)

        data = {
            "appNamespace": namespace,
            "name": app_name,
            "patch": json.dumps(patch_payload),
            "patchType": "merge",
            "project": project,
        }

        response = await self.api.patch(endpoint=uri, data=json.dumps(data))
        response_json = response.json()
        _handle_response(response_json, response.status_code)
