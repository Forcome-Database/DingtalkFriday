"""
DingTalk HTTP client with automatic access_token management.

The access_token is cached in memory and refreshed automatically
when it expires (valid for 2 hours, refreshed 5 minutes early).
"""

import time
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class DingTalkClientError(Exception):
    """Raised when a DingTalk API call returns a non-zero errcode."""

    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"DingTalk API error {errcode}: {errmsg}")


class DingTalkClient:
    """Async HTTP client for DingTalk open-platform APIs."""

    # Token validity: 7200 seconds (2 hours).
    # Refresh 5 minutes (300 seconds) before expiry.
    TOKEN_REFRESH_BUFFER = 300

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http: Optional[httpx.AsyncClient] = None

    async def _get_http(self) -> httpx.AsyncClient:
        """Lazy-initialize the underlying httpx client."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=settings.dingtalk_base_url,
                timeout=30.0,
            )
        return self._http

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _refresh_token(self) -> str:
        """
        Fetch a new access_token from DingTalk.
        GET /gettoken?appkey=xxx&appsecret=xxx
        """
        http = await self._get_http()
        resp = await http.get(
            "/gettoken",
            params={
                "appkey": settings.dingtalk_app_key,
                "appsecret": settings.dingtalk_app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        errcode = data.get("errcode", 0)
        if errcode != 0:
            raise DingTalkClientError(errcode, data.get("errmsg", "unknown"))

        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)

        self._access_token = token
        self._token_expires_at = time.time() + expires_in - self.TOKEN_REFRESH_BUFFER

        logger.info("DingTalk access_token refreshed, expires_in=%d", expires_in)
        return token

    async def get_access_token(self) -> str:
        """Return a valid access_token, refreshing if necessary."""
        if self._access_token is None or time.time() >= self._token_expires_at:
            return await self._refresh_token()
        return self._access_token

    # ------------------------------------------------------------------
    # Generic request helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute an authenticated API request.
        Automatically attaches access_token as a query parameter.
        Raises DingTalkClientError if errcode != 0.
        """
        token = await self.get_access_token()
        http = await self._get_http()

        # Merge access_token into query params
        query = {"access_token": token}
        if params:
            query.update(params)

        if method.upper() == "GET":
            resp = await http.get(path, params=query)
        else:
            resp = await http.post(path, params=query, json=json_body or {})

        resp.raise_for_status()
        data = resp.json()

        errcode = data.get("errcode", 0)
        if errcode != 0:
            raise DingTalkClientError(errcode, data.get("errmsg", "unknown"))

        return data

    async def get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Authenticated GET request."""
        return await self._request("GET", path, params=params)

    async def post(
        self, path: str, json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Authenticated POST request."""
        return await self._request("POST", path, json_body=json_body)


# Module-level singleton so the whole application shares one token cache.
dingtalk_client = DingTalkClient()
