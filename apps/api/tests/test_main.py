import unittest

from fastapi.testclient import TestClient

from press_watch_api.main import app


class HealthCheckApiTest(unittest.TestCase):
    """ヘルスチェックAPIのテスト"""

    def test_health_returns_ok_response(self) -> None:
        """GET /healthがHTTP 200と正常ステータスを返すこと"""

        response = TestClient(app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
