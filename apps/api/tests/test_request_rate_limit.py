import asyncio
import unittest
from unittest.mock import Mock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session
from starlette.status import HTTP_200_OK, HTTP_429_TOO_MANY_REQUESTS

from press_watch_api.main import app
from press_watch_api.request_rate_limit import RequestRateLimit


EXPECTED_BURST_CAPACITY = 20


class RequestRateLimitTest(unittest.IsolatedAsyncioTestCase):
    """HTTPで共有枠とDB到達の境界を確認"""

    async def test_shared_limit_rejects_before_db_and_recovers(self) -> None:
        """両ルートの同時要求を合算し、枯渇時は入力検証やDB処理より先に拒否"""
        session = Mock(spec=Session)
        factory = Mock(return_value=session)
        capacity = EXPECTED_BURST_CAPACITY
        excess = 2
        paths = ("/fixed-categories", "/press-releases")
        with (
            patch(
                "press_watch_api.request_rate_limit.monotonic",
                return_value=0.0,
            ) as clock,
            patch(
                "press_watch_api.dependencies.get_session_factory",
                return_value=factory,
            ) as get_factory,
            patch(
                "press_watch_api.routers.press_releases.count_press_releases",
                return_value=0,
            ) as count,
            patch(
                "press_watch_api.routers.fixed_categories."
                "list_fixed_categories",
                return_value=(),
            ) as categories,
        ):
            self.enterContext(
                patch.object(
                    app.state, "request_rate_limit", RequestRateLimit(),
                )
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                responses = await asyncio.gather(*(
                    client.get(
                        paths[index % len(paths)],
                        headers={"X-Forwarded-For": f"192.0.2.{index + 1}"},
                    )
                    for index in range(capacity + excess)
                ))
                self.assertEqual(
                    sorted(response.status_code for response in responses),
                    [HTTP_200_OK] * capacity
                    + [HTTP_429_TOO_MANY_REQUESTS] * excess,
                )
                self.assertEqual(
                    (get_factory.call_count, factory.call_count),
                    (capacity, capacity),
                )
                self.assertEqual(
                    count.call_count + categories.call_count, capacity,
                )

                for path in ("/press-releases?page=0", "/fixed-categories"):
                    rejected = await client.get(path)
                    self.assertEqual(
                        rejected.status_code, HTTP_429_TOO_MANY_REQUESTS,
                    )
                    self.assertEqual(
                        rejected.json(), {"detail": "Too many requests"},
                    )
                    self.assertEqual(rejected.headers["Retry-After"], "1")

                health = await client.get("/health")
                self.assertEqual(health.status_code, HTTP_200_OK)
                clock.return_value = 0.499
                before_refill = await client.get("/fixed-categories")
                self.assertEqual(
                    before_refill.status_code,
                    HTTP_429_TOO_MANY_REQUESTS,
                )
                self.assertEqual(
                    (get_factory.call_count, factory.call_count),
                    (capacity, capacity),
                )
                self.assertEqual(
                    count.call_count + categories.call_count, capacity,
                )
                clock.return_value = 0.5
                after_refill = await client.get("/fixed-categories")
                self.assertEqual(after_refill.status_code, HTTP_200_OK)
                self.assertEqual(
                    (get_factory.call_count, factory.call_count),
                    (capacity + 1, capacity + 1),
                )

                clock.return_value = 120.0
                recovered = [
                    await client.get("/fixed-categories")
                    for _ in range(capacity + 1)
                ]
                self.assertEqual(
                    [response.status_code for response in recovered],
                    [HTTP_200_OK] * capacity + [HTTP_429_TOO_MANY_REQUESTS],
                )

    def test_openapi_declares_rate_limit_for_both_routes(self) -> None:
        """読み取りルートのOpenAPIに429の本文と待ち時間ヘッダーを掲載"""
        for path in ("/press-releases", "/fixed-categories"):
            with self.subTest(path=path):
                responses = app.openapi()["paths"][path]["get"]["responses"]
                response = responses[str(HTTP_429_TOO_MANY_REQUESTS)]
                self.assertEqual(
                    response["content"]["application/json"]["schema"],
                    {"$ref": "#/components/schemas/ErrorResponse"},
                )
                self.assertEqual(
                    response["headers"]["Retry-After"]["schema"]["type"],
                    "integer",
                )
