"""High level helpers for interacting with Argo CD."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any, Dict, Optional

import yaml
from loguru import logger

from ..errors import ArgoCDError
from .api import ArgoCDAPI

__all__ = ["ArgoCD", "logger"]


@dataclass(frozen=True)
class _AppFingerprint:
    revision: Optional[str]
    reconciled_at: Optional[str]
    op_finished_at: Optional[str]
    history_len: int

def _fp_from_status(status: Dict[str, Any]) -> _AppFingerprint:
    sync = status.get("sync") or {}
    op = status.get("operationState") or {}
    hist = status.get("history") or []
    return _AppFingerprint(
        revision=sync.get("revision"),
        reconciled_at=status.get("reconciledAt"),
        op_finished_at=op.get("finishedAt"),
        history_len=len(hist),
    )


def evaluate_argo_result(app_status: dict) -> dict:
    """
    Evaluate ArgoCD Application status and return:
      {'result': 'SUCCESS' | 'FAILED' | 'INPROGRESS', 'message': str}
    """
    sync_status = (app_status.get("sync") or {}).get("status")
    health_status = (app_status.get("health") or {}).get("status")
    phase = (app_status.get("operationState") or {}).get("phase")
    op_msg = (app_status.get("operationState") or {}).get("message") or ""

    import re

    def extract_namespace(msg: str) -> str | None:
        match = re.search(r'namespaces?\s+"([^"]+)"\s+not found', msg)
        return match.group(1) if match else None

    # 1️⃣ Explicit Argo operation failure
    if phase in {"Failed", "Error"}:
        ns = extract_namespace(op_msg)
        if ns:
            return {"result": "FAILED", "message": f"Namespace '{ns}' not found"}
        if "forbidden" in op_msg or "permission" in op_msg:
            return {"result": "FAILED", "message": "RBAC or permission denied"}
        if "helm" in op_msg.lower() and ("render" in op_msg.lower() or "template" in op_msg.lower()):
            return {"result": "FAILED", "message": "Helm rendering error"}
        return {"result": "FAILED", "message": op_msg or "ArgoCD operation failed"}

    # 2️⃣ Healthy and synced
    if sync_status == "Synced" and health_status == "Healthy":
        return {"result": "SUCCESS", "message": "Application is healthy and synced"}

    # 3️⃣ OutOfSync or still reconciling
    if sync_status in {"OutOfSync", "Unknown"} or phase == "Running":
        return {
            "result": "INPROGRESS",
            "message": f"Application is progressing (Sync={sync_status}, Health={health_status})",
        }

    # 4️⃣ Missing or degraded health
    if health_status in {"Missing", "Degraded"}:
        ns = extract_namespace(op_msg)
        if ns:
            return {"result": "FAILED", "message": f"Namespace '{ns}' not found"}
        return {"result": "FAILED", "message": f"Health={health_status}, Sync={sync_status}"}

    # 5️⃣ Fallback (still in progress)
    return {
        "result": "INPROGRESS",
        "message": f"Sync={sync_status}, Health={health_status}, Phase={phase}",
    }



class ArgoCD:
    """Convenience wrapper that offers higher level Argo CD interactions."""

    def __init__(self, base_url: str, api_key: str, application_set_timeout: int) -> None:
        self.api = ArgoCDAPI(base_url, api_key)
        self.application_set_timeout = application_set_timeout


    async def wait_for_update(self, app_name: str) -> Dict[str, Any]:
        """
        Wait until the ArgoCD Application shows a new update (revision or reconcile change).
        Returns the latest Application object when a change is detected.

        Uses self.application_set_timeout as the maximum wait time (in seconds).
        """
        
        await self.wait_for_app_creation(app_name)

        current = await self.api.get_app(app_name)
        baseline_fp = _fp_from_status(current.get("status", {}))

        elapsed = 0
        while elapsed < self.application_set_timeout:
            await asyncio.sleep(1)
            elapsed += 1
            try:
                app = await self.api.get_app(app_name)
            except ArgoCDError as exc:

                if exc.status_code in (403, 404):
                    logger.info("Application {} disappeared while waiting for update", app_name)
                    raise TimeoutError(f"Application {app_name} no longer exists") from exc
                raise

            fp = _fp_from_status(app.get("status", {}))
            if fp != baseline_fp:
                logger.info("Detected update for {} (revision: {} -> {}, reconciledAt: {} -> {})",
                            app_name,
                            baseline_fp.revision, fp.revision,
                            baseline_fp.reconciled_at, fp.reconciled_at)
                return app

        raise TimeoutError(f"Timed out waiting for update on {app_name}")


    async def wait_for_app_deletion(self, app_name: str) -> None:
        """Wait until the given Argo CD application is deleted."""
        timeout = 0
        
        try:
            await self.api.get_app(app_name)
        except ArgoCDError as exc:
            if exc.status_code == 403:  # app no longer exists
                return None
            raise
        
        while timeout < self.application_set_timeout:
            logger.info("Waiting for {} to be deleted...", app_name)
            try:
                await self.api.get_app(app_name)
            except ArgoCDError as exc:
                if exc.status_code == 403:  # app no longer exists
                    return None
                raise
            await asyncio.sleep(1)
            timeout += 1

        raise TimeoutError(f"Timed out waiting for {app_name} to be deleted")

    async def wait_for_app_creation(self, app_name: str) -> None:
        timeout = 0
        while timeout < self.application_set_timeout:
            logger.info("Waiting for {} to be created...", app_name)
            try:
                await self.api.get_app(app_name)
                return None
            except ArgoCDError as exc:
                if exc.status_code != 403:
                    raise
                await asyncio.sleep(1)
                timeout += 1

        raise TimeoutError(f"Timed out waiting for {app_name}")

    async def sync(self, app_name: str) -> None:
        logger.info(f"Syncing {app_name}")
        await self.api.sync_app(app_name)

    async def get_app_status(self, app_name: str) -> Dict[str, Any]:
        logger.info(f"Getting status for {app_name}")
        response = await self.api.get_app(app_name)
        status = evaluate_argo_result(response["status"])
        return status

    async def get_app_values(self, app_name: str) -> str:
        logger.info("Getting ArgoCD app values for {}", app_name)
        response = await self.api.get_app(app_name)
        return response.get("spec", {}).get("source", {}).get("helm", {}).get("values", "")

    async def modify_values(self, values: Dict[str, Any], app_name: str, namespace: str, project: str) -> None:
        logger.info(f"Modifying values for {app_name}")
        values_yaml = yaml.safe_dump(values)
        data = {
            "spec": {
                "source": {
                    "helm": {
                        "values": values_yaml,
                    }
                }
            }
        }

        await self.api.patch_app(data, app_name, namespace, project)
