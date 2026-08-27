import os
import unittest
from collections.abc import Mapping
from unittest.mock import MagicMock, Mock, patch

from sqlalchemy import URL, make_url

from integration_tests import database
from integration_tests.database import (
    TEST_DATABASE_DRIVER,
    TEST_DATABASE_HOST,
    TEST_DATABASE_MAJOR_VERSION,
    TEST_DATABASE_NAME,
    TEST_DATABASE_PORT,
    TEST_DATABASE_URL_ENV,
    TEST_DATABASE_USER,
    UnsafeTestDatabaseError,
    prepare_test_database,
)


_TEST_DATABASE_PASSWORD = "test-value"


def _test_database_url(
    *,
    drivername: str = TEST_DATABASE_DRIVER,
    username: str = TEST_DATABASE_USER,
    password: str | None = _TEST_DATABASE_PASSWORD,
    host: str = TEST_DATABASE_HOST,
    port: int = TEST_DATABASE_PORT,
    database: str = TEST_DATABASE_NAME,
    query: Mapping[str, str] | None = None,
) -> URL:
    """安全条件の各項目を差し替えられるテスト用URLを生成"""

    return URL.create(
        drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=query or {},
    )


_VALID_TEST_DATABASE_URL = _test_database_url()


class TestDatabaseSafetyTest(unittest.TestCase):
    """テスト専用DB以外への接続を拒否する安全ガードのテスト"""

    def test_missing_test_database_url_is_rejected_before_connection(self) -> None:
        """専用環境変数がなければDBへ接続しないこと"""

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("integration_tests.database.create_engine") as create_engine,
            self.assertRaisesRegex(
                UnsafeTestDatabaseError,
                TEST_DATABASE_URL_ENV,
            ),
        ):
            prepare_test_database()

        create_engine.assert_not_called()

    def test_malformed_port_is_rejected_before_connection(self) -> None:
        """数値でないportを専用例外で拒否しDBへ接続しないこと"""

        malformed_url = (
            f"{TEST_DATABASE_DRIVER}://{TEST_DATABASE_USER}:"
            f"{_TEST_DATABASE_PASSWORD}@{TEST_DATABASE_HOST}:"
            f"not-a-port/{TEST_DATABASE_NAME}"
        )
        with (
            patch("integration_tests.database.create_engine") as create_engine,
            self.assertRaises(UnsafeTestDatabaseError) as raised,
        ):
            prepare_test_database(malformed_url)

        create_engine.assert_not_called()
        self.assertNotIn(_TEST_DATABASE_PASSWORD, str(raised.exception))
        self.assertNotIn(malformed_url, str(raised.exception))

    def test_non_test_database_targets_are_rejected_before_connection(self) -> None:
        """URLの許可条件が一つでも異なる場合はDBへ接続しないこと"""

        unsafe_urls = (
            ("driver", _test_database_url(drivername="postgresql")),
            ("host", _test_database_url(host="localhost")),
            ("port", _test_database_url(port=5_432)),
            ("database", _test_database_url(database="presswatch")),
            ("user", _test_database_url(username="presswatch")),
            ("password", _test_database_url(password=None)),
            ("remote host", _test_database_url(host="db.example")),
            (
                "query",
                _test_database_url(query={"sslmode": "require"}),
            ),
        )

        for field_name, unsafe_url in unsafe_urls:
            rendered_url = unsafe_url.render_as_string(hide_password=False)
            with self.subTest(field_name=field_name):
                with (
                    patch(
                        "integration_tests.database.create_engine"
                    ) as create_engine,
                    self.assertRaises(UnsafeTestDatabaseError) as raised,
                ):
                    prepare_test_database(rendered_url)

                create_engine.assert_not_called()
                self.assertNotIn(_TEST_DATABASE_PASSWORD, str(raised.exception))
                self.assertNotIn(rendered_url, str(raised.exception))

    def test_database_identity_mismatches_are_rejected(self) -> None:
        """実接続先の識別情報が一つでも異なれば拒否すること"""

        unsafe_identities = (
            (
                "database",
                database.TestDatabaseIdentity(
                    database="presswatch",
                    user=TEST_DATABASE_USER,
                    major_version=TEST_DATABASE_MAJOR_VERSION,
                ),
            ),
            (
                "user",
                database.TestDatabaseIdentity(
                    database=TEST_DATABASE_NAME,
                    user="presswatch",
                    major_version=TEST_DATABASE_MAJOR_VERSION,
                ),
            ),
            (
                "PostgreSQL major version",
                database.TestDatabaseIdentity(
                    database=TEST_DATABASE_NAME,
                    user=TEST_DATABASE_USER,
                    major_version=16,
                ),
            ),
        )

        for field_name, identity in unsafe_identities:
            with (
                self.subTest(field_name=field_name),
                self.assertRaisesRegex(
                    UnsafeTestDatabaseError,
                    field_name,
                ),
            ):
                database._assert_expected_identity(identity)

    def test_unmanaged_table_is_rejected_before_migration(self) -> None:
        """migration管理外テーブルがある実接続先を変更しないこと"""

        engine = MagicMock()
        connection = Mock()
        engine.connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.one.return_value = (
            TEST_DATABASE_NAME,
            TEST_DATABASE_USER,
            str(TEST_DATABASE_MAJOR_VERSION * 10_000),
            "public",
        )
        database_url = _VALID_TEST_DATABASE_URL.render_as_string(
            hide_password=False
        )
        with (
            patch(
                "integration_tests.database._create_test_engine",
                return_value=engine,
            ),
            patch("integration_tests.database.inspect") as inspect_database,
            patch(
                "integration_tests.database._run_migrations_from_base"
            ) as run_migrations,
            self.assertRaisesRegex(
                UnsafeTestDatabaseError,
                "migration管理外",
            ),
        ):
            inspect_database.return_value.get_table_names.return_value = [
                "alembic_version",
                "press_releases",
                "unmanaged_table",
            ]
            prepare_test_database(database_url)

        engine.dispose.assert_called_once_with()
        run_migrations.assert_not_called()

    def test_non_public_schema_is_rejected_before_migration(self) -> None:
        """実接続のcurrent schemaがpublicでなければ変更しないこと"""

        engine = MagicMock()
        connection = Mock()
        engine.connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.one.return_value = (
            TEST_DATABASE_NAME,
            TEST_DATABASE_USER,
            str(TEST_DATABASE_MAJOR_VERSION * 10_000),
            "unsafe_schema",
        )
        database_url = _VALID_TEST_DATABASE_URL.render_as_string(
            hide_password=False
        )
        with (
            patch(
                "integration_tests.database._create_test_engine",
                return_value=engine,
            ),
            patch("integration_tests.database.inspect") as inspect_database,
            patch(
                "integration_tests.database._run_migrations_from_base"
            ) as run_migrations,
            self.assertRaisesRegex(UnsafeTestDatabaseError, "schema"),
        ):
            inspect_database.return_value.get_table_names.return_value = []
            prepare_test_database(database_url)

        engine.dispose.assert_called_once_with()
        run_migrations.assert_not_called()

    def test_failed_database_identity_is_rejected_before_migration(self) -> None:
        """実接続先を確認できなければmigrationを開始しないこと"""

        database_url = _VALID_TEST_DATABASE_URL.render_as_string(
            hide_password=False
        )
        engine = Mock()
        with (
            patch(
                "integration_tests.database._create_test_engine",
                return_value=engine,
            ),
            patch(
                "integration_tests.database._read_verified_identity",
                side_effect=UnsafeTestDatabaseError(
                    "実接続先をテスト専用DBと確認できません。"
                ),
            ),
            patch(
                "integration_tests.database._run_migrations_from_base"
            ) as run_migrations,
            self.assertRaises(UnsafeTestDatabaseError),
        ):
            prepare_test_database(database_url)

        engine.dispose.assert_called_once_with()
        run_migrations.assert_not_called()

    def test_failed_database_identity_after_migration_disposes_engine(self) -> None:
        """migration後の実接続確認に失敗したEngineを破棄すること"""

        database_url = _VALID_TEST_DATABASE_URL.render_as_string(
            hide_password=False
        )
        verification_engine = Mock()
        migrated_engine = Mock()
        with (
            patch(
                "integration_tests.database._create_test_engine",
                side_effect=(verification_engine, migrated_engine),
            ),
            patch(
                "integration_tests.database._read_verified_identity",
                side_effect=(
                    Mock(),
                    UnsafeTestDatabaseError(
                        "migration後の実接続先を確認できません。"
                    ),
                ),
            ),
            patch(
                "integration_tests.database._run_migrations_from_base"
            ) as run_migrations,
            self.assertRaises(UnsafeTestDatabaseError),
        ):
            prepare_test_database(database_url)

        verification_engine.dispose.assert_called_once_with()
        migrated_engine.dispose.assert_called_once_with()
        run_migrations.assert_called_once()

    def test_engine_pins_host_address_and_public_schema(self) -> None:
        """Engine接続で実アドレスとcurrent schemaを固定すること"""

        with patch("integration_tests.database.create_engine") as create_engine:
            database._create_test_engine(_VALID_TEST_DATABASE_URL)

        self.assertEqual(
            create_engine.call_args.kwargs.get("connect_args"),
            {
                "hostaddr": TEST_DATABASE_HOST,
                "options": "-c search_path=public",
            },
        )

    def test_migrations_pin_host_address_and_public_schema(self) -> None:
        """Alembic接続で実アドレスとcurrent schemaを固定すること"""

        captured_database_urls: list[str] = []

        def capture_database_url(*_args: object) -> None:
            captured_database_urls.append(os.environ[database.DATABASE_URL_ENV])

        with (
            patch("integration_tests.database._build_alembic_config"),
            patch(
                "integration_tests.database.command.downgrade",
                side_effect=capture_database_url,
            ),
            patch(
                "integration_tests.database.command.upgrade",
                side_effect=capture_database_url,
            ),
        ):
            database._run_migrations_from_base(_VALID_TEST_DATABASE_URL)

        self.assertEqual(len(captured_database_urls), 2)
        for captured_database_url in captured_database_urls:
            secured_url = make_url(captured_database_url)
            self.assertEqual(
                secured_url.query.get("hostaddr"),
                TEST_DATABASE_HOST,
            )
            self.assertEqual(
                secured_url.query.get("options"),
                "-c search_path=public",
            )


if __name__ == "__main__":
    unittest.main()
