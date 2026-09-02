from contextlib import redirect_stderr
from datetime import date
import io
import unittest
from unittest.mock import Mock, call, patch

from fastapi.testclient import TestClient
from httpx import Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from press_watch_api.main import app


INTERNAL_MARKER = "synthetic_regression_internal_marker"


class HttpErrorRegressionTest(unittest.TestCase):
    """DBエラー処理の追加後も既存のHTTP契約を維持すること"""

    def setUp(self) -> None:
        self.stderr = self.enterContext(redirect_stderr(io.StringIO()))
        self.session = Mock(spec=Session)
        self.session_factory = Mock(return_value=self.session)
        self.get_session_factory = self.enterContext(
            patch(
                "press_watch_api.dependencies.get_session_factory",
                return_value=self.session_factory,
            )
        )
        self.count = self.enterContext(
            patch(
                "press_watch_api.routers.press_releases.count_press_releases",
                return_value=0,
            )
        )
        self.list_releases = self.enterContext(
            patch(
                "press_watch_api.routers.press_releases.list_press_releases",
                return_value=(),
            )
        )

    def _request(
        self,
        path: str = "/press-releases",
        *,
        method: str = "GET",
        params: dict[str, str | int] | None = None,
        raise_server_exceptions: bool = True,
    ) -> Response:
        response = None
        try:
            response = TestClient(
                app,
                raise_server_exceptions=raise_server_exceptions,
            ).request(method, path, params=params)
        except Exception:
            pass
        if response is None:
            self.fail("HTTP応答の取得中に予期しない例外が外へ漏れた")
        return response

    def _json(self, response: Response) -> dict[str, object]:
        self.assertTrue(
            response.headers.get("content-type", "").partition(";")[0]
            == "application/json",
            "既存のJSON応答形式を維持すること",
        )
        payload = None
        try:
            payload = response.json()
        except ValueError:
            pass
        if not isinstance(payload, dict):
            self.fail("応答をJSONオブジェクトとして取得できること")
        return payload

    def _assert_session_closed(self) -> None:
        self.assertTrue(
            self.session.close.call_count == 1
            and self.session.close.call_args == call(),
            "Sessionのcloseを引数なしで1回試みること",
        )
        self.assertTrue(
            self.session.commit.call_count == 0
            and self.session.rollback.call_count == 0,
            "読み取りAPIでcommitや明示rollbackを呼ばないこと",
        )

    def test_unexpected_errors_keep_default_500_and_propagate(self) -> None:
        """想定外例外と実DTO検証失敗をDB障害へ変換しないこと"""

        runtime_error = RuntimeError(INTERNAL_MARKER)
        invalid_release = {
            "title": [INTERNAL_MARKER],
            "source_url": "https://example.test/press/1",
            "published_at": date(2026, 8, 31),
            "source_categories": None,
        }
        for failure in ("runtime", "dto"):
            for close_fails in (False, True):
                with self.subTest(failure=failure, close_fails=close_fails):
                    self.count.side_effect = (
                        runtime_error if failure == "runtime" else None
                    )
                    self.count.return_value = 1
                    self.list_releases.return_value = (invalid_release,)
                    self.session.close.side_effect = (
                        SQLAlchemyError(INTERNAL_MARKER) if close_fails else None
                    )
                    self.session.reset_mock()
                    self.stderr.seek(0)
                    self.stderr.truncate(0)

                    response = self._request(raise_server_exceptions=False)

                    self.assertTrue(response.status_code == 500, "既定の500を返すこと")
                    self.assertTrue(
                        response.headers.get("content-type", "").partition(";")[0]
                        == "text/plain",
                        "想定外例外の500をDBエラーのJSONへ変換しないこと",
                    )
                    self.assertTrue(
                        response.content == b"Internal Server Error",
                        "既定の500本文へ元の例外やDTO入力値を含めないこと",
                    )
                    self._assert_session_closed()
                    self.assertTrue(
                        self.stderr.getvalue()
                        == ("database_cleanup_failed\n" if close_fails else ""),
                        "想定外例外へDB障害の診断を追加しないこと",
                    )

                    self.session.reset_mock()
                    raised_error = None
                    try:
                        TestClient(app).get("/press-releases")
                    except Exception as exc:
                        raised_error = exc

                    if failure == "runtime":
                        self.assertTrue(
                            raised_error is runtime_error,
                            "既定のTestClientでは元の想定外例外を伝えること",
                        )
                    else:
                        self.assertTrue(
                            isinstance(raised_error, ValidationError),
                            "DTOの実際の検証エラーをそのまま伝えること",
                        )
                        validation_errors = raised_error.errors()
                        self.assertTrue(
                            len(validation_errors) == 1
                            and validation_errors[0]["loc"] == ("title",)
                            and validation_errors[0]["type"] == "string_type",
                            "一覧DTOのtitle検証による失敗であること",
                        )
                    self.assertTrue(
                        raised_error.__context__ is None,
                        "元の例外へclose失敗の例外連鎖を追加しないこと",
                    )
                    self._assert_session_closed()

    def test_validation_shape_survives_close_failure(self) -> None:
        """各入力条件の422の位置と種別をclose失敗時も維持すること"""

        cases = (
            ("page_lower", {"page": 0}, "page", "greater_than_equal"),
            ("page_upper", {"page": 10_001}, "page", "less_than_equal"),
            ("size_lower", {"page_size": 9}, "page_size", "greater_than_equal"),
            ("size_upper", {"page_size": 101}, "page_size", "less_than_equal"),
            ("query_length", {"q": "x" * 101}, "q", "string_too_long"),
            ("query_nul", {"q": INTERNAL_MARKER + "\x00"}, "q", "string_pattern_mismatch"),
        )
        for name, params, field, error_type in cases:
            for close_fails in (False, True):
                with self.subTest(condition=name, close_fails=close_fails):
                    self.session.reset_mock()
                    self.session.close.side_effect = (
                        SQLAlchemyError(INTERNAL_MARKER) if close_fails else None
                    )

                    response = self._request(params=params)

                    self.assertTrue(response.status_code == 422, "不正な入力には422を返すこと")
                    payload = self._json(response)
                    self.assertTrue(set(payload) == {"detail"}, "422の外側の形式を維持すること")
                    detail = payload["detail"]
                    self.assertTrue(
                        isinstance(detail, list) and len(detail) == 1,
                        "422のdetailは検証エラー1件の配列であること",
                    )
                    self.assertTrue(
                        isinstance(detail[0], dict)
                        and detail[0].get("loc") == ["query", field]
                        and detail[0].get("type") == error_type,
                        "422のエラー位置と種別を既存契約から変えないこと",
                    )
                    self.assertTrue(
                        self.count.call_count == 0 and self.list_releases.call_count == 0,
                        "入力検証で拒否したリクエストではrepositoryを呼ばないこと",
                    )
                    self._assert_session_closed()

    def test_liveness_and_http_errors_do_not_initialize_database(self) -> None:
        self.get_session_factory.side_effect = RuntimeError(INTERNAL_MARKER)
        cases = (
            ("GET", "/", 200, {"service": "press-watch-api", "status": "ready"}),
            ("GET", "/health", 200, {"status": "ok"}),
            ("GET", "/not-found", 404, {"detail": "Not Found"}),
            ("POST", "/press-releases", 405, {"detail": "Method Not Allowed"}),
        )
        for method, path, status_code, expected in cases:
            with self.subTest(method=method, path=path):
                response = self._request(path, method=method)

                self.assertTrue(
                    response.status_code == status_code,
                    "livenessと既存HTTPエラーのステータスを維持すること",
                )
                self.assertTrue(self._json(response) == expected, "既存の応答本文を維持すること")
                self.assertTrue(
                    self.get_session_factory.call_count == 0
                    and self.session_factory.call_count == 0,
                    "livenessと404・405ではDB初期化を行わないこと",
                )
                self.assertTrue(
                    self.session.close.call_count == 0
                    and self.count.call_count == 0
                    and self.list_releases.call_count == 0,
                    "DB非依存の応答でSessionやrepositoryを使わないこと",
                )


if __name__ == "__main__":
    unittest.main()
