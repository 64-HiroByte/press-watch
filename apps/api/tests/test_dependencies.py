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


if __name__ == "__main__":
    unittest.main()
