from contextlib import redirect_stderr, redirect_stdout
from datetime import date
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
from press_watch_api.models.press_release import PressRelease


INTERNAL_MARKER = "synthetic_internal_marker"


class DatabaseErrorHttpTest(unittest.TestCase):
    """実dependencyとMock Sessionを通したDBエラー応答のテスト"""

    def setUp(self) -> None:
        """実dependencyを残してfactoryとrepositoryをMockへ差し替え、診断を捕捉

        factory・repositoryのpatchとstdout・stderrの差し替えは、
        addCleanupまたはenterContextで登録したcleanupが解除する。
        """

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
        self.memberships = self.enterContext(patch(
            "press_watch_api.routers.press_releases.list_press_release_fixed_categories",
            return_value={},
        ))

    def _set_failure(self, stage: str, error: Exception) -> None:
        """指定段階のMockだけを失敗させ、所属取得へ到達できる記事を用意

        factory取得・Session生成・件数・一覧・所属・closeのside_effectを設定し、
        指定段階以外の失敗設定は解除する。Mockの呼出し履歴はリセットしない。

        Args:
            stage: 失敗させる段階。factory、session、count、list、memberships、close
            error: 指定した段階のMockから送出する例外
        """

        self.get_session_factory.side_effect = error if stage == "factory" else None
        self.session_factory.side_effect = error if stage == "session" else None
        self.count.side_effect = error if stage == "count" else None
        self.count.return_value = 1
        self.list_releases.side_effect = error if stage == "list" else None
        self.list_releases.return_value = (PressRelease(
            id=1, title="合成記事", source_url="https://example.test/press/1",
            published_at=date(2026, 8, 31), source_categories=None,
        ),)
        self.memberships.side_effect = error if stage == "memberships" else None
        self.session.close.side_effect = error if stage == "close" else None

    def _get_response(
        self,
        *,
        params: dict[str, object] | None = None,
        raise_server_exceptions: bool = True,
    ) -> Response:
        """予期しない例外の本文をテスト結果へ出さずに一覧のHTTP応答を取得

        Args:
            params: 一覧APIのクエリ値。Noneならクエリを付けない
            raise_server_exceptions: TestClientでサーバー例外を再送出する設定
                Falseなら想定外例外のHTTP 500応答も検査可能

        Returns:
            HTTP応答。例外が外へ送出され応答を取得できない場合は、
            例外の詳細を含まないメッセージでテスト失敗
        """

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
        """DB障害の固定JSON・Content-TypeとRetry-Afterの不在を確認

        Args:
            response: DB障害を発生させた一覧APIのHTTP応答
            status_code: 期待する500または503。対応する固定メッセージも検査
        """

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

    def test_count_list_and_memberships_classify_database_errors(self) -> None:
        """各取得段階のDB例外を固定JSONの500・503へ分類し、Sessionを終了"""

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
        for operation in ("count", "list", "memberships"):
            for name, error, status_code in cases:
                with self.subTest(operation=operation, error=name):
                    self.session.close.reset_mock()
                    self._set_failure(operation, error)

                    response = self._get_response()

                    self._assert_error_response(response, status_code)
                    self.session.close.assert_called_once_with()
                    self.session.commit.assert_not_called()
                    self.session.rollback.assert_not_called()

    def test_fixed_category_preserves_database_errors_and_safe_diagnostics(
        self,
    ) -> None:
        """カテゴリ指定時もDB障害の応答と詳細を含めない診断を維持"""

        params = {"fixed_category": ["air", "soil"], "q": "climate"}
        for stage in ("factory", "session", "count", "list", "memberships", "close"):
            for error, status in (
                (SQLAlchemyTimeoutError(INTERNAL_MARKER), 503),
                (ProgrammingError(
                    INTERNAL_MARKER, {}, RuntimeError(INTERNAL_MARKER)
                ), 500),
            ):
                with self.subTest(stage=stage, status=status):
                    self.session.reset_mock()
                    self.stderr.seek(0)
                    self.stderr.truncate(0)
                    self._set_failure(stage, error)

                    response = self._get_response(params=params)

                    self._assert_error_response(response, status)
                    self.assertEqual(
                        self.stderr.getvalue(), "database_error\n"
                    )
                    self.assertEqual(self.stdout.getvalue(), "")
                    self.session.commit.assert_not_called()
                    self.session.rollback.assert_not_called()
                    if stage in ("count", "list", "memberships", "close"):
                        self.session.close.assert_called_once_with()

    def test_fixed_category_initialization_error_precedes_validation(
        self,
    ) -> None:
        """不正カテゴリの入力検証よりDB初期化失敗の応答が優先"""

        self.get_session_factory.side_effect = RuntimeError(INTERNAL_MARKER)

        response = self._get_response(params={"fixed_category": "Air"})

        self._assert_error_response(response, 500)
        self.count.assert_not_called()
        self.list_releases.assert_not_called()

    def test_initialization_failures_return_safe_errors_without_queries(self) -> None:
        """factory取得・Session生成の失敗を安全な500・503へ変換し、照会を省略"""

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
        """ページ・日付が不正でも初期化失敗の500を優先し、照会とcloseを省略"""

        self.get_session_factory.side_effect = RuntimeError(INTERNAL_MARKER)

        for params in (
            {"page": 0}, {"published_from": "2026-1-02"},
            {"published_to": "2026-02-29"},
            {"published_from": "2026-01-04", "published_to": "2026-01-02"},
        ):
            with self.subTest(params=params):
                response = self._get_response(params=params)
                self._assert_error_response(response, 500)
                self.count.assert_not_called()
                self.list_releases.assert_not_called()
                self.session.close.assert_not_called()

    def test_session_closes_before_response_start(self) -> None:
        """実dependencyが正常応答の送信開始前にSessionを1回closeすること"""

        close_counts = []

        async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
            """応答開始時のclose呼出し回数を観測するASGIラッパー

            Args:
                scope: TestClientから渡されるリクエスト情報
                receive: アプリが要求メッセージを受け取るための関数
                send: 観測後の応答メッセージを転送する関数
            """

            async def observed_send(message: Message) -> None:
                """応答開始を観測し、元の送信先へメッセージを転送

                Args:
                    message: アプリから送られるASGI応答メッセージ
                """

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
        """closeだけが失敗した場合は例外の種類に応じた固定JSONの500・503を返すこと"""

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
        """件数・所属取得のDB例外をclose失敗より優先し、両失敗を固定診断で区別"""

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
        for operation in ("count", "memberships"):
            for name, query_error, close_error, status_code in cases:
                with self.subTest(operation=operation, error=name):
                    self.stderr.seek(0)
                    self.stderr.truncate(0)
                    self.session.close.reset_mock()
                    self._set_failure(operation, query_error)
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
        """close失敗でも元の想定外例外を伝え、終了失敗の例外連鎖を追加しないこと"""

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
        """入力検証とclose失敗が重なっても元の422と本文を保持し、照会を省略"""

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
        """DB処理・初期化・終了の失敗を固定イベントだけで診断し、内部値を出力しないこと"""

        query_error = DBAPIError(
            INTERNAL_MARKER,
            {"value": INTERNAL_MARKER},
            RuntimeError(INTERNAL_MARKER),
            connection_invalidated=True,
        )
        cases = (
            ("count", query_error, 503, "database_error\n"),
            ("list", query_error, 503, "database_error\n"),
            ("memberships", query_error, 503, "database_error\n"),
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
        """診断のwrite・flushが失敗しても元のDBエラー応答を保持し、出力を再試行しないこと"""

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
        """closeと診断出力が失敗しても元の想定外例外を保持し、例外連鎖を追加しないこと"""

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
