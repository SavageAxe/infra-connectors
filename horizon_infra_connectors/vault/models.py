"""Pydantic models that describe Vault payloads."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field, ConfigDict

__all__ = ["VaultSecret", "VaultSecretResponse", "VaultSecretPayload"]


class VaultSecret(BaseModel):
    """Secret data and metadata returned by Vault."""

    model_config = ConfigDict(extra="allow")

    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VaultSecretResponse(BaseModel):
    """Envelope returned by the Vault KV API."""

    model_config = ConfigDict(extra="allow")

    data: VaultSecret = Field(default_factory=VaultSecret)


class VaultSecretPayload(BaseModel):
    """Payload used to write secrets to Vault."""

    model_config = ConfigDict(extra="allow")

    data: Dict[str, Any] = Field(default_factory=dict)
