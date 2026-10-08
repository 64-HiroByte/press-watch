from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from typing import Any
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from httpx import Response
from pydantic import ValidationError
from sqlalchemy.exc import (
    DBAPIError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlalchemy.orm import Session
from starlette.types import Message, Receive, Scope, Send

from press_watch_api.main import app
from press_watch_api.models.fixed_category import FixedCategory


_INTERNAL_MARKER = "synthetic_fixed_category_internal_marker"
_PATH = "/fixed-categories"


class FixedCategoryListApiTest(unittest.TestCase):
    """実dependencyとMock Sessionで公開契約・終了処理・秘匿応答を確認"""

    def setUp(self) -> None:
        """Session factoryと取得結果を差し替え、実dependencyを通すHTTP環境を準備

        サーバー例外は通常の500応答として観測し、patchとclientは各テスト後に解除する。
        SQLの生成・実行結果はrepositoryテストとDB統合テストで確認する。
        """

        self.stderr = self.enterContext(redirect_stderr(io.StringIO()))
        self.stdout = self.enterContext(redirect_stdout(io.StringIO()))
        self.session = Mock(spec=Session)
        self.saved_categories = (
            FixedCategory(id=2003, slug="air", name="保存済み大気", display_order=10),
            FixedCategory(id=51, slug="soil", name="保存済み土壌", display_order=30),
        )
        self.session_factory = Mock(return_value=self.session)
        self.get_session_factory = self.enterContext(patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=self.session_factory,
        ))
        self.list_categories = self.enterContext(patch(
            "press_watch_api.routers.fixed_categories.list_fixed_categories",
            return_value=self.saved_categories,
        ))
        self.client = self.enterContext(TestClient(
            app, raise_server_exceptions=False,
        ))

    def _reset_request_state(self) -> None:
        """subTestの前要求の呼出し履歴・例外設定・診断を除去

        各段階の失敗を独立に検証するため、正常な取得結果へ戻してから例外を設定する。
        """

        for mock in (
            self.get_session_factory, self.session_factory,
            self.session, self.list_categories,
        ):
            mock.reset_mock(side_effect=True)
        self.list_categories.return_value = self.saved_categories
        for output in (self.stderr, self.stdout):
            output.seek(0)
            output.truncate(0)

    def _assert_session_closed(self) -> None:
        """実dependencyによるcloseの1回試行と明示commit・rollbackの不在を確認"""

        self.session.close.assert_called_once_with()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()

    def _assert_database_error(
        self, response: Response, status: int, event: str,
    ) -> None:
        """例外の入力値を含まない固定HTTP応答とアプリ診断を確認

        Args:
            response: 実dependencyと共通ハンドラを通したHTTP応答
            status: 失敗の種類に対して契約で定めたHTTPステータス
            event: 改行を含む期待するstderrの固定イベント列
        """

        self.assertEqual(response.status_code, status)
        self.assertEqual(
            response.headers["content-type"].partition(";")[0],
            "application/json",
        )
        self.assertEqual(response.json(), {
            "detail": "Service unavailable" if status == 503 else "Internal server error",
        })
        self.assertNotIn("retry-after", response.headers)
        self.assertEqual(self.stderr.getvalue(), event)
        self.assertEqual(self.stdout.getvalue(), "")

    def test_returns_only_saved_public_fields_in_repository_order(self) -> None:
        response = self.client.get(_PATH)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [
            {"slug": "air", "name": "保存済み大気", "display_order": 10},
            {"slug": "soil", "name": "保存済み土壌", "display_order": 30},
        ]})
        self.get_session_factory.assert_called_once_with()
        self.session_factory.assert_called_once_with()
        self.list_categories.assert_called_once_with(self.session)
        self._assert_session_closed()

    def test_empty_definitions_return_200_with_empty_items(self) -> None:
        self.list_categories.return_value = ()

        response = self.client.get(_PATH)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})
        self.list_categories.assert_called_once_with(self.session)
        self._assert_session_closed()

    def test_openapi_describes_public_response_and_error_content_types(self) -> None:
        """schemaの名称や参照形式に依存せず、公開項目・型・必須性を確認"""

        document = app.openapi()
        self.assertIn(_PATH, document["paths"])
        operation = document["paths"][_PATH]["get"]
        responses = operation["responses"]
        self.assertTrue({"200", "500", "503"}.issubset(responses))

        def resolve_schema(schema: dict[str, Any]) -> dict[str, Any]:
            """公開schemaを直接定義・components参照のどちらからでも取得"""

            if "$ref" in schema:
                return document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
            return schema

        response_schema = resolve_schema(
            responses["200"]["content"]["application/json"]["schema"]
        )
        self.assertEqual(set(response_schema["properties"]), {"items"})
        self.assertEqual(response_schema["required"], ["items"])
        items = response_schema["properties"]["items"]
        self.assertEqual(items["type"], "array")
        item_schema = resolve_schema(items["items"])
        self.assertEqual(set(item_schema["properties"]), {"slug", "name", "display_order"})
        self.assertEqual(set(item_schema["required"]), {"slug", "name", "display_order"})
        self.assertEqual(
            {key: value["type"] for key, value in item_schema["properties"].items()},
            {"slug": "string", "name": "string", "display_order": "integer"},
        )
        self.assertEqual(set(responses["500"]["content"]), {"application/json", "text/plain"})
        self.assertEqual(set(responses["503"]["content"]), {"application/json"})
        self.assertEqual(
            responses["500"]["content"]["text/plain"]["schema"]["type"], "string",
        )
        for status in ("500", "503"):
            error_content = responses[status]["content"]["application/json"]
            error_schema = resolve_schema(error_content["schema"])
            self.assertEqual(set(error_schema["properties"]), {"detail"})
            self.assertEqual(error_schema["required"], ["detail"])
            self.assertEqual(error_schema["properties"]["detail"]["type"], "string")
            self.assertEqual(error_content["example"], {
                "detail": "Service unavailable" if status == "503" else "Internal server error",
            })
        self.get_session_factory.assert_not_called()

    def test_database_failures_at_all_stages_keep_status_and_safe_diagnostics(self) -> None:
        cases = (
            ("pool_timeout", lambda: SQLAlchemyTimeoutError(_INTERNAL_MARKER), 503),
            ("invalidated_connection", lambda: DBAPIError(
                _INTERNAL_MARKER, {"value": _INTERNAL_MARKER},
                RuntimeError(_INTERNAL_MARKER), connection_invalidated=True,
            ), 503),
            ("connection_failure", lambda: OperationalError(
                _INTERNAL_MARKER, {"value": _INTERNAL_MARKER},
                RuntimeError(_INTERNAL_MARKER),
            ), 500),
            ("missing_table_or_permission", lambda: ProgrammingError(
                _INTERNAL_MARKER, {"value": _INTERNAL_MARKER},
                RuntimeError(_INTERNAL_MARKER),
            ), 500),
            ("other_sqlalchemy_error", lambda: SQLAlchemyError(_INTERNAL_MARKER), 500),
        )
        targets = {
            "factory": self.get_session_factory,
            "session": self.session_factory,
            "read": self.list_categories,
            "close": self.session.close,
        }
        for stage, target in targets.items():
            for name, create_error, status in cases:
                with self.subTest(stage=stage, error=name):
                    self._reset_request_state()
                    target.side_effect = create_error()

                    self._assert_database_error(
                        self.client.get(_PATH), status, "database_error\n",
                    )

                    self.get_session_factory.assert_called_once_with()
                    if stage == "factory":
                        self.session_factory.assert_not_called()
                    else:
                        self.session_factory.assert_called_once_with()
                    if stage in ("factory", "session"):
                        self.list_categories.assert_not_called()
                        self.session.close.assert_not_called()
                    else:
                        self.list_categories.assert_called_once_with(self.session)
                        self._assert_session_closed()

    def test_non_sqlalchemy_initialization_errors_are_safe_500_without_query(self) -> None:
        for stage, target, error in (
            ("factory", self.get_session_factory, RuntimeError(_INTERNAL_MARKER)),
            ("session", self.session_factory, ValueError(_INTERNAL_MARKER)),
        ):
            with self.subTest(stage=stage):
                self._reset_request_state()
                target.side_effect = error

                self._assert_database_error(
                    self.client.get(_PATH), 500, "database_initialization_failed\n",
                )

                self.list_categories.assert_not_called()
                self.session.close.assert_not_called()

    def test_non_sqlalchemy_close_error_replaces_success_with_safe_500(self) -> None:
        self.session.close.side_effect = RuntimeError(_INTERNAL_MARKER)

        self._assert_database_error(
            self.client.get(_PATH), 500, "database_cleanup_failed\n",
        )
        self.list_categories.assert_called_once_with(self.session)
        self._assert_session_closed()

    def test_processing_database_error_precedes_close_error(self) -> None:
        for query_error, close_error, status in (
            (SQLAlchemyError(_INTERNAL_MARKER), SQLAlchemyTimeoutError(_INTERNAL_MARKER), 500),
            (SQLAlchemyTimeoutError(_INTERNAL_MARKER), RuntimeError(_INTERNAL_MARKER), 503),
        ):
            with self.subTest(status=status):
                self._reset_request_state()
                self.list_categories.side_effect = query_error
                self.session.close.side_effect = close_error

                self._assert_database_error(
                    self.client.get(_PATH), status,
                    "database_cleanup_failed\ndatabase_error\n",
                )

                self.list_categories.assert_called_once_with(self.session)
                self._assert_session_closed()

    def test_unexpected_error_and_invalid_dto_keep_default_500(self) -> None:
        """HTTPの秘匿500と、元の想定外例外・DTO検証例外の維持を別要求で確認"""

        for failure in ("runtime", "dto"):
            for close_fails in (False, True):
                with self.subTest(failure=failure, close_fails=close_fails):
                    error = RuntimeError(_INTERNAL_MARKER)
                    self._reset_request_state()
                    self.list_categories.side_effect = error if failure == "runtime" else None
                    self.list_categories.return_value = ({
                        "slug": "air", "name": [_INTERNAL_MARKER], "display_order": 1,
                    },)
                    self.session.close.side_effect = (
                        SQLAlchemyError(_INTERNAL_MARKER) if close_fails else None
                    )

                    response = self.client.get(_PATH)

                    self.assertEqual(response.status_code, 500)
                    self.assertEqual(
                        response.headers["content-type"].partition(";")[0], "text/plain",
                    )
                    self.assertEqual(response.content, b"Internal Server Error")
                    self.assertEqual(
                        self.stderr.getvalue(), "database_cleanup_failed\n" if close_fails else "",
                    )
                    self.list_categories.assert_called_once_with(self.session)
                    self._assert_session_closed()

                    self.session.reset_mock()
                    self.list_categories.reset_mock()
                    with TestClient(app) as client:
                        raised = None
                        try:
                            client.get(_PATH)
                        except Exception as caught:
                            raised = caught
                    if failure == "runtime":
                        self.assertIs(raised, error)
                    else:
                        self.assertIsInstance(raised, ValidationError)
                    self.assertIsNone(raised.__context__)
                    self.list_categories.assert_called_once_with(self.session)
                    self._assert_session_closed()

    def test_session_closes_before_response_start(self) -> None:
        close_counts = []

        async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
            """実ASGIアプリの応答開始時にcloseの試行回数を観測し、送信を委任"""

            async def observed_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    close_counts.append(self.session.close.call_count)
                await send(message)
            await app(scope, receive, observed_send)

        with TestClient(observed_app) as client:
            response = client.get(_PATH)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(close_counts, [1])
        self._assert_session_closed()


if __name__ == "__main__":
    unittest.main()
