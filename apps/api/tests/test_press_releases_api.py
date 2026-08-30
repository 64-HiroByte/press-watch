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
                    "page_size": 50,
                    "total_items": 2,
                    "total_pages": 1,
                },
            },
        )
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query=None,
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=50,
            offset=0,
            title_query=None,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_applies_requested_page_and_rounds_up_total_pages(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """指定ページをoffsetへ変換して総ページ数を切り上げること"""

        count_press_releases_mock.return_value = 34_421
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
                "total_items": 34_421,
                "total_pages": 3_443,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=10,
            offset=10,
            title_query=None,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_does_not_add_page_when_total_items_is_divisible(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """総件数がページサイズで割り切れる場合に余分なページを作らないこと"""

        count_press_releases_mock.return_value = 100
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page": 2, "page_size": 50},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 2,
                "page_size": 50,
                "total_items": 100,
                "total_pages": 2,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=50,
            offset=50,
            title_query=None,
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
                "page_size": 50,
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

        count_press_releases_mock.return_value = 34_421

        response = self.client.get(
            "/press-releases",
            params={"page": 690, "page_size": 50},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 690,
                "page_size": 50,
                "total_items": 34_421,
                "total_pages": 689,
            },
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_applies_last_page_offset_for_actual_data_size(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """実データ規模の最終ページを正しいoffsetへ変換すること"""

        count_press_releases_mock.return_value = 34_421
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page": 689, "page_size": 50},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 689,
                "page_size": 50,
                "total_items": 34_421,
                "total_pages": 689,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=50,
            offset=34_400,
            title_query=None,
        )

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
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query=None,
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_passes_maximum_page_size_to_repository(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """ページサイズの上限値をrepositoryの取得件数へ渡すこと"""

        count_press_releases_mock.return_value = 101
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page_size": 100},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": 100,
                "total_items": 101,
                "total_pages": 2,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=100,
            offset=0,
            title_query=None,
        )

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
            params={"page": 1, "page_size": 10},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": 10,
                "total_items": 1,
                "total_pages": 1,
            },
        )
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query=None,
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=10,
            offset=0,
            title_query=None,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_applies_normalized_title_query_to_count_and_list(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """前後空白を除いたタイトル検索条件を件数と一覧へ渡すこと"""

        count_press_releases_mock.return_value = 11
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"q": "  水質50%_/  ", "page": 2, "page_size": 10},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 2,
                "page_size": 10,
                "total_items": 11,
                "total_pages": 2,
            },
        )
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query="水質50%_/",
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=10,
            offset=10,
            title_query="水質50%_/",
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_search_uses_default_page_size(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """タイトル検索でも未指定のページサイズを50件とすること"""

        count_press_releases_mock.return_value = 51
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"q": "水質"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": 50,
                "total_items": 51,
                "total_pages": 2,
            },
        )
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query="水質",
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=50,
            offset=0,
            title_query="水質",
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_treats_empty_title_query_as_unspecified(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """空文字列と空白だけの検索条件を未指定として扱うこと"""

        count_press_releases_mock.return_value = 0

        for title_query in ("", "   ", "　", " " * 100):
            with self.subTest(title_query=title_query):
                response = self.client.get(
                    "/press-releases",
                    params={"q": title_query},
                )

                self.assertEqual(response.status_code, 200)
                count_press_releases_mock.assert_called_once_with(
                    self.session,
                    title_query=None,
                )
                list_press_releases_mock.assert_not_called()

                count_press_releases_mock.reset_mock()
                list_press_releases_mock.reset_mock()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_accepts_maximum_title_query_length(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """100文字のタイトル検索条件を受け付けること"""

        title_query = "水" * 100
        count_press_releases_mock.return_value = 0

        response = self.client.get(
            "/press-releases",
            params={"q": title_query},
        )

        self.assertEqual(response.status_code, 200)
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query=title_query,
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_rejects_title_query_over_maximum_length(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """101文字のタイトル検索条件をHTTP 422で拒否すること"""

        for title_query in ("水" * 101, " " * 101):
            with self.subTest(title_query=title_query):
                response = self.client.get(
                    "/press-releases",
                    params={"q": title_query},
                )

                self.assertEqual(response.status_code, 422)
        count_press_releases_mock.assert_not_called()
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_rejects_title_query_containing_null_character(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """NUL文字を含むタイトル検索条件をHTTP 422で拒否すること"""

        response = self.client.get(
            "/press-releases",
            params={"q": "水質\x00検査"},
        )

        self.assertEqual(response.status_code, 422)
        count_press_releases_mock.assert_not_called()
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_search_returns_empty_response_when_no_title_matches(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """タイトル検索結果が0件の場合は一覧取得を省略すること"""

        count_press_releases_mock.return_value = 0

        response = self.client.get(
            "/press-releases",
            params={"q": "該当しない語"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["pagination"]["total_pages"], 0)
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query="該当しない語",
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_search_skips_list_query_after_last_matching_page(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """検索後の最終ページ超過時は一覧取得を省略すること"""

        count_press_releases_mock.return_value = 21

        response = self.client.get(
            "/press-releases",
            params={
                "q": "水質",
                "page": 4,
                "page_size": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["pagination"]["total_pages"], 3)
        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query="水質",
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_rejects_out_of_range_pagination_parameters(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """ページ条件の下限未満と上限超過をHTTP 422で拒否すること"""

        count_press_releases_mock.return_value = 0
        invalid_params = (
            {"page": -1},
            {"page": 0},
            {"page": 10_001},
            {"page_size": 9},
            {"page_size": 101},
        )

        for params in invalid_params:
            with self.subTest(params=params):
                response = self.client.get("/press-releases", params=params)

                self.assertEqual(response.status_code, 422)

        count_press_releases_mock.assert_not_called()
        list_press_releases_mock.assert_not_called()

    def test_list_response_schema_is_registered_in_openapi(self) -> None:
        """一覧response schemaがOpenAPIの成功レスポンスへ登録されること"""

        response_schema = app.openapi()["paths"]["/press-releases"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]

        self.assertEqual(
            response_schema,
            {"$ref": "#/components/schemas/PressReleaseListResponse"},
        )

    def test_list_page_size_is_registered_in_openapi(self) -> None:
        """ページサイズの既定値と許容範囲がOpenAPIへ登録されること"""

        parameters = app.openapi()["paths"]["/press-releases"]["get"][
            "parameters"
        ]
        page_size_parameter = next(
            parameter
            for parameter in parameters
            if parameter["name"] == "page_size"
        )

        self.assertEqual(page_size_parameter["in"], "query")
        self.assertFalse(page_size_parameter["required"])
        self.assertEqual(page_size_parameter["schema"]["default"], 50)
        self.assertEqual(page_size_parameter["schema"]["minimum"], 10)
        self.assertEqual(page_size_parameter["schema"]["maximum"], 100)

    def test_list_title_query_is_registered_in_openapi(self) -> None:
        """任意のタイトル検索条件と最大長がOpenAPIへ登録されること"""

        parameters = app.openapi()["paths"]["/press-releases"]["get"][
            "parameters"
        ]
        title_query_parameter = next(
            parameter for parameter in parameters if parameter["name"] == "q"
        )
        string_schema = next(
            schema
            for schema in title_query_parameter["schema"]["anyOf"]
            if schema.get("type") == "string"
        )

        self.assertEqual(title_query_parameter["in"], "query")
        self.assertFalse(title_query_parameter["required"])
        self.assertEqual(string_schema["maxLength"], 100)
        self.assertEqual(string_schema["pattern"], r"^[^\x00]*$")


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
