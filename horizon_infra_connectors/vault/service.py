"""High level helpers wrapping the Vault API client."""

from __future__ import annotations

from typing import Mapping, Union

from pydantic import BaseModel
from loguru import logger

from .api import VaultAPI
from .models import VaultSecret, VaultSecretPayload

__all__ = ["Vault", "logger"]


class Vault:
    """Higher level wrapper around :class:`VaultAPI`."""

    def __init__(self, base_url: str, token: str) -> None:
        self.api = VaultAPI(base_url, token)

    async def read_secret(self, path: str) -> VaultSecret:
        logger.debug("Reading Vault secret at {}", path)
        response = await self.api.read_secret(path)
        return response.data

    async def write_secret(
        self,
        path: str,
        data: Union[VaultSecretPayload, Mapping[str, object], BaseModel],
    ) -> None:
        logger.debug("Writing Vault secret at {}", path)
        if isinstance(data, VaultSecretPayload):
            payload = data
        elif isinstance(data, BaseModel):
            payload = VaultSecretPayload(data=data.model_dump(exclude_none=True))
        else:
            payload = VaultSecretPayload(data=dict(data))
        await self.api.write_secret(path, payload)

    async def delete_secret(self, path: str) -> None:
        logger.debug("Deleting Vault secret at {}", path)
        await self.api.delete_secret(path)
