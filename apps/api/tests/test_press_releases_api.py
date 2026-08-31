from datetime import UTC, date, datetime
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.main import app
from press_watch_api.models.press_release import PressRelease
from api_test_constants import (
    ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1,
    ENV_PRESS_RELEASE_URL_2 as SOURCE_URL_2,
)

EXPECTED_DEFAULT_PAGE_SIZE = 50
EXPECTED_MIN_PAGE_SIZE = 10
EXPECTED_MAX_PAGE_SIZE = 100


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

    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_count_database_error_returns_safe_json_response(
        self,
        count_press_releases_mock: Mock,
    ) -> None:
        """件数取得のDB例外を固定JSONのHTTP 500として返すこと"""

        count_press_releases_mock.side_effect = SQLAlchemyError(
            "synthetic database error"
        )

        response = TestClient(app, raise_server_exceptions=False).get(
            "/press-releases"
        )

        count_press_releases_mock.assert_called_once_with(
            self.session,
            title_query=None,
        )
        self.assertTrue(
            response.status_code == 500,
            "DB例外時はHTTP 500を返すこと",
        )
        self.assertTrue(
            response.headers.get("content-type", "").partition(";")[0]
            == "application/json",
            "DB例外時はJSONのContent-Typeを返すこと",
        )

        response_json = None
        try:
            response_json = response.json()
        except ValueError:
            pass
        self.assertTrue(
            response_json == {"detail": "Internal server error"},
            "DB例外時は内部情報を含まない固定JSONを返すこと",
        )

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
                    "page_size": EXPECTED_DEFAULT_PAGE_SIZE,
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
            limit=EXPECTED_DEFAULT_PAGE_SIZE,
            offset=0,
            title_query=None,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_applies_requested_page_and_offset(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """指定ページをoffsetへ変換して一覧取得すること"""

        requested_page = 2
        page_size = EXPECTED_MIN_PAGE_SIZE
        total_items = page_size * requested_page + 1
        expected_offset = page_size * (requested_page - 1)

        count_press_releases_mock.return_value = total_items
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page": requested_page, "page_size": page_size},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"]["page"],
            requested_page,
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=page_size,
            offset=expected_offset,
            title_query=None,
        )

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_calculates_total_pages_around_divisible_boundary(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """ページサイズで割り切れる件数の前後で総ページ数を正しく返すこと"""

        page_size = EXPECTED_DEFAULT_PAGE_SIZE
        expected_full_pages = 2
        divisible_total_items = page_size * expected_full_pages
        list_press_releases_mock.return_value = ()

        cases = (
            (divisible_total_items - 1, expected_full_pages),
            (divisible_total_items, expected_full_pages),
            (divisible_total_items + 1, expected_full_pages + 1),
        )

        for total_items, expected_total_pages in cases:
            with self.subTest(
                total_items=total_items,
                expected_total_pages=expected_total_pages,
            ):
                count_press_releases_mock.return_value = total_items

                response = self.client.get(
                    "/press-releases",
                    params={"page_size": page_size},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json()["pagination"]["total_pages"],
                    expected_total_pages,
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
                "page_size": EXPECTED_DEFAULT_PAGE_SIZE,
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

        page_size = EXPECTED_DEFAULT_PAGE_SIZE
        last_page = 2
        total_items = page_size * last_page
        requested_page = last_page + 1

        count_press_releases_mock.return_value = total_items

        response = self.client.get(
            "/press-releases",
            params={"page": requested_page, "page_size": page_size},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": requested_page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": last_page,
            },
        )
        list_press_releases_mock.assert_not_called()

    @patch("press_watch_api.routers.press_releases.list_press_releases")
    @patch("press_watch_api.routers.press_releases.count_press_releases")
    def test_list_applies_last_page_offset(
        self,
        count_press_releases_mock: Mock,
        list_press_releases_mock: Mock,
    ) -> None:
        """最終ページを正しいoffsetへ変換すること"""

        page_size = EXPECTED_DEFAULT_PAGE_SIZE
        last_page = 3
        expected_offset = page_size * (last_page - 1)
        total_items = expected_offset + 1

        count_press_releases_mock.return_value = total_items
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page": last_page, "page_size": page_size},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": last_page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": last_page,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=page_size,
            offset=expected_offset,
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
            params={"page": 10_000, "page_size": EXPECTED_MAX_PAGE_SIZE},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 10_000,
                "page_size": EXPECTED_MAX_PAGE_SIZE,
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

        total_items = EXPECTED_MAX_PAGE_SIZE + 1

        count_press_releases_mock.return_value = total_items
        list_press_releases_mock.return_value = ()

        response = self.client.get(
            "/press-releases",
            params={"page_size": EXPECTED_MAX_PAGE_SIZE},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": EXPECTED_MAX_PAGE_SIZE,
                "total_items": total_items,
                "total_pages": 2,
            },
        )
        list_press_releases_mock.assert_called_once_with(
            self.session,
            limit=EXPECTED_MAX_PAGE_SIZE,
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
            params={"page": 1, "page_size": EXPECTED_MIN_PAGE_SIZE},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 1,
                "page_size": EXPECTED_MIN_PAGE_SIZE,
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
            limit=EXPECTED_MIN_PAGE_SIZE,
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
            params={
                "q": "  水質50%_/  ",
                "page": 2,
                "page_size": EXPECTED_MIN_PAGE_SIZE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"],
            {
                "page": 2,
                "page_size": EXPECTED_MIN_PAGE_SIZE,
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
            limit=EXPECTED_MIN_PAGE_SIZE,
            offset=EXPECTED_MIN_PAGE_SIZE,
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
                "page_size": EXPECTED_DEFAULT_PAGE_SIZE,
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
            limit=EXPECTED_DEFAULT_PAGE_SIZE,
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
                "page_size": EXPECTED_MIN_PAGE_SIZE,
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
            {"page_size": EXPECTED_MIN_PAGE_SIZE - 1},
            {"page_size": EXPECTED_MAX_PAGE_SIZE + 1},
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

    def test_error_responses_are_registered_in_openapi(self) -> None:
        """DBエラーと想定外例外の応答形式を成功・422のschemaと併記すること"""

        schema = app.openapi()
        responses = schema["paths"]["/press-releases"]["get"]["responses"]
        self.assertEqual(set(responses), {"200", "422", "500", "503"})

        for status_code, message in (
            ("500", "Internal server error"),
            ("503", "Service unavailable"),
        ):
            with self.subTest(status_code=status_code):
                content = responses[status_code]["content"]
                expected_types = (
                    {"application/json", "text/plain"}
                    if status_code == "500"
                    else {"application/json"}
                )
                self.assertEqual(set(content), expected_types)
                self.assertEqual(
                    content["application/json"]["schema"],
                    {"$ref": "#/components/schemas/ErrorResponse"},
                )
                self.assertEqual(
                    content["application/json"]["example"],
                    {"detail": message},
                )

        self.assertEqual(
            responses["500"]["content"]["text/plain"],
            {"schema": {"type": "string"}, "example": "Internal Server Error"},
        )
        error_schema = schema["components"]["schemas"]["ErrorResponse"]
        self.assertEqual(set(error_schema["properties"]), {"detail"})
        self.assertEqual(error_schema["required"], ["detail"])
        self.assertEqual(error_schema["properties"]["detail"]["type"], "string")
        for status_code, response_model in (
            ("200", "PressReleaseListResponse"),
            ("422", "HTTPValidationError"),
        ):
            with self.subTest(status_code=status_code):
                self.assertEqual(
                    responses[status_code]["content"]["application/json"]["schema"],
                    {"$ref": f"#/components/schemas/{response_model}"},
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
        self.assertEqual(
            page_size_parameter["schema"]["default"],
            EXPECTED_DEFAULT_PAGE_SIZE,
        )
        self.assertEqual(
            page_size_parameter["schema"]["minimum"],
            EXPECTED_MIN_PAGE_SIZE,
        )
        self.assertEqual(
            page_size_parameter["schema"]["maximum"],
            EXPECTED_MAX_PAGE_SIZE,
        )

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
