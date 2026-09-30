"""
DingTalk HTTP client with automatic access_token management.

The access_token is cached in memory and refreshed automatically
when it expires (valid for 2 hours, refreshed 5 minutes early).
"""

import asyncio
import time
import logging
from collections import Counter
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
# httpx INFO logs include access_token and appsecret in legacy request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class DingTalkClientError(Exception):
    """Raised when a DingTalk API call returns a non-zero errcode."""

    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"DingTalk API error {errcode}: {errmsg}")

    @property
    def retryable(self) -> bool:
        return self.errcode in {-1, 88, 90018, 429} or 500 <= self.errcode < 600


class DingTalkClient:
    """Async HTTP client for DingTalk open-platform APIs."""

    # Token validity: 7200 seconds (2 hours).
    # Refresh 5 minutes (300 seconds) before expiry.
    TOKEN_REFRESH_BUFFER = 300

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http: Optional[httpx.AsyncClient] = None
        self._token_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._request_counts: Counter[str] = Counter()

    def request_counts(self) -> Dict[str, int]:
        return dict(self._request_counts)

    async def _throttle(self, path: str) -> None:
        async with self._rate_lock:
            delay = settings.dingtalk_request_interval - (time.monotonic() - self._last_request_at)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()
            self._request_counts[path] += 1

    def _safe_message(self, message: str) -> str:
        for secret in (self._access_token, settings.dingtalk_app_secret, settings.dingtalk_app_key):
            if secret:
                message = message.replace(secret, "<REDACTED>")
        return message

    async def _send(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        await self._throttle(path)
        http = await self._get_http()
        try:
            resp = await http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise DingTalkClientError(-1, f"Transport error: {type(exc).__name__}") from None
        if not 200 <= resp.status_code < 300:
            raise DingTalkClientError(resp.status_code, f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise DingTalkClientError(-2, "Invalid JSON response") from None
        if not isinstance(data, dict):
            raise DingTalkClientError(-2, "Invalid response object")
        return data

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
        data = await self._send(
            "GET",
            "/gettoken",
            params={
                "appkey": settings.dingtalk_app_key,
                "appsecret": settings.dingtalk_app_secret,
            },
        )
        errcode = data.get("errcode", 0)
        if errcode != 0:
            raise DingTalkClientError(errcode, self._safe_message(data.get("errmsg", "unknown")))

        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)

        self._access_token = token
        self._token_expires_at = time.time() + expires_in - self.TOKEN_REFRESH_BUFFER

        logger.info("DingTalk access_token refreshed, expires_in=%d", expires_in)
        return token

    async def get_access_token(self, invalid_token: Optional[str] = None) -> str:
        """Return a valid access_token, refreshing if necessary."""
        async with self._token_lock:
            if (
                self._access_token is None
                or time.time() >= self._token_expires_at
                or (invalid_token is not None and invalid_token == self._access_token)
            ):
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
        for attempt in range(2):
            query = {"access_token": token, **(params or {})}
            kwargs = {"params": query}
            if method.upper() != "GET":
                kwargs["json"] = json_body or {}
            data = await self._send(method, path, **kwargs)
            errcode = data.get("errcode", 0)
            if errcode == 0:
                return data
            if attempt == 0 and errcode in {40014, 42001}:
                token = await self.get_access_token(invalid_token=token)
                continue
            raise DingTalkClientError(errcode, self._safe_message(data.get("errmsg", "unknown")))

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

    async def workflow_instance(self, instance_id: str) -> Dict[str, Any]:
        """Read current workflow detail using the modern API token header."""
        token = await self.get_access_token()
        path = "/v1.0/workflow/processInstances"
        for attempt in range(2):
            try:
                data = await self._send(
                    "GET", "https://api.dingtalk.com" + path,
                    params={"processInstanceId": instance_id},
                    headers={"x-acs-dingtalk-access-token": token},
                )
            except DingTalkClientError as exc:
                if exc.errcode == 401 and attempt == 0:
                    token = await self.get_access_token(invalid_token=token)
                    continue
                raise
            if data.get("success") is False or data.get("code"):
                raise DingTalkClientError(-2, self._safe_message(str(data.get("message", "Workflow detail failed"))))
            result = data.get("result", data)
            if not isinstance(result, dict):
                raise DingTalkClientError(-2, "Invalid workflow detail")
            return result


# Module-level singleton so the whole application shares one token cache.
dingtalk_client = DingTalkClient()
