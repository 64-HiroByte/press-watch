"""CAの配置・復元とジョブ接続設定の検証"""

import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch
from sqlalchemy.engine import make_url

from press_watch_api.db_tls import certificate_environment
from press_watch_api.commands import run_fetch_job as job


class CertificateEnvironmentTest(unittest.TestCase):
    """共有CA準備の既存API互換"""

    def test_certificate_is_private_and_previous_path_is_restored(self) -> None:
        """一時CAは所有者専用で、例外時も削除と設定復元を行うこと"""
        with patch.dict(
            os.environ,
            {'PRESSWATCH_DB_CA_CERT': 'test-ca', 'PGSSLROOTCERT': 'before'},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                with certificate_environment():
                    path = Path(os.environ['PGSSLROOTCERT'])
                    self.assertEqual(path.read_text(), 'test-ca')
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    raise RuntimeError('synthetic')
            self.assertFalse(path.exists())
            self.assertEqual(os.environ['PGSSLROOTCERT'], 'before')

    def test_optional_absent_and_empty_rejected(self) -> None:
        """APIではCA未設定を許容し、明示的な空値を拒否すること"""
        with patch.dict(os.environ, {}, clear=True):
            with certificate_environment():
                self.assertNotIn('PGSSLROOTCERT', os.environ)
            os.environ['PRESSWATCH_DB_CA_CERT'] = '  '
            with self.assertRaises(RuntimeError):
                with certificate_environment():
                    self.fail('empty CA accepted')


class JobConnectionTest(unittest.TestCase):
    """本番監督入口でTLSの弱い指定を許容しないこと"""

    def test_invalid_connection_settings_are_rejected(self) -> None:
        """ドライバー、接続先、認証情報、TLSの不適切な指定を拒否すること"""
        invalid_urls = [
            'postgresql+psycopg2://writer:example@db.example/postgres?sslmode=verify-full',
            'postgresql://writer:example@db.example/postgres?sslmode=require',
            'postgresql://writer:example@db.example/postgres?sslmode=verify-full&sslrootcert=other',
            'postgresql://writer:example@db.example/postgres?sslmode=verify-full&sslmode=verify-full',
            'postgresql://writer:example@db.example/postgres',
            'postgresql://:example@db.example/postgres?sslmode=verify-full',
            'postgresql://writer@db.example/postgres?sslmode=verify-full',
            'postgresql://writer:example@db.example?sslmode=verify-full',
            'postgresql://writer:example@pooler.supabase.com/postgres?sslmode=verify-full',
            'postgresql:///postgres?sslmode=verify-full',
            'postgresql://writer:example@@test/postgres?sslmode=verify-full',
            'postgresql://writer:example@db.invalid,@test/postgres?sslmode=verify-full',
            'postgresql://writer:example@db.invalid,/postgres?sslmode=verify-full',
        ]
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                job.connection_environment({
                    'DATABASE_URL': url,
                    'PRESSWATCH_DB_CA_CERT': 'ca',
                    'PGHOST': 'inherited',
                })

    def test_malformed_url_does_not_expose_credentials(self) -> None:
        """URL解析に失敗した場合に入力値や解析元の例外を外へ渡さないこと"""
        with self.assertRaises(ValueError) as failure:
            job.connection_environment({
                'DATABASE_URL': 'malformed:sample-user:sample-password@db.invalid/postgres',
                'PRESSWATCH_DB_CA_CERT': 'ca',
            })

        error = failure.exception
        for value in ('malformed:', 'sample-user', 'sample-password', 'db.invalid'):
            self.assertNotIn(value, str(error))
        self.assertIsNone(error.__context__)

    def test_target_connection_drops_inherited_pg_settings(self) -> None:
        """対象URLを維持しつつ親の接続先とパスワードを除くこと"""
        url = 'postgresql+psycopg://writer:example@db.example/postgres?sslmode=verify-full'
        env = job.connection_environment({
            'DATABASE_URL': url,
            'PRESSWATCH_DB_CA_CERT': 'ca',
            'PGHOST': 'wrong',
            'PGPASSWORD': 'wrong',
            'PATH': '/bin',
        })
        self.assertNotIn('PGHOST', env)
        self.assertNotIn('PGPASSWORD', env)
        prepared = make_url(env['DATABASE_URL'])
        self.assertEqual(prepared.host, 'db.example')
        self.assertEqual(prepared.password, 'example')
        self.assertEqual(prepared.query['sslmode'], 'verify-full')
        self.assertEqual(prepared.query['connect_timeout'], '5')
