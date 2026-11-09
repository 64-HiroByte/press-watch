"""ローカルTLS検証が親の接続先設定を使用しないことを確認"""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from integration_tests import run_fetch_job_tls as validation


class ValidationSafetyTest(unittest.TestCase):
    """検証プロセスのDocker・libpq設定を隔離"""

    def test_docker_connection_is_fixed_and_parent_settings_removed(self) -> None:
        """親がremote contextでも専用設定とローカルUnix socketだけを使用すること"""
        with (
            patch.object(Path, 'is_socket', return_value=True),
            patch.object(Path, 'is_file', return_value=True),
        ):
            env = validation.local_environment(
                {
                    'DOCKER_HOST': 'tcp://remote.invalid:2375',
                    'DOCKER_CONTEXT': 'remote',
                    'DOCKER_CONFIG': '/original',
                    'PGHOSTADDR': '192.0.2.1',
                    'DATABASE_URL': 'unused',
                },
                '/tmp/dedicated',
            )
        self.assertTrue(env['DOCKER_HOST'].startswith('unix://'))
        self.assertEqual(env['DOCKER_CONFIG'], '/tmp/dedicated')
        self.assertNotIn('DOCKER_CONTEXT', env)
        self.assertNotIn('PGHOSTADDR', env)
        self.assertNotIn('DATABASE_URL', env)

    def test_first_database_connection_has_no_parent_pg_settings(self) -> None:
        """最初の管理接続に到達する時点で親のPGHOSTADDRとPGOPTIONSがないこと"""
        class Checked(Exception):
            """実接続前に検証を終えるテスト用例外"""

        def inspect_connection(**kwargs):
            """実接続を行わず環境の隔離状態を確認

            Args:
                kwargs: 接続へ渡す明示設定
            """
            self.assertFalse('PGHOSTADDR' in os.environ)
            self.assertFalse('PGOPTIONS' in os.environ)
            raise Checked()

        with (
            patch.dict(
                os.environ,
                {
                    'PGHOSTADDR': '192.0.2.1',
                    'PGOPTIONS': '-c default_transaction_read_only=on',
                },
            ),
            patch.object(
                validation.psycopg,
                'connect',
                side_effect=inspect_connection,
            ),
        ):
            with self.assertRaises(Checked):
                validation._verify(
                    55434,
                    'synthetic',
                    Path('/tmp'),
                    {},
                    'synthetic-container',
                )

    def test_missing_local_socket_is_rejected_before_docker_start(self) -> None:
        """既知ローカルsocketがない場合はremoteへ代替接続せず起動前に拒否すること"""
        with (
            patch.object(Path, 'is_socket', return_value=False),
            patch.object(validation.subprocess, 'run') as run,
        ):
            with self.assertRaises(RuntimeError):
                validation.local_environment(
                    {'DOCKER_HOST': 'tcp://remote.invalid:2375'},
                    '/tmp/dedicated',
                )
        run.assert_not_called()
