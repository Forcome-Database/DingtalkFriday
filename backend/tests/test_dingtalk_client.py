import asyncio
import unittest

import httpx

from app.dingtalk.client import DingTalkClient


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_requests_share_one_token_refresh(self):
        token_requests = 0

        async def respond(request):
            nonlocal token_requests
            if request.url.path == "/gettoken":
                token_requests += 1
                await asyncio.sleep(0.02)
                return httpx.Response(200, json={
                    "errcode": 0, "access_token": "test-token", "expires_in": 7200,
                })
            return httpx.Response(200, json={"errcode": 0, "result": []})

        client = DingTalkClient()
        client._http = httpx.AsyncClient(
            base_url="https://example.test", transport=httpx.MockTransport(respond)
        )
        try:
            await asyncio.gather(*(client.get("/data") for _ in range(20)))
        finally:
            await client.close()
        self.assertEqual(token_requests, 1)


if __name__ == "__main__":
    unittest.main()
