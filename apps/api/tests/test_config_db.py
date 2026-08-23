import importlib
import os
import unittest
from unittest.mock import patch

from press_watch_api.config import load_settings


TEST_DATABASE_URL = "postgresql+psycopg://presswatch@127.0.0.1:5432/presswatch"


class SettingsTest(unittest.TestCase):
    def test_load_settings_reads_database_url(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": TEST_DATABASE_URL}):
            settings = load_settings()

        self.assertEqual(settings.database_url, TEST_DATABASE_URL)

    def test_load_settings_requires_database_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is not set"):
                load_settings()


class DatabaseTest(unittest.TestCase):
    """DBリソースの遅延初期化に関するテスト"""

    def test_db_module_does_not_require_database_url_on_import(self) -> None:
        """DB moduleのimport時にはDATABASE_URLを要求しないこと"""

        with patch.dict(os.environ, {}, clear=True):
            db = importlib.import_module("press_watch_api.db")

            reloaded_db = importlib.reload(db)

        self.assertTrue(callable(reloaded_db.get_engine))
        self.assertTrue(callable(reloaded_db.get_session_factory))

    def test_get_engine_builds_engine_from_database_url(self) -> None:
        """Engine getterの初回呼び出しでDB設定を反映すること"""

        with patch.dict(os.environ, {"DATABASE_URL": TEST_DATABASE_URL}):
            db = importlib.import_module("press_watch_api.db")
            reloaded_db = importlib.reload(db)

            with patch.object(
                reloaded_db,
                "create_engine",
                wraps=reloaded_db.create_engine,
            ) as create_engine_mock:
                engine = reloaded_db.get_engine()

        self.addCleanup(engine.dispose)
        create_engine_mock.assert_called_once_with(
            TEST_DATABASE_URL,
            pool_pre_ping=True,
        )
        self.assertEqual(engine.url.drivername, "postgresql+psycopg")
        self.assertEqual(engine.url.host, "127.0.0.1")
        self.assertIs(reloaded_db.get_engine(), engine)

    def test_get_session_factory_reuses_engine(self) -> None:
        """Sessionファクトリを同じEngineへbindして再利用すること"""

        with patch.dict(os.environ, {"DATABASE_URL": TEST_DATABASE_URL}):
            db = importlib.import_module("press_watch_api.db")
            reloaded_db = importlib.reload(db)

            session_factory = reloaded_db.get_session_factory()
            engine = reloaded_db.get_engine()

        self.addCleanup(engine.dispose)
        self.assertIs(session_factory.kw["bind"], engine)
        self.assertFalse(session_factory.kw["autocommit"])
        self.assertFalse(session_factory.kw["autoflush"])
        self.assertIs(
            reloaded_db.get_session_factory(),
            session_factory,
        )

    def test_get_engine_requires_database_url_when_called(self) -> None:
        """DB設定不足はEngine getterの呼び出し時に検出すること"""

        with patch.dict(os.environ, {}, clear=True):
            db = importlib.import_module("press_watch_api.db")
            reloaded_db = importlib.reload(db)

            with self.assertRaisesRegex(
                RuntimeError,
                "DATABASE_URL is not set",
            ):
                reloaded_db.get_engine()


if __name__ == "__main__":
    unittest.main()
