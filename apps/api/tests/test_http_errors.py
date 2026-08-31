from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from httpx import Response
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


INTERNAL_MARKER = "synthetic_internal_marker"


class DatabaseErrorHttpTest(unittest.TestCase):
    """実dependencyとMock Sessionを通したDBエラー応答のテスト"""

    def setUp(self) -> None:
        self.stderr = self.enterContext(redirect_stderr(io.StringIO()))
        self.stdout = self.enterContext(redirect_stdout(io.StringIO()))
        self.session = Mock(spec=Session)
        self.session_factory = Mock(return_value=self.session)
        factory_patch = patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=self.session_factory,
        )
        self.get_session_factory = factory_patch.start()
        self.addCleanup(factory_patch.stop)
        count_patch = patch(
            "press_watch_api.routers.press_releases.count_press_releases",
            return_value=0,
        )
        self.count = count_patch.start()
        self.addCleanup(count_patch.stop)
        list_patch = patch(
            "press_watch_api.routers.press_releases.list_press_releases",
            return_value=(),
        )
        self.list_releases = list_patch.start()
        self.addCleanup(list_patch.stop)

    def _set_failure(self, stage: str, error: Exception) -> None:
        self.get_session_factory.side_effect = error if stage == "factory" else None
        self.session_factory.side_effect = error if stage == "session" else None
        self.count.side_effect = error if stage == "count" else None
        self.count.return_value = 1
        self.list_releases.side_effect = error if stage == "list" else None
        self.session.close.side_effect = error if stage == "close" else None

    def _get_response(
        self,
        *,
        params: dict[str, object] | None = None,
        raise_server_exceptions: bool = True,
    ) -> Response:
        """予期しない例外の本文をテスト結果へ出さずにHTTP応答を取得"""

        response = None
        try:
            response = TestClient(
                app,
                raise_server_exceptions=raise_server_exceptions,
            ).get("/press-releases", params=params)
        except Exception:
            pass
        if response is None:
            self.fail("HTTP応答の取得中に例外が外へ漏れた")
        return response

    def _assert_error_response(
        self,
        response: Response,
        status_code: int,
    ) -> None:
        self.assertTrue(
            response.status_code == status_code,
            "DBエラーのHTTPステータスが契約と一致すること",
        )
        self.assertTrue(
            response.headers.get("content-type", "").partition(";")[0]
            == "application/json",
            "DBエラーはJSONとして返すこと",
        )
        payload = None
        try:
            payload = response.json()
        except ValueError:
            pass
        message = (
            "Service unavailable"
            if status_code == 503
            else "Internal server error"
        )
        self.assertTrue(
            payload == {"detail": message},
            "DBエラーのJSONには固定メッセージだけを含めること",
        )
        self.assertTrue(
            "retry-after" not in response.headers,
            "復旧時刻を推測したRetry-Afterを付けないこと",
        )

    def test_count_and_list_classify_database_errors(self) -> None:
        cases = (
            ("pool_timeout", SQLAlchemyTimeoutError(INTERNAL_MARKER), 503),
            (
                "invalidated_connection",
                DBAPIError(
                    INTERNAL_MARKER,
                    {"value": INTERNAL_MARKER},
                    RuntimeError(INTERNAL_MARKER),
                    connection_invalidated=True,
                ),
                503,
            ),
            (
                "operational_error",
                OperationalError(
                    INTERNAL_MARKER,
                    {"value": INTERNAL_MARKER},
                    RuntimeError(INTERNAL_MARKER),
                ),
                500,
            ),
            (
                "programming_error",
                ProgrammingError(
                    INTERNAL_MARKER,
                    {"value": INTERNAL_MARKER},
                    RuntimeError(INTERNAL_MARKER),
                ),
                500,
            ),
            ("other_sqlalchemy_error", SQLAlchemyError(INTERNAL_MARKER), 500),
        )
        for operation in ("count", "list"):
            for name, error, status_code in cases:
                with self.subTest(operation=operation, error=name):
                    self.session.close.reset_mock()
                    self.count.side_effect = error if operation == "count" else None
                    self.count.return_value = 1
                    self.list_releases.side_effect = (
                        error if operation == "list" else None
                    )

                    response = self._get_response()

                    self._assert_error_response(response, status_code)
                    self.session.close.assert_called_once_with()
                    self.session.commit.assert_not_called()
                    self.session.rollback.assert_not_called()

    def test_initialization_failures_return_safe_errors_without_queries(self) -> None:
        cases = (
            ("configuration", RuntimeError(INTERNAL_MARKER), 500),
            ("invalid_configuration", ValueError(INTERNAL_MARKER), 500),
            ("unexpected_initialization", TypeError(INTERNAL_MARKER), 500),
            ("sqlalchemy", SQLAlchemyError(INTERNAL_MARKER), 500),
            ("pool_timeout", SQLAlchemyTimeoutError(INTERNAL_MARKER), 503),
        )
        for stage in ("factory", "session"):
            for name, error, status_code in cases:
                with self.subTest(stage=stage, error=name):
                    self.get_session_factory.side_effect = (
                        error if stage == "factory" else None
                    )
                    self.session_factory.side_effect = (
                        error if stage == "session" else None
                    )

                    response = self._get_response()

                    self._assert_error_response(response, status_code)
                    self.count.assert_not_called()
                    self.list_releases.assert_not_called()
                    self.session.close.assert_not_called()

    def test_initialization_failure_precedes_invalid_query(self) -> None:
        self.get_session_factory.side_effect = RuntimeError(INTERNAL_MARKER)

        response = self._get_response(params={"page": 0})

        self._assert_error_response(response, 500)
        self.count.assert_not_called()

    def test_session_closes_before_response_start(self) -> None:
        close_counts = []

        async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
            async def observed_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    close_counts.append(self.session.close.call_count)
                await send(message)

            await app(scope, receive, observed_send)

        response = TestClient(observed_app).get("/press-releases")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(close_counts, [1])
        self.session.close.assert_called_once_with()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()

    def test_close_failure_returns_safe_error(self) -> None:
        cases = (
            ("sqlalchemy", SQLAlchemyError(INTERNAL_MARKER), 500),
            ("pool_timeout", SQLAlchemyTimeoutError(INTERNAL_MARKER), 503),
            (
                "invalidated_connection",
                DBAPIError(
                    INTERNAL_MARKER,
                    {"value": INTERNAL_MARKER},
                    RuntimeError(INTERNAL_MARKER),
                    connection_invalidated=True,
                ),
                503,
            ),
            ("other_close_error", RuntimeError(INTERNAL_MARKER), 500),
        )
        for name, error, status_code in cases:
            with self.subTest(error=name):
                self.session.close.reset_mock()
                self.session.close.side_effect = error

                response = self._get_response()

                self._assert_error_response(response, status_code)
                self.session.close.assert_called_once_with()
                self.session.commit.assert_not_called()
                self.session.rollback.assert_not_called()

    def test_query_error_takes_precedence_over_close_error(self) -> None:
        cases = (
            (
                "query_500",
                SQLAlchemyError(INTERNAL_MARKER),
                SQLAlchemyTimeoutError(INTERNAL_MARKER),
                500,
            ),
            (
                "query_503",
                SQLAlchemyTimeoutError(INTERNAL_MARKER),
                RuntimeError(INTERNAL_MARKER),
                503,
            ),
        )
        for name, query_error, close_error, status_code in cases:
            with self.subTest(error=name):
                self.stderr.seek(0)
                self.stderr.truncate(0)
                self.session.close.reset_mock()
                self.count.side_effect = query_error
                self.session.close.side_effect = close_error

                response = self._get_response()

                self._assert_error_response(response, status_code)
                self.session.close.assert_called_once_with()
                self.session.commit.assert_not_called()
                self.session.rollback.assert_not_called()
                self.assertTrue(
                    self.stderr.getvalue()
                    == "database_cleanup_failed\ndatabase_error\n",
                    "元のDBエラーと終了失敗を固定診断で区別すること",
                )

    def test_unexpected_query_error_is_not_replaced_by_close_error(self) -> None:
        query_error = RuntimeError(INTERNAL_MARKER)
        self.count.side_effect = query_error
        self.session.close.side_effect = SQLAlchemyTimeoutError(INTERNAL_MARKER)

        raised_error = None
        try:
            TestClient(app).get("/press-releases")
        except Exception as exc:
            raised_error = exc

        self.assertTrue(
            raised_error is query_error,
            "想定外の処理例外はDB障害へ変換せず同一の例外を伝えること",
        )
        self.session.close.assert_called_once_with()
        self.assertTrue(
            query_error.__context__ is None,
            "元の例外へclose失敗の例外連鎖を追加しないこと",
        )
        self.assertTrue(
            self.stderr.getvalue() == "database_cleanup_failed\n",
            "想定外例外へDBエラーの診断を付けないこと",
        )

    def test_validation_error_takes_precedence_over_close_error(self) -> None:
        baseline = self._get_response(params={"page": 0})
        self.session.close.reset_mock()
        self.session.close.side_effect = SQLAlchemyTimeoutError(INTERNAL_MARKER)

        response = self._get_response(params={"page": 0})

        self.assertTrue(baseline.status_code == 422, "入力範囲外は422にすること")
        self.assertTrue(response.status_code == 422, "close失敗でも元の422を返すこと")
        self.assertTrue(
            response.content == baseline.content,
            "close失敗でも元の入力検証応答を変更しないこと",
        )
        self.count.assert_not_called()
        self.list_releases.assert_not_called()
        self.session.close.assert_called_once_with()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()

    def test_diagnostics_contain_only_fixed_events(self) -> None:
        query_error = DBAPIError(
            INTERNAL_MARKER,
            {"value": INTERNAL_MARKER},
            RuntimeError(INTERNAL_MARKER),
            connection_invalidated=True,
        )
        cases = (
            ("count", query_error, 503, "database_error\n"),
            ("list", query_error, 503, "database_error\n"),
            (
                "factory",
                RuntimeError(INTERNAL_MARKER),
                500,
                "database_initialization_failed\n",
            ),
            (
                "session",
                ValueError(INTERNAL_MARKER),
                500,
                "database_initialization_failed\n",
            ),
            (
                "close",
                RuntimeError(INTERNAL_MARKER),
                500,
                "database_cleanup_failed\n",
            ),
        )
        for stage, error, status_code, expected_event in cases:
            with self.subTest(stage=stage):
                self.stderr.seek(0)
                self.stderr.truncate(0)
                self._set_failure(stage, error)

                response = self._get_response(params={"q": INTERNAL_MARKER})

                self._assert_error_response(response, status_code)
                self.assertTrue(
                    self.stderr.getvalue() == expected_event,
                    "stderrには元の例外や入力値を含まない固定診断だけを出すこと",
                )
                self.assertTrue(
                    self.stdout.getvalue() == "",
                    "診断をstdoutへ出さないこと",
                )

    def test_diagnostic_write_and_flush_failures_do_not_change_response(self) -> None:
        for stage in ("count", "factory", "close"):
            for operation in ("write", "flush"):
                with self.subTest(stage=stage, operation=operation):
                    error = (
                        SQLAlchemyTimeoutError(INTERNAL_MARKER)
                        if stage == "count"
                        else RuntimeError(INTERNAL_MARKER)
                    )
                    self._set_failure(stage, error)
                    output = Mock()
                    getattr(output, operation).side_effect = OSError(INTERNAL_MARKER)

                    with patch("sys.stderr", output):
                        response = self._get_response()

                    self._assert_error_response(
                        response,
                        503 if stage == "count" else 500,
                    )
                    self.assertTrue(
                        output.write.call_count == 1,
                        "診断の書込は1回だけ試みること",
                    )
                    self.assertTrue(
                        output.flush.call_count == (0 if operation == "write" else 1),
                        "診断の出力失敗を再試行しないこと",
                    )
                    self.assertTrue(
                        self.stderr.getvalue() == "",
                        "診断出力の失敗時に別の例外診断を出さないこと",
                    )

    def test_diagnostic_failure_preserves_original_query_exception(self) -> None:
        error = RuntimeError(INTERNAL_MARKER)
        self.count.side_effect = error
        self.session.close.side_effect = SQLAlchemyError(INTERNAL_MARKER)
        output = Mock()
        output.write.side_effect = OSError(INTERNAL_MARKER)

        raised_error = None
        with patch("sys.stderr", output):
            try:
                TestClient(app).get("/press-releases")
            except Exception as exc:
                raised_error = exc

        self.assertTrue(raised_error is error, "診断失敗でも元の処理例外を維持すること")
        self.assertTrue(error.__context__ is None, "診断失敗の例外連鎖を追加しないこと")
        self.assertTrue(output.write.call_count == 1, "終了失敗の診断を1回だけ試みること")


if __name__ == "__main__":
    unittest.main()
