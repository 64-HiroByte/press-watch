import importlib
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from press_watch_api.config import load_settings
from press_watch_api.main import app


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
        """DB URLと接続上限を反映した共有Engineを初回だけ生成"""

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
        self.assertEqual(create_engine_mock.call_count, 1)
        self.assertEqual(create_engine_mock.call_args.args, (TEST_DATABASE_URL,))
        self.assertTrue(create_engine_mock.call_args.kwargs["pool_pre_ping"])
        self.assertEqual(create_engine_mock.call_args.kwargs.get("max_overflow"), 0)
        self.assertEqual(engine.url.drivername, "postgresql+psycopg")
        self.assertEqual(engine.url.host, "127.0.0.1")
        self.assertEqual(engine.pool.size(), 2)
        self.assertEqual(engine.pool.timeout(), 5)
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


class ApiCertificateTest(unittest.TestCase):
    """API起動時のlibpq用CA指定に関するテスト"""

    def test_api_uses_owner_only_ca_file_until_shutdown(self) -> None:
        """CA環境変数を所有者専用ファイルに保存し、終了時に元の設定へ復元"""

        certificate = "dummy certificate for the file lifecycle test\n"
        with patch.dict(
            os.environ,
            {"PRESSWATCH_DB_CA_CERT": certificate, "PGSSLROOTCERT": "original.crt"},
            clear=True,
        ):
            with TestClient(app) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                ca_path = Path(os.environ["PGSSLROOTCERT"])
                self.assertTrue(ca_path.is_absolute())
                self.assertEqual(ca_path.read_text(encoding="utf-8"), certificate)
                self.assertEqual(stat.S_IMODE(ca_path.stat().st_mode), 0o600)

            self.assertFalse(ca_path.exists())
            self.assertEqual(os.environ["PGSSLROOTCERT"], "original.crt")


if __name__ == "__main__":
    unittest.main()
