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
    def test_db_module_builds_engine_from_database_url(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": TEST_DATABASE_URL}):
            import press_watch_api.db as db

            reloaded_db = importlib.reload(db)

        self.assertEqual(reloaded_db.engine.url.drivername, "postgresql+psycopg")
        self.assertEqual(reloaded_db.engine.url.host, "127.0.0.1")
        self.assertEqual(reloaded_db.SessionLocal.kw["bind"], reloaded_db.engine)


if __name__ == "__main__":
    unittest.main()
