"""Low level client that communicates with the Git provider."""

from __future__ import annotations

import base64
from typing import Any, Dict, List

from horizon_fastapi_template.utils import BaseAPI
from ..errors import GitError
from .models import GitDirectoryEntry, GitFileContent

__all__ = ["GitAPI"]


def _safe_json(response) -> Dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {}


def _handle_response(response_json: Dict[str, Any], status_code: int) -> None:
    message = response_json.get("message")

    if status_code == 401:
        raise GitError(
            status_code=status_code,
            detail="Git token is invalid or revoked."
            + (f" Git message: {message}" if message else ""),
        )

    if status_code == 404:
        raise GitError(
            status_code=404,
            detail="Git path (repo or file) not found."
            + (f" Git message: {message}" if message else ""),
        )

    if status_code == 422:
        if isinstance(message, str) and "sha" in message:
            raise GitError(status_code=422, detail="Git path (repo or file) already exists.")
        raise GitError(
            status_code=422,
            detail="Invalid request."
            + (f" Git message: {message}" if message else ""),
        )

    if status_code >= 400:
        detail = f"Git status code: {status_code}."
        if message:
            detail += f" Git message: {message}"
        raise GitError(status_code=status_code, detail=detail)


class GitAPI:
    """Client wrapping the subset of the GitHub REST API used by the platform."""

    def __init__(self, base_url: str, token: str) -> None:
        headers = {"Authorization": f"Bearer {token}"}
        self.api = BaseAPI(base_url.rstrip("/"), headers=headers).client

    async def get_file(self, path: str) -> GitFileContent:
        response = await self.api.get(f"/contents/{path.lstrip('/')}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return GitFileContent.model_validate(response_json)

    async def delete_file(self, path: str, commit_message: str) -> None:
        data = await self.get_file(path)
        if not data.sha:
            raise GitError(status_code=404, detail=f"Missing SHA for {path}")

        payload = {
            "sha": data.sha,
            "message": commit_message,
            "branch": "main",
        }

        response = await self.api.delete(f"/contents/{path.lstrip('/')}", json=payload)
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)

    async def modify_file_content(self, path: str, commit_message: str, content: str) -> None:
        file = await self.get_file(path)
        if not file.sha:
            raise GitError(status_code=404, detail=f"Missing SHA for {path}")

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "sha": file.sha,
            "content": encoded_content,
            "message": commit_message,
        }

        response = await self.api.put(f"/contents/{path.lstrip('/')}", json=payload)
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)

    async def list_dir(self, path: str) -> List[GitDirectoryEntry]:
        response = await self.api.get(f"/contents/{path.lstrip('/')}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        if not isinstance(response_json, list):
            return []
        return [GitDirectoryEntry.model_validate(item) for item in response_json]

    async def create_new_file(self, path: str, commit_message: str, content: str) -> None:
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "content": encoded_content,
            "message": commit_message,
        }

        response = await self.api.put(f"/contents/{path.lstrip('/')}", json=payload)
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)

    async def commits_per_path(self, path: str, since: str, until: str) -> List[Dict[str, Any]]:
        params = {"path": path, "since": since, "until": until}

        response = await self.api.get("/commits", params=params)
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return response_json if isinstance(response_json, list) else []

    async def compare_commits(self, base: str, head: str) -> Dict[str, Any]:
        path = f"/compare/{base}...{head}"

        response = await self.api.get(path)
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return response_json

    async def get_last_commit(self) -> Dict[str, Any]:
        response = await self.api.get("/commits/main")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return response_json

    async def get_commit(self, sha: str) -> Dict[str, Any]:
        response = await self.api.get(f"/commits/{sha}")
        response_json = _safe_json(response)
        _handle_response(response_json, response.status_code)
        return response_json
