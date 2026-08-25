from datetime import UTC, date, datetime
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.main import app
from press_watch_api.models.press_release import PressRelease
from api_test_constants import (
    ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1,
    ENV_PRESS_RELEASE_URL_2 as SOURCE_URL_2,
)


class PressReleaseListApiTest(unittest.TestCase):
    """報道発表一覧APIのテスト"""

    def setUp(self) -> None:
        """APIテスト用のDB Session dependency差し替え"""

        self.session = Mock(spec=Session)

        def override_get_db_session():
            yield self.session

        app.dependency_overrides[get_db_session] = override_get_db_session
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_returns_default_page_with_public_fields(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """既定のページ条件と公開対象項目だけを返すこと"""

        count_press_releases_mock.return_value = 2
        list_press_releases_mock.return_value = (
            _press_release(
                title="報道発表1",
                source_url=SOURCE_URL_1,
                source_categories=["総合政策", "自然環境"],
                id=2,
            ),
            _press_release(
                title="報道発表2",
                source_url=SOURCE_URL_2,
                published_at=date(2026, 5, 25),
                source_categories=None,
                id=1,
            ),
        )

        response = self.client.get("/press-releases")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {
                        "title": "報道発表1",
                        "source_url": SOURCE_URL_1,
                        "published_at": "2026-05-26",
                        "source_categories": ["総合政策", "自然環境"],
                    },
                    {
                        "title": "報道発表2",
                        "source_url": SOURCE_URL_2,
                        "published_at": "2026-05-25",
                        "source_categories": None,
                    },
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total_items": 2,
                    "total_pages": 1,
                },
            },
        )
        count_press_releases_mock.assert_called_once_with(self.session)
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=20,
            offset=0,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_applies_requested_page_and_rounds_up_total_pages(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """指定ページをoffsetへ変換して総ページ数を切り上げること"""

        count_press_releases_mock.return_value = 25
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page": 2, "page_size": 10},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 2,
                "page_size": 10,
                "total_items": 25,
                "total_pages": 3,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=10,
            offset=10,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_returns_empty_response_without_list_query_when_no_data(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """0件時は一覧取得を省略して総ページ数0を返すこと"""

        count_press_releases_mock.return_value = 0

        response = self.client.get("/press-releases")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": 20,
                "total_items": 0,
                "total_pages": 0,
            },
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_returns_empty_response_without_query_after_last_page(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """最終ページ超過時は一覧取得を省略して要求ページを返すこと"""

        count_press_releases_mock.return_value = 21

        response = self.client.get(
            "/press-releases",
            params={"page": 4, "page_size": 10},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 4,
                "page_size": 10,
                "total_items": 21,
                "total_pages": 3,
            },
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_accepts_maximum_pagination_parameters(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """ページ番号とページサイズの上限値を受け付けること"""

        count_press_releases_mock.return_value = 0

        response = self.client.get(
            "/press-releases",
            params={"page": 10_000, "page_size": 100},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 10_000,
                "page_size": 100,
                "total_items": 0,
                "total_pages": 0,
            },
        )
        count_press_releases_mock.assert_called_once_with(self.session)
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_accepts_minimum_pagination_parameters(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """ページ番号とページサイズの下限値を受け付けること"""

        count_press_releases_mock.return_value = 1
        list_press_releases_mock.return_value = (
            _press_release(
                title="報道発表",
                source_url=SOURCE_URL_1,
                source_categories=None,
                id=1,
            ),
        )

        response = self.client.get(
            "/press-releases",
            params={"page": 1, "page_size": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": 1,
                "total_items": 1,
                "total_pages": 1,
            },
        )
        count_press_releases_mock.assert_called_once_with(self.session)
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=1,
            offset=0,
        )

    def test_list_rejects_out_of_range_pagination_parameters(self) -> None:
        """ページ条件の下限未満と上限超過をHTTP 422で拒否すること"""

        invalid_params = (
            {"page": -1},
            {"page": 0},
            {"page": 10_001},
            {"page_size": -1},
            {"page_size": 0},
            {"page_size": 101},
        )

        for params in invalid_params:
            with self.subTest(params=params):
                response = self.client.get("/press-releases", params=params)

                self.assertEqual(response.status_code, 422)

    def test_list_response_schema_is_registered_in_openapi(self) -> None:
        """一覧response schemaがOpenAPIの成功レスポンスへ登録されること"""

        response_schema = app.openapi()["paths"]["/press-releases"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]

        self.assertEqual(
            response_schema,
            {"$ref": "#/components/schemas/PressReleaseListResponse"},
        )


def _press_release(
    *,
    title: str,
    source_url: str,
    published_at: date = date(2026, 5, 26),
    source_categories: list[str] | None,
    id: int,
) -> PressRelease:
    """一覧APIへ渡す報道発表DBモデルを生成

    Args:
        title: 報道発表タイトル
        source_url: 報道発表詳細ページURL
        published_at: 公開日
        source_categories: 取得元カテゴリ
        id: DBモデルの主キー

    Returns:
        APIテスト用の報道発表DBモデル
    """

    return PressRelease(
        id=id,
        title=title,
        source_url=source_url,
        published_at=published_at,
        source_categories=source_categories,
        fetched_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
    )


if __name__ == "__main__":
    unittest.main()
