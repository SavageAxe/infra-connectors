"""High level wrapper around the Git provider APIs."""

from __future__ import annotations

import base64
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from loguru import logger

from .api import GitAPI as GithubAPI
from .bitbucket_api import GitAPI as BitbucketAPI
from .models import GitChangedFile, GitDirectoryEntry, GitFileContent
from ..errors import GitError

__all__ = ["Git", "logger"]

ProviderLiteral = Union[str, None]


class Git:
    """Provider-agnostic helper that wraps the GitHub or Bitbucket clients."""

    def __init__(
        self,
        base_url: str,
        token: str,
        email: Optional[str] = None,
        workspace: Optional[str] = None,
        repo_slug: Optional[str] = None,
        default_ref: str = "main",
        *,
        provider: ProviderLiteral = None,
    ) -> None:
        provider_name = (provider or "bitbucket").lower()

        if provider_name == "github":
            logger.debug("Initialising Git service with GitHub provider: base_url={}.", base_url)
            self.api = GithubAPI(base_url, token)
        elif provider_name == "bitbucket":
            if not all([email, workspace, repo_slug]):
                raise ValueError("Bitbucket provider requires email, workspace, and repo_slug")
            logger.debug(
                "Initialising Git service with Bitbucket provider: base_url={}, workspace={}, repo_slug={}.",
                base_url,
                workspace,
                repo_slug,
            )
            self.api = BitbucketAPI(base_url, email, token, workspace, repo_slug, default_ref)
        else:
            raise ValueError(f"Unsupported git provider: {provider_name}")

        self.provider = provider_name
        self.default_ref = default_ref
        self.last_commit: Optional[str] = None

    async def async_init(self) -> None:
        if hasattr(self.api, "get_last_commit"):
            logger.debug("Fetching last commit for provider={}.", self.provider)
            last_commit = await self.api.get_last_commit()
            self.last_commit = last_commit.get("sha") if isinstance(last_commit, dict) else None
            logger.debug("Initialised last_commit={} for provider={}.", self.last_commit, self.provider)
        else:
            logger.debug("Provider {} does not expose get_last_commit; skipping init cache.", self.provider)
            self.last_commit = None

    async def modify_file(self, path: str, commit_message: str, content: Union[str, bytes], *, branch: Optional[str] = None) -> None:
        logger.info("Modifying file at path={} on provider={} (branch={}).", path, self.provider, branch or self.default_ref)
        if hasattr(self.api, "create_or_update_file"):
            await self._ensure_exists_for_mutation(path, branch)
            await self.api.create_or_update_file(path, commit_message, content, branch=branch)
            return

        if hasattr(self.api, "modify_file_content"):
            await self._ensure_exists_for_mutation(path, branch)
            await self.api.modify_file_content(path, commit_message, self._ensure_str(content))
            return

        raise AttributeError("Underlying API does not support modify_file operation")

    async def add_file(self, path: str, commit_message: str, content: Union[str, bytes], *, branch: Optional[str] = None) -> None:
        logger.info("Adding file at path={} on provider={} (branch={}).", path, self.provider, branch or self.default_ref)
        await self._ensure_absent_for_create(path, branch)
        if hasattr(self.api, "create_new_file"):
            await self.api.create_new_file(path, commit_message, self._ensure_str(content))
            return

        if hasattr(self.api, "create_or_update_file"):
            await self.api.create_or_update_file(path, commit_message, content, branch=branch)
            return

        if hasattr(self.api, "modify_file_content"):
            await self.api.modify_file_content(path, commit_message, self._ensure_str(content))
            return

        raise AttributeError("Underlying API does not support add_file operation")

    async def delete_file(self, path: str, commit_message: str, *, branch: Optional[str] = None) -> None:
        logger.info("Deleting file at path={} on provider={} (branch={}).", path, self.provider, branch or self.default_ref)
        if hasattr(self.api, "delete_file"):
            try:
                await self._get_file(path, ref=branch or self.default_ref)
            except GitError as exc:
                logger.error(
                    "Failed to locate file {} on provider {} before delete: {}",
                    path,
                    self.provider,
                    exc.detail if hasattr(exc, "detail") else exc,
                )
                raise
            kwargs = {"branch": branch} if branch is not None else {}
            await self.api.delete_file(path, commit_message, **kwargs)
            return
        raise AttributeError("Underlying API does not support delete_file operation")

    async def get_file_content(self, path: str, ref: Optional[str] = None, encoding: str = "utf-8") -> str:
        logger.debug("Fetching text for path={} (ref={}) from provider={}.", path, ref or self.default_ref, self.provider)
        meta = await self._get_file(path, ref=ref)
        if not meta.content:
            raise GitError(status_code=500, detail=f"File {path} missing content on provider {self.provider}")
        return base64.b64decode(meta.content).decode(encoding)

    async def get_file_bytes(self, path: str, ref: Optional[str] = None) -> bytes:
        logger.debug("Fetching bytes for path={} (ref={}) from provider={}.", path, ref or self.default_ref, self.provider)
        meta = await self._get_file(path, ref=ref)
        if not meta.content:
            raise GitError(status_code=500, detail=f"File {path} missing content on provider {self.provider}")
        return base64.b64decode(meta.content)

    async def list_dir(self, path: str, ref: Optional[str] = None) -> List[Tuple[str, str]]:
        logger.debug("Listing directory path={} (ref={}) on provider={}.", path or "/", ref or self.default_ref, self.provider)
        items = await self._list_dir_raw(path, ref=ref)
        return [
            (item.name or "", item.path or "")
            for item in items
            if (item.name or "") and (item.path or "")
        ]

    async def list_files_recursive(self, path: str = "", ref: Optional[str] = None) -> List[str]:
        logger.debug("Listing files recursively from path={} (ref={}) on provider={}.", path or "/", ref or self.default_ref, self.provider)
        if hasattr(self.api, "list_files_recursive"):
            return await self.api.list_files_recursive(path, ref)

        files: List[str] = []
        stack: List[str] = [path.strip("/")] if path else [""]

        while stack:
            current = stack.pop()
            entries = await self._list_dir_raw(current, ref=ref)
            for entry in entries:
                entry_type = (entry.type or "").lower()
                entry_path = entry.path or ""
                if not entry_path:
                    continue
                if entry_type == "dir":
                    stack.append(entry_path)
                elif entry_type == "file":
                    files.append(entry_path)

        return sorted(set(files))

    async def get_changed_files(self, path: str, since: str, until: str) -> List[GitChangedFile]:
        logger.debug(
            "Fetching changed files for path={} between {} and {} on provider={}.",
            path,
            since,
            until,
            self.provider,
        )
        if not (hasattr(self.api, "commits_per_path") and hasattr(self.api, "compare_commits")):
            logger.debug("Provider {} lacks commit comparison endpoints; returning empty diff.", self.provider)
            return []

        commits = await self.api.commits_per_path(path, since, until)
        if not commits:
            logger.debug("No commits found for path={} in window {}-{} on provider={}.", path, since, until, self.provider)
            return []

        def _commit_date(commit: dict) -> str:
            commit_meta = commit.get("commit", {}) if isinstance(commit, dict) else {}
            author = commit_meta.get("author", {}) if isinstance(commit_meta, dict) else {}
            return author.get("date") or ""

        commits = sorted((c for c in commits if isinstance(c, dict)), key=_commit_date)
        if not commits:
            logger.debug("Filtered commits list empty for path={} on provider={}.", path, self.provider)
            return []

        head = commits[-1].get("sha")
        if not head:
            logger.debug("Head commit missing SHA for path={} on provider={}.", path, self.provider)
            return []

        base = self.last_commit or head
        logger.debug("Comparing commits base={} head={} for path={} on provider={}.", base, head, path, self.provider)
        diff = await self.api.compare_commits(base, head)
        self.last_commit = head
        files_raw = diff.get("files", []) if isinstance(diff, dict) else []

        files: List[GitChangedFile] = []
        for item in files_raw:
            if isinstance(item, GitChangedFile):
                files.append(item)
            elif isinstance(item, dict):
                try:
                    files.append(GitChangedFile.model_validate(item))
                except Exception:
                    logger.debug("Skipping diff entry due to validation error: {}", item)
        return files

    def commit_context(self, message: str = "Commit via context", branch: Optional[str] = None):
        if hasattr(self.api, "commit_context"):
            logger.debug("Creating commit_context on provider={} (branch={}, message={}).", self.provider, branch or self.default_ref, message)
            return self.api.commit_context(message=message, branch=branch)
        raise NotImplementedError("commit_context is not supported by this provider")

    @staticmethod
    def _ensure_str(content: Union[str, bytes], *, encoding: str = "utf-8") -> str:
        return content.decode(encoding) if isinstance(content, bytes) else content

    async def _ensure_exists_for_mutation(self, path: str, branch: Optional[str]) -> None:
        ref = branch or self.default_ref
        try:
            await self._get_file(path, ref=ref)
        except GitError as exc:
            logger.error(
                "Mutation target {} missing on provider {} (ref={}): {}",
                path,
                self.provider,
                ref,
                exc.detail if hasattr(exc, "detail") else exc,
            )
            raise

    async def _ensure_absent_for_create(self, path: str, branch: Optional[str]) -> None:
        ref = branch or self.default_ref
        try:
            await self._get_file(path, ref=ref)
        except GitError:
            return
        logger.error(
            "Creation target {} already exists on provider {} (ref={}).",
            path,
            self.provider,
            ref,
        )
        raise GitError(status_code=409, detail=f"File {path} already exists on {self.provider}")

    async def _get_file(self, path: str, ref: Optional[str]) -> GitFileContent:
        if self.provider == "bitbucket":
            return await self.api.get_file(path, ref=ref)
        return await self.api.get_file(path)

    async def _list_dir_raw(self, path: str, ref: Optional[str]) -> Sequence[GitDirectoryEntry]:
        if self.provider == "bitbucket":
            return await self.api.list_dir(path, ref=ref)
        return await self.api.list_dir(path)
