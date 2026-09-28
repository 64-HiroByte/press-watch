import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from press_watch_api.main import app


class HealthCheckApiTest(unittest.TestCase):
    """ヘルスチェックAPIのテスト"""

    def test_health_returns_ok_response(self) -> None:
        """GET /healthがHTTP 200と正常ステータスを返すこと"""

        response = TestClient(app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_application_import_and_health_do_not_require_database_url(
        self,
    ) -> None:
        """DB設定が空でもapplicationをimportしてhealthを実行できること"""

        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            main_module = importlib.import_module("press_watch_api.main")
            reloaded_main_module = importlib.reload(main_module)
            response = TestClient(reloaded_main_module.app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
