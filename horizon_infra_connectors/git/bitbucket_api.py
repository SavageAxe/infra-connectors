"""Hybrid Bitbucket GitAPI client: structured errors, GitHub-like shapes, httpx multipart, and a commit context."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from horizon_fastapi_template.utils import BaseAPI
from ..errors import GitError
from .models import GitChangedFile, GitDirectoryEntry, GitFileContent

__all__ = ["GitAPI"]


def _safe_json(response) -> Dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {}


def _bb_message(data: Dict[str, Any]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    if "error" in data and isinstance(data["error"], dict):
        return data["error"].get("message")
    return data.get("message")


def _handle_response(response_json: Dict[str, Any], status_code: int) -> None:
    message = _bb_message(response_json)

    if status_code == 401:
        raise GitError(401, f"Bitbucket token invalid. {message or ''}")
    if status_code == 403:
        raise GitError(403, f"Permission denied. {message or ''}")
    if status_code == 404:
        raise GitError(404, f"Path, repo, or ref not found. {message or ''}")
    if status_code >= 400:
        raise GitError(status_code, f"Bitbucket error: {message or status_code}")


def _blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("utf-8")
    return hashlib.sha1(header + content).hexdigest()


def _src_endpoint(workspace: str, repo_slug: str, ref: str, path: str) -> str:
    clean = path.lstrip("/")
    if clean:
        return f"/repositories/{workspace}/{repo_slug}/src/{ref}/{clean}"
    return f"/repositories/{workspace}/{repo_slug}/src/{ref}"


def _parse_author(author: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    author_data = author if isinstance(author, dict) else {}
    raw = author_data.get("raw") or ""
    name = email = None
    if raw:
        match = re.match(r"^(?P<name>.*?)(?:<(?P<email>[^>]+)>)?$", raw)
        if match:
            name = (match.group("name") or "").strip() or None
            email = (match.group("email") or "").strip() or None
        else:
            name = raw.strip() or None
    user = author_data.get("user")
    if isinstance(user, dict):
        name = name or user.get("display_name") or user.get("nickname")
        email = email or user.get("email")
    return name, email


def _convert_commit(commit: Dict[str, Any]) -> Dict[str, Any]:
    sha = commit.get("hash")
    name, email = _parse_author(commit.get("author", {}))
    summary = commit.get("summary")
    message = summary.get("raw") if isinstance(summary, dict) else str(summary or "")
    parents = [
        {"sha": p["hash"]}
        for p in commit.get("parents", [])
        if isinstance(p, dict) and p.get("hash")
    ]
    html_url = commit.get("links", {}).get("html", {}).get("href")
    return {
        "sha": sha,
        "commit": {"author": {"name": name, "email": email, "date": commit.get("date")}, "message": message},
        "parents": parents,
        "html_url": html_url,
    }


def _convert_diffstat_entry(entry: Dict[str, Any]) -> GitChangedFile:
    if not isinstance(entry, dict):
        return GitChangedFile()
    old, new = entry.get("old", {}), entry.get("new", {})
    filename = new.get("path") or old.get("path")
    previous = old.get("path") if old.get("path") and new.get("path") and old["path"] != new["path"] else None
    return GitChangedFile(
        filename=filename,
        status=entry.get("status"),
        additions=entry.get("lines_added", 0),
        deletions=entry.get("lines_removed", 0),
        previous_filename=previous,
    )


class GitAPI:
    def __init__(self, base_url: str, username_or_email: str, token: str, workspace: str, repo_slug: str, default_ref: str = "main") -> None:
        headers = {
            "Authorization": "Basic " + base64.b64encode(f"{username_or_email}:{token}".encode()).decode(),
            "Accept": "application/json",
        }
        self.api = BaseAPI(base_url.rstrip("/"), headers=headers).client
        self.workspace, self.repo_slug, self._default_ref = workspace, repo_slug, default_ref

    async def get_file(self, path: str, ref: Optional[str] = None) -> GitFileContent:
        ref = ref or self._default_ref
        endpoint = _src_endpoint(self.workspace, self.repo_slug, ref, path)
        meta_response = await self.api.get(endpoint, params={"format": "meta"})
        meta_data = _safe_json(meta_response)
        _handle_response(meta_data, meta_response.status_code)
        raw_response = await self.api.get(endpoint, headers={"Accept": "application/octet-stream"})
        _handle_response(_safe_json(raw_response), raw_response.status_code)
        content_bytes = raw_response.content
        meta_path = meta_data.get("path") if isinstance(meta_data, dict) else None
        commit = meta_data.get("commit") if isinstance(meta_data, dict) else None
        return GitFileContent(
            type="file",
            encoding="base64",
            size=len(content_bytes),
            name=(meta_path or path).split("/")[-1],
            path=meta_path or path.lstrip("/"),
            content=base64.b64encode(content_bytes).decode(),
            sha=_blob_sha(content_bytes),
            commit=_convert_commit(commit or {}) if commit else None,
        )

    async def list_dir(self, path: str, ref: Optional[str] = None) -> List[GitDirectoryEntry]:
        ref = ref or self._default_ref
        response = await self.api.get(_src_endpoint(self.workspace, self.repo_slug, ref, path), params={"format": "meta"})
        data = _safe_json(response)
        _handle_response(data, response.status_code)
        entries: List[GitDirectoryEntry] = []
        for e in data.get("values", []):
            if not isinstance(e, dict) or not e.get("path"):
                continue
            entry_type = "dir" if e.get("type") == "commit_directory" else "file"
            entries.append(
                GitDirectoryEntry(
                    name=e["path"].split("/")[-1],
                    path=e["path"],
                    type=entry_type,
                )
            )
        return entries

    async def _commit_via_src(self, commit_message: str, *, files: Optional[Dict[str, bytes]], deleted: List[str], branch: Optional[str] = None) -> None:
        ref = branch or self._default_ref
        data: Dict[str, Any] = {"message": commit_message, "branch": ref}
        if deleted:
            data["files"] = [d.lstrip("/") for d in deleted]

        multipart_files = [
            (
                p.lstrip("/"),
                (
                    p.split("/")[-1],
                    c,
                    "application/octet-stream",
                ),
            )
            for p, c in (files or {}).items()
        ]

        response = await self.api.post(
            f"/repositories/{self.workspace}/{self.repo_slug}/src",
            data=data,
            files=multipart_files or None,
        )
        _handle_response(_safe_json(response), response.status_code)

    async def create_or_update_file(self, path: str, commit_message: str, content: Union[str, bytes], branch: Optional[str] = None) -> None:
        data_bytes = content.encode() if isinstance(content, str) else content
        await self._commit_via_src(commit_message, files={path: data_bytes}, deleted=[], branch=branch)

    async def delete_file(self, path: str, commit_message: str, branch: Optional[str] = None) -> None:
        await self._commit_via_src(commit_message, files=None, deleted=[path], branch=branch)

    class CommitContext:
        def __init__(self, api: "GitAPI", message: str = "Commit via context", branch: Optional[str] = None):
            self.api, self.message, self.branch = api, message, branch
            self.files, self.deleted = {}, []
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb):
            if exc_type is None:
                await self.api._commit_via_src(self.message, files=self.files or None, deleted=self.deleted, branch=self.branch)
        def add_or_edit_file(self, path: str, content: Union[str, bytes]):
            self.files[path] = content.encode() if isinstance(content, str) else content
        def delete_file(self, path: str):
            self.deleted.append(path)
        def add_directory(self, local_dir: Union[str, Path], repo_prefix: str = ""):
            base = Path(local_dir)
            if not base.is_dir():
                raise ValueError(f"{base} is not a directory")
            for p in base.rglob("*"):
                if p.is_file():
                    rel = str(p.relative_to(base))
                    repo_path = f"{repo_prefix}/{rel}".lstrip("/")
                    self.files[repo_path] = p.read_bytes()

    def commit_context(self, message: str = "Commit via context", branch: Optional[str] = None) -> "GitAPI.CommitContext":
        return self.CommitContext(self, message=message, branch=branch)
