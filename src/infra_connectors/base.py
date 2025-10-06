"""Shared HTTP client utilities used by the service specific clients."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import httpx


class BaseAPI:
    """Small asynchronous wrapper around :class:`httpx.AsyncClient`.

    Each request opens a short lived client instance to avoid sharing state
    across coroutines.  The helper centralises the base URL, default headers
    and timeout configuration used by the higher level API clients.
    """

    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = 10.0,
        verify: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.verify = verify

    async def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[List[Tuple[str, Tuple[str, bytes, str]]]] = None,
    ) -> httpx.Response:
        """Dispatch a request and return the raw :class:`httpx.Response`."""

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        merged_headers = {**self.headers, **(headers or {})}

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=merged_headers,
            timeout=self.timeout,
            verify=self.verify,
        ) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params,
                data=data,
                json=json,
                headers=merged_headers,
                files=files,
            )
        return response

    async def get(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", endpoint, **kwargs)

    async def upload_file_bytes(
        self,
        endpoint: str,
        field_name: str,
        filename: str,
        file_bytes: bytes,
        content_type: str = "application/octet-stream",
        extra_fields: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        files = [
            (field_name, (filename, file_bytes, content_type)),
        ]
        if extra_fields:
            for key, value in extra_fields.items():
                files.append((key, (None, value)))
        return await self.post(endpoint, files=files)

    async def download_file_bytes(self, endpoint: str) -> bytes:
        response = await self.get(endpoint)
        return response.content

