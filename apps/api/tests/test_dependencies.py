from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session


class DatabaseSessionDependencyTest(unittest.TestCase):
    """DB Session dependencyのテスト"""

    def test_get_db_session_creates_and_closes_session(self) -> None:
        """正常終了時にリクエスト用Sessionを生成して閉じること"""

        session = Mock(spec=Session)
        session_factory = Mock(return_value=session)

        with patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=session_factory,
        ):
            dependency = get_db_session()

            yielded_session = next(dependency)
            dependency.close()

        self.assertIs(yielded_session, session)
        session_factory.assert_called_once_with()
        session.close.assert_called_once_with()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_get_db_session_closes_session_after_exception(self) -> None:
        """path operationの例外終了時にもSessionを閉じること"""

        session = Mock(spec=Session)
        session_factory = Mock(return_value=session)

        with patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=session_factory,
        ):
            dependency = get_db_session()
            next(dependency)

            with self.assertRaisesRegex(RuntimeError, "route failed"):
                dependency.throw(RuntimeError("route failed"))

        session.close.assert_called_once_with()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_base_exception_is_not_converted_to_database_error(self) -> None:
        """dependency単体でBaseExceptionを変換せず、既存のfinallyを維持すること"""

        class StopRequest(BaseException):
            pass

        for stage in ("factory", "session", "body", "close", "body_and_close"):
            with self.subTest(stage=stage):
                error = StopRequest("synthetic_stop_marker")
                session = Mock(spec=Session)
                session_factory = Mock(return_value=session)
                if stage == "session":
                    session_factory.side_effect = error
                if stage == "close":
                    session.close.side_effect = error
                elif stage == "body_and_close":
                    session.close.side_effect = RuntimeError("synthetic_close_marker")

                raised_error = None
                with patch(
                    "press_watch_api.dependencies.get_session_factory",
                    return_value=session_factory,
                    side_effect=error if stage == "factory" else None,
                ), redirect_stderr(io.StringIO()):
                    dependency = get_db_session()
                    try:
                        next(dependency)
                        if stage in ("body", "body_and_close"):
                            dependency.throw(error)
                        else:
                            next(dependency)
                    except (StopRequest, Exception) as exc:
                        raised_error = exc

                self.assertTrue(
                    raised_error is error,
                    "BaseExceptionを通常のDBエラーや終了失敗で置き換えないこと",
                )
                self.assertTrue(
                    session.close.call_count
                    == (0 if stage in ("factory", "session") else 1),
                    "Session生成後のfinallyによる終了処理を省略しないこと",
                )
                session.commit.assert_not_called()
                session.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
