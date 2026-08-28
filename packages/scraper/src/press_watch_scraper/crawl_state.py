"""ローカル月別巡回stateの保存と検証"""

from collections.abc import Callable
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .env_press import (
    ArchiveMonthLink,
    CrawlStopReason,
    _has_same_origin,
    _resolve_http_url,
)


MANIFEST_VERSION = 1
MANIFEST_FILENAME = 'manifest.json'
PAGES_DIRECTORY_NAME = 'pages'
STATE_DIRECTORY_MODE = 0o700
STATE_FILE_MODE = 0o600
JSON_ENCODING = 'utf-8'
CREDENTIALS_IN_URL_RE = re.compile(r'(?i)(https?://)[^/@\s]+@')
MAX_FAILURE_REASON_LENGTH = 1000
VALID_STOP_REASONS = {
    'archive_month_limit_reached',
    'duplicate_release_detected',
    'archive_month_links_exhausted',
}


class CrawlStateError(RuntimeError):
    """巡回stateが安全に利用できない場合の例外"""


class CrawlState:
    """ページHTMLとmanifestを管理するローカル巡回state

    Attributes:
        root: stateディレクトリ
    """

    def __init__(
        self,
        root: Path,
        manifest: dict[str, Any],
        *,
        refetch_invalid_pages: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = root
        self._manifest = manifest
        self._refetch_invalid_pages = refetch_invalid_pages
        self._clock = clock or _utc_now

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        start_url: str,
        archive_month_limit: int,
        all_archive_months: bool,
        clock: Callable[[], datetime] | None = None,
    ) -> 'CrawlState':
        """新規ローカル巡回stateを作成

        Args:
            root: stateディレクトリ
            start_url: 起点ページURL
            archive_month_limit: 取得する月別ページ数
            all_archive_months: 全月別ページを巡回するかどうか
            clock: manifest日時の生成に使う時計

        Returns:
            初期manifestを保持する巡回state

        Raises:
            CrawlStateError: 保存先やURLが新規stateの条件を満たさない場合
        """

        validated_start_url = _validated_url(start_url)
        _prepare_new_state_directory(root)
        pages_directory = root / PAGES_DIRECTORY_NAME
        pages_directory.mkdir(mode=STATE_DIRECTORY_MODE)
        os.chmod(pages_directory, STATE_DIRECTORY_MODE)

        now = _timestamp((clock or _utc_now)())
        mode = (
            'all_archive_months'
            if all_archive_months
            else 'archive_month_limit'
        )
        manifest: dict[str, Any] = {
            'version': MANIFEST_VERSION,
            'start_url': validated_start_url,
            'crawl_mode': mode,
            'archive_month_limit': (
                None if all_archive_months else archive_month_limit
            ),
            'status': 'in_progress',
            'stop_reason': None,
            'created_at': now,
            'updated_at': now,
            'completed_at': None,
            'pages': [
                _new_page(
                    page_id='index',
                    kind='index',
                    year=None,
                    month=None,
                    url=validated_start_url,
                    file_path=f'{PAGES_DIRECTORY_NAME}/index.html',
                    updated_at=now,
                )
            ],
        }
        state = cls(root, manifest, clock=clock)
        state._write_manifest()
        return state

    @classmethod
    def resume(
        cls,
        root: Path,
        *,
        start_url: str,
        archive_month_limit: int,
        all_archive_months: bool,
        refetch_invalid_pages: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> 'CrawlState':
        """既存manifestからローカル巡回を再開

        Args:
            root: 既存stateディレクトリ
            start_url: 再開時に指定された起点ページURL
            archive_month_limit: 再開時の月別ページ数
            all_archive_months: 全月別ページを巡回するかどうか
            refetch_invalid_pages: 検証不能ページを明示的に再取得するかどうか
            clock: manifest日時の生成に使う時計

        Returns:
            検証済みmanifestを保持する巡回state

        Raises:
            CrawlStateError: stateまたは巡回条件を安全に再利用できない場合
        """

        _validate_existing_state_directory(root)
        manifest_value = _read_manifest(root / MANIFEST_FILENAME)

        validated_start_url = _validated_url(start_url)
        expected_mode = (
            'all_archive_months'
            if all_archive_months
            else 'archive_month_limit'
        )
        expected_limit = None if all_archive_months else archive_month_limit
        _validate_manifest(
            manifest_value,
            expected_start_url=validated_start_url,
            expected_mode=expected_mode,
            expected_limit=expected_limit,
        )
        state = cls(
            root,
            manifest_value,
            refetch_invalid_pages=refetch_invalid_pages,
            clock=clock,
        )
        state._validate_resume_pages()
        now = state._now()
        state._manifest['status'] = 'in_progress'
        state._manifest['stop_reason'] = None
        state._manifest['completed_at'] = None
        state._touch(now)
        state._write_manifest()
        return state

    def register_archive_pages(
        self,
        archive_links: tuple[ArchiveMonthLink, ...],
    ) -> None:
        """選択済み月別ページをmanifestへ登録

        Args:
            archive_links: 実際に巡回する年月降順の月別リンク
        """

        existing_archive_pages = self._manifest['pages'][1:]
        if existing_archive_pages:
            expected = [
                (
                    page['year'],
                    page['month'],
                    page['url'],
                    page['file'],
                )
                for page in existing_archive_pages
            ]
            actual = [
                (
                    link.year,
                    link.month,
                    link.url,
                    _archive_page_file(index),
                )
                for index, link in enumerate(archive_links, start=1)
            ]
            if actual != expected:
                raise CrawlStateError(
                    'archive page plan does not match crawl state manifest'
                )
            return

        now = self._now()
        for index, link in enumerate(archive_links, start=1):
            if not _has_same_origin(self._manifest['start_url'], link.url):
                raise CrawlStateError(
                    'archive page URL must use the crawl start origin'
                )
            self._manifest['pages'].append(
                _new_page(
                    page_id=f'archive-{index:04}',
                    kind='archive',
                    year=link.year,
                    month=link.month,
                    url=link.url,
                    file_path=_archive_page_file(index),
                    updated_at=now,
                )
            )
        self._touch(now)
        self._write_manifest()

    def load_or_fetch(
        self,
        url: str,
        fetcher: Callable[[str], str],
        *,
        progress: Callable[[str], None] | None = None,
    ) -> str:
        """保存済みHTMLを読み込み、未取得の場合は取得して保存

        Args:
            url: 読み込みまたは取得するページURL
            fetcher: 実HTTP取得を行う関数
            progress: 保存元を通知する関数

        Returns:
            解析へ渡すHTML
        """

        page = self._page_for_url(url)
        if page['status'] in {'saved', 'parsing', 'parsed', 'parse_failed'}:
            html = self._read_valid_page(page)
            if progress is not None:
                progress(f'reusing saved crawl page: {url}')
            return html

        now = self._now()
        page['status'] = 'fetching'
        page['size_bytes'] = None
        page['sha256'] = None
        page['failure'] = None
        page['updated_at'] = now
        self._touch(now)
        self._write_manifest()
        if progress is not None:
            progress(f'fetching crawl page: {url}')

        try:
            html = fetcher(url)
        except Exception as exc:
            self._record_failure(page, 'fetch_failed', 'fetch', exc)
            raise

        now = self._now()
        page['status'] = 'saving'
        page['updated_at'] = now
        self._touch(now)
        self._write_manifest()

        html_bytes = html.encode(JSON_ENCODING)
        page_path = self.root / page['file']
        try:
            _atomic_write(page_path, html_bytes)
        except Exception as exc:
            self._record_failure(page, 'save_failed', 'save', exc)
            raise

        now = self._now()
        page['status'] = 'saved'
        page['size_bytes'] = len(html_bytes)
        page['sha256'] = hashlib.sha256(html_bytes).hexdigest()
        page['failure'] = None
        page['updated_at'] = now
        self._touch(now)
        self._write_manifest()
        if progress is not None:
            progress(f'saved crawl page: {url}')
        return html

    def mark_parsing(self, url: str) -> None:
        """ページ解析開始をmanifestへ記録

        Args:
            url: 解析を開始するページURL
        """

        self._set_page_status(url, 'parsing')

    def mark_parsed(self, url: str) -> None:
        """ページ解析成功をmanifestへ記録

        Args:
            url: 解析に成功したページURL
        """

        self._set_page_status(url, 'parsed')

    def mark_parse_failed(self, url: str, exc: Exception) -> None:
        """ページ解析失敗をmanifestへ記録

        Args:
            url: 解析に失敗したページURL
            exc: 解析処理が送出した例外
        """

        self._record_failure(
            self._page_for_url(url),
            'parse_failed',
            'parse',
            exc,
        )

    def mark_complete(self, stop_reason: CrawlStopReason) -> None:
        """巡回全体の正常完了をmanifestへ記録

        Args:
            stop_reason: 月別巡回が正常に終了した理由
        """

        if any(
            page['status'] != 'parsed' for page in self._manifest['pages']
        ):
            raise CrawlStateError(
                'crawl state cannot complete with unparsed pages'
            )
        now = self._now()
        self._manifest['status'] = 'complete'
        self._manifest['stop_reason'] = stop_reason
        self._manifest['completed_at'] = now
        self._touch(now)
        self._write_manifest()

    def _read_valid_page(self, page: dict[str, Any]) -> str:
        """保存HTMLを検証して読み込み

        Args:
            page: manifestに記録されたページ情報

        Returns:
            UTF-8で復号した保存HTML

        Raises:
            CrawlStateError: ファイル、権限、サイズ、SHA-256が不正な場合
            UnicodeError: 保存HTMLをUTF-8で復号できない場合
        """

        page_path = self.root / page['file']
        _validate_state_file(
            page_path,
            f'saved crawl page {page["id"]}',
        )
        page_bytes = page_path.read_bytes()
        if len(page_bytes) != page['size_bytes']:
            raise CrawlStateError(
                f'saved crawl page size does not match: {page["id"]}'
            )
        page_hash = hashlib.sha256(page_bytes).hexdigest()
        if page_hash != page['sha256']:
            raise CrawlStateError(
                f'saved crawl page hash does not match: {page["id"]}'
            )
        return page_bytes.decode(JSON_ENCODING)

    def _validate_resume_pages(self) -> None:
        """再開前に全ページの再利用可否を検証

        検証不能ページは失敗状態へ更新し、明示的な再取得指定がなければ
        再開を拒否する。symlinkは再取得指定の有無にかかわらず拒否する。

        Raises:
            CrawlStateError: ページを安全に再利用または再取得できない場合
        """

        reusable_statuses = {
            'saved',
            'parsing',
            'parsed',
            'parse_failed',
        }
        refetch_required_statuses = {
            'fetching',
            'saving',
            'save_failed',
            'invalid',
        }
        for page in self._manifest['pages']:
            page_path = self.root / page['file']
            if page_path.is_symlink():
                raise CrawlStateError(
                    f'saved crawl page must not be a symlink: {page["id"]}'
                )
            if page['status'] in reusable_statuses:
                try:
                    self._read_valid_page(page)
                except (CrawlStateError, UnicodeError) as exc:
                    self._record_failure(
                        page,
                        'invalid',
                        'validate',
                        exc,
                    )
                    if not self._refetch_invalid_pages:
                        raise CrawlStateError(
                            f'crawl page cannot be reused: {page["id"]}'
                        ) from exc
            elif (
                page['status'] in refetch_required_statuses
                and not self._refetch_invalid_pages
            ):
                raise CrawlStateError(
                    'crawl page requires --refetch-invalid-pages: '
                    f'{page["id"]}'
                )

    def _page_for_url(self, url: str) -> dict[str, Any]:
        """URLに対応するmanifestのページ情報を取得

        Args:
            url: 検索するページURL

        Returns:
            URLに対応するページ情報

        Raises:
            CrawlStateError: URLがmanifestへ登録されていない場合
        """

        for page in self._manifest['pages']:
            if page['url'] == url:
                return page
        raise CrawlStateError(f'page URL is not registered in manifest: {url}')

    def _set_page_status(self, url: str, status_value: str) -> None:
        """ページ状態を更新してmanifestへ保存

        Args:
            url: 更新するページURL
            status_value: 更新後のページ状態
        """

        page = self._page_for_url(url)
        now = self._now()
        page['status'] = status_value
        page['failure'] = None
        page['updated_at'] = now
        self._touch(now)
        self._write_manifest()

    def _record_failure(
        self,
        page: dict[str, Any],
        status_value: str,
        stage: str,
        exc: Exception,
    ) -> None:
        """ページと巡回全体の失敗情報をmanifestへ記録

        Args:
            page: 失敗したページ情報
            status_value: ページへ設定する失敗状態
            stage: 失敗した処理段階
            exc: 記録対象の例外
        """

        now = self._now()
        page['status'] = status_value
        page['failure'] = {
            'stage': stage,
            'exception': type(exc).__name__,
            'reason': _failure_reason(exc),
            'occurred_at': now,
        }
        page['updated_at'] = now
        self._manifest['status'] = 'failed'
        self._manifest['stop_reason'] = None
        self._manifest['completed_at'] = None
        self._touch(now)
        self._write_manifest()

    def _now(self) -> str:
        return _timestamp(self._clock())

    def _touch(self, timestamp: str) -> None:
        self._manifest['updated_at'] = timestamp

    def _write_manifest(self) -> None:
        """現在のmanifestをJSONとして原子的に保存"""

        payload = json.dumps(
            self._manifest,
            ensure_ascii=False,
            indent=2,
        )
        _atomic_write(
            self.root / MANIFEST_FILENAME,
            f'{payload}\n'.encode(JSON_ENCODING),
        )




def _new_page(
    *,
    page_id: str,
    kind: str,
    year: int | None,
    month: int | None,
    url: str,
    file_path: str,
    updated_at: str,
) -> dict[str, Any]:
    """未取得ページの初期manifest項目を生成

    Args:
        page_id: manifest内で一意となるページID
        kind: 起点ページまたは月別ページを表す種別
        year: 月別ページの年、起点ページの場合はNone
        month: 月別ページの月、起点ページの場合はNone
        url: 取得対象の絶対URL
        file_path: stateディレクトリからのHTML相対パス
        updated_at: ページ状態の更新日時

    Returns:
        `pending`状態のページ情報
    """

    return {
        'id': page_id,
        'kind': kind,
        'year': year,
        'month': month,
        'url': url,
        'file': file_path,
        'status': 'pending',
        'size_bytes': None,
        'sha256': None,
        'updated_at': updated_at,
        'failure': None,
    }


def _archive_page_file(index: int) -> str:
    return f'{PAGES_DIRECTORY_NAME}/archive-{index:04}.html'


def _prepare_new_state_directory(root: Path) -> None:
    """新規state用の空ディレクトリを安全な権限で準備

    Args:
        root: 準備するstateディレクトリ

    Raises:
        CrawlStateError: パスがsymlink、ディレクトリ以外、または空でない場合
    """

    if root.is_symlink():
        raise CrawlStateError('crawl state directory must not be a symlink')
    if root.exists():
        if not root.is_dir():
            raise CrawlStateError('crawl state path must be a directory')
        if any(root.iterdir()):
            raise CrawlStateError('new crawl state directory must be empty')
        os.chmod(root, STATE_DIRECTORY_MODE)
        return
    if not root.parent.is_dir():
        raise CrawlStateError(
            'crawl state parent directory does not exist'
        )
    root.mkdir(mode=STATE_DIRECTORY_MODE)
    os.chmod(root, STATE_DIRECTORY_MODE)


def _validate_existing_state_directory(root: Path) -> None:
    """既存stateとpagesディレクトリの所有者・権限を検証

    Args:
        root: 検証するstateディレクトリ

    Raises:
        CrawlStateError: ディレクトリ構成、所有者、権限が不正な場合
    """

    if root.is_symlink():
        raise CrawlStateError('crawl state directory must not be a symlink')
    if not root.is_dir():
        raise CrawlStateError('crawl state directory does not exist')
    root_stat = root.stat()
    if hasattr(os, 'geteuid') and root_stat.st_uid != os.geteuid():
        raise CrawlStateError('crawl state directory must be owned by the user')
    if (root_stat.st_mode & 0o777) != STATE_DIRECTORY_MODE:
        raise CrawlStateError(
            'crawl state directory permissions must be 0700'
        )
    pages_directory = root / PAGES_DIRECTORY_NAME
    if pages_directory.is_symlink() or not pages_directory.is_dir():
        raise CrawlStateError('crawl state pages directory is invalid')
    pages_stat = pages_directory.stat()
    if hasattr(os, 'geteuid') and pages_stat.st_uid != os.geteuid():
        raise CrawlStateError(
            'crawl state pages directory must be owned by the user'
        )
    if (pages_stat.st_mode & 0o777) != STATE_DIRECTORY_MODE:
        raise CrawlStateError(
            'crawl state pages directory permissions must be 0700'
        )


def _validate_state_file(path: Path, label: str) -> None:
    """state内ファイルの種別・所有者・権限を検証

    Args:
        path: 検証するファイルパス
        label: エラーメッセージに使用する対象名

    Raises:
        CrawlStateError: 通常ファイルでないか所有者・権限が不正な場合
    """

    if path.is_symlink() or not path.is_file():
        raise CrawlStateError(f'{label} is missing or invalid')
    path_stat = path.stat()
    if hasattr(os, 'geteuid') and path_stat.st_uid != os.geteuid():
        raise CrawlStateError(f'{label} must be owned by the user')
    if (path_stat.st_mode & 0o777) != STATE_FILE_MODE:
        raise CrawlStateError(f'{label} permissions must be 0600')


def _read_manifest(path: Path) -> dict[str, Any]:
    """stateのmanifestをJSONオブジェクトとして読み込み

    Args:
        path: manifestのファイルパス

    Returns:
        JSONから復元したmanifest

    Raises:
        CrawlStateError: ファイルまたはJSONオブジェクトが不正な場合
    """

    _validate_state_file(path, 'crawl state manifest')
    try:
        manifest_value = json.loads(path.read_text(encoding=JSON_ENCODING))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CrawlStateError('crawl state manifest is invalid') from exc
    if not isinstance(manifest_value, dict):
        raise CrawlStateError('crawl state manifest must be an object')
    return manifest_value






def _validate_manifest(
    manifest: dict[str, Any],
    *,
    expected_start_url: str,
    expected_mode: str,
    expected_limit: int | None,
) -> None:
    """manifest全体のschemaと再開条件との一致を検証

    Args:
        manifest: 検証するmanifest
        expected_start_url: 再開またはcleanupで期待する起点URL
        expected_mode: 期待する巡回モード
        expected_limit: 期待する月別ページ数上限

    Raises:
        CrawlStateError: 必須項目、型、列挙値、巡回条件が不正な場合
    """

    expected_keys = {
        'version',
        'start_url',
        'crawl_mode',
        'archive_month_limit',
        'status',
        'stop_reason',
        'created_at',
        'updated_at',
        'completed_at',
        'pages',
    }
    if set(manifest) != expected_keys:
        raise CrawlStateError('crawl state manifest fields are invalid')
    if not isinstance(manifest['version'], int) or isinstance(
        manifest['version'],
        bool,
    ):
        raise CrawlStateError('crawl state manifest version is invalid')
    if manifest['version'] != MANIFEST_VERSION:
        raise CrawlStateError('crawl state manifest version is unsupported')
    if manifest['start_url'] != expected_start_url:
        raise CrawlStateError('crawl start URL does not match manifest')
    if manifest['crawl_mode'] != expected_mode:
        raise CrawlStateError('crawl mode does not match manifest')
    if manifest['crawl_mode'] not in {
        'all_archive_months',
        'archive_month_limit',
    }:
        raise CrawlStateError('crawl mode is invalid')
    if manifest['archive_month_limit'] != expected_limit:
        raise CrawlStateError('crawl month limit does not match manifest')
    if manifest['crawl_mode'] == 'all_archive_months':
        if manifest['archive_month_limit'] is not None:
            raise CrawlStateError('crawl month limit is invalid')
    elif (
        not isinstance(manifest['archive_month_limit'], int)
        or isinstance(manifest['archive_month_limit'], bool)
        or manifest['archive_month_limit'] <= 0
    ):
        raise CrawlStateError('crawl month limit is invalid')
    if not isinstance(manifest['status'], str) or manifest['status'] not in {
        'in_progress',
        'failed',
        'complete',
    }:
        raise CrawlStateError('crawl state status is invalid')
    for timestamp_field in ('created_at', 'updated_at'):
        if not _is_timestamp(manifest[timestamp_field]):
            raise CrawlStateError(
                f'crawl state {timestamp_field} is invalid'
            )
    completed_at = manifest['completed_at']
    if completed_at is not None and not _is_timestamp(completed_at):
        raise CrawlStateError('crawl state completed_at is invalid')
    if manifest['status'] == 'complete':
        if completed_at is None:
            raise CrawlStateError(
                'completed crawl state requires completed_at'
            )
        if (
            not isinstance(manifest['stop_reason'], str)
            or manifest['stop_reason'] not in VALID_STOP_REASONS
        ):
            raise CrawlStateError(
                'completed crawl state stop_reason is invalid'
            )
    elif completed_at is not None or manifest['stop_reason'] is not None:
        raise CrawlStateError(
            'incomplete crawl state completion fields are invalid'
        )
    pages = manifest['pages']
    if not isinstance(pages, list) or not pages:
        raise CrawlStateError('crawl state pages are invalid')
    for index, page in enumerate(pages):
        _validate_page(page, index=index, start_url=expected_start_url)
    page_urls = [page['url'] for page in pages]
    if len(set(page_urls)) != len(page_urls):
        raise CrawlStateError('crawl state page URLs must be unique')
    if (
        manifest['crawl_mode'] == 'archive_month_limit'
        and len(pages) - 1 > manifest['archive_month_limit']
    ):
        raise CrawlStateError('crawl state page count exceeds month limit')
    if manifest['status'] == 'complete' and any(
        page['status'] != 'parsed' for page in pages
    ):
        raise CrawlStateError(
            'completed crawl state has unparsed pages'
        )


def _validate_page(
    value: object,
    *,
    index: int,
    start_url: str,
) -> None:
    """manifest内のページ項目と固定パス対応を検証

    Args:
        value: 検証するページ項目
        index: manifestのページ一覧における位置
        start_url: 同一オリジン判定に使う起点URL

    Raises:
        CrawlStateError: 項目、型、URL、パス、状態が不正な場合
    """

    if not isinstance(value, dict):
        raise CrawlStateError('crawl state page must be an object')
    expected_keys = {
        'id',
        'kind',
        'year',
        'month',
        'url',
        'file',
        'status',
        'size_bytes',
        'sha256',
        'updated_at',
        'failure',
    }
    if set(value) != expected_keys:
        raise CrawlStateError('crawl state page fields are invalid')
    expected_id = 'index' if index == 0 else f'archive-{index:04}'
    expected_kind = 'index' if index == 0 else 'archive'
    expected_file = (
        f'{PAGES_DIRECTORY_NAME}/index.html'
        if index == 0
        else _archive_page_file(index)
    )
    if value['id'] != expected_id or value['kind'] != expected_kind:
        raise CrawlStateError('crawl state page identity is invalid')
    if value['file'] != expected_file:
        raise CrawlStateError('crawl state page path is invalid')
    if not isinstance(value['url'], str):
        raise CrawlStateError('crawl state page URL is invalid')
    validated_page_url = _validated_url(value['url'])
    if index == 0:
        if validated_page_url != start_url:
            raise CrawlStateError('crawl state index URL is invalid')
        if value['year'] is not None or value['month'] is not None:
            raise CrawlStateError('crawl state index month is invalid')
    else:
        if not _has_same_origin(start_url, validated_page_url):
            raise CrawlStateError('crawl state archive URL origin is invalid')
        if (
            not isinstance(value['year'], int)
            or isinstance(value['year'], bool)
            or not isinstance(value['month'], int)
            or isinstance(value['month'], bool)
        ):
            raise CrawlStateError('crawl state archive month is invalid')
        if value['month'] < 1 or value['month'] > 12:
            raise CrawlStateError('crawl state archive month is invalid')
    allowed_statuses = {
        'pending',
        'fetching',
        'saving',
        'saved',
        'parsing',
        'parsed',
        'fetch_failed',
        'save_failed',
        'parse_failed',
        'invalid',
    }
    if not isinstance(value['status'], str) or value['status'] not in (
        allowed_statuses
    ):
        raise CrawlStateError('crawl state page status is invalid')
    if not _is_timestamp(value['updated_at']):
        raise CrawlStateError('crawl state page updated_at is invalid')
    if value['size_bytes'] is not None and not isinstance(
        value['size_bytes'], int
    ):
        raise CrawlStateError('crawl state page size is invalid')
    if isinstance(value['size_bytes'], bool) or (
        isinstance(value['size_bytes'], int) and value['size_bytes'] < 0
    ):
        raise CrawlStateError('crawl state page size is invalid')
    if value['sha256'] is not None and not (
        isinstance(value['sha256'], str)
        and re.fullmatch(r'[0-9a-f]{64}', value['sha256']) is not None
    ):
        raise CrawlStateError('crawl state page hash is invalid')
    if (value['size_bytes'] is None) != (value['sha256'] is None):
        raise CrawlStateError('crawl state page metadata is inconsistent')
    _validate_failure(value['failure'])
    saved_statuses = {'saved', 'parsing', 'parsed', 'parse_failed'}
    if value['status'] in saved_statuses:
        if value['size_bytes'] is None or value['sha256'] is None:
            raise CrawlStateError(
                'saved crawl state page metadata is incomplete'
            )
    elif value['status'] == 'invalid':
        if value['failure'] is None:
            raise CrawlStateError(
                'invalid crawl state page requires failure details'
            )
    elif value['size_bytes'] is not None or value['sha256'] is not None:
        if value['status'] not in {'save_failed'}:
            raise CrawlStateError(
                'unsaved crawl state page metadata is invalid'
            )
    failure_statuses = {
        'fetch_failed',
        'save_failed',
        'parse_failed',
        'invalid',
    }
    if (value['status'] in failure_statuses) != (
        value['failure'] is not None
    ):
        raise CrawlStateError(
            'crawl state page failure status is inconsistent'
        )


def _validate_failure(value: object) -> None:
    """ページ失敗情報のschemaと記録形式を検証

    Args:
        value: 検証する失敗情報またはNone

    Raises:
        CrawlStateError: 必須項目、型、処理段階、日時が不正な場合
    """

    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        'stage',
        'exception',
        'reason',
        'occurred_at',
    }:
        raise CrawlStateError('crawl state page failure is invalid')
    if not isinstance(value['stage'], str) or value['stage'] not in {
        'fetch',
        'save',
        'parse',
        'validate',
    }:
        raise CrawlStateError('crawl state failure stage is invalid')
    if not all(
        isinstance(value[field], str)
        for field in ('exception', 'reason')
    ):
        raise CrawlStateError('crawl state failure details are invalid')
    if (
        not value['exception']
        or not value['reason']
        or len(value['reason']) > MAX_FAILURE_REASON_LENGTH
        or '\n' in value['reason']
        or '\r' in value['reason']
    ):
        raise CrawlStateError('crawl state failure details are invalid')
    if not _is_timestamp(value['occurred_at']):
        raise CrawlStateError('crawl state failure time is invalid')


def _is_timestamp(value: object) -> bool:
    """値がUTCのISO 8601日時文字列か判定

    Args:
        value: 判定する値

    Returns:
        `Z`で終わる解釈可能な日時文字列ならTrue
    """

    if not isinstance(value, str) or not value.endswith('Z'):
        return False
    try:
        datetime.fromisoformat(f'{value[:-1]}+00:00')
    except ValueError:
        return False
    return True


def _validated_url(url: str) -> str:
    """stateへ記録できるHTTP(S)絶対URLを検証

    Args:
        url: 検証するURL

    Returns:
        検証済みの絶対URL

    Raises:
        CrawlStateError: URLが保存・取得条件を満たさない場合
    """

    try:
        return _resolve_http_url(url, '')
    except ValueError as exc:
        raise CrawlStateError('crawl state URL is invalid') from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    """一時ファイルを経由してstateファイルを原子的に置換

    一時ファイルと置換後のファイルを`0600`にし、置換前に内容を
    `fsync()`する。失敗時は作成した一時ファイルを削除する。

    Args:
        path: 最終的な保存先パス
        payload: 保存するバイト列
    """

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f'.{path.name}.',
        suffix='.tmp',
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, STATE_FILE_MODE)
        with os.fdopen(file_descriptor, 'wb') as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, STATE_FILE_MODE)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def _failure_reason(exc: Exception) -> str:
    """例外理由をmanifestへ保存できる診断文字列へ変換

    URL内の認証情報を伏字にし、連続空白をまとめて一行化したうえで
    最大文字数へ切り詰める。

    Args:
        exc: 理由を記録する例外

    Returns:
        伏字・一行化・文字数制限を適用した理由
    """

    redacted = CREDENTIALS_IN_URL_RE.sub(
        r'\1[redacted]@',
        str(exc),
    )
    one_line = ' '.join(redacted.split()) or 'no detail'
    if len(one_line) > MAX_FAILURE_REASON_LENGTH:
        return f'{one_line[:MAX_FAILURE_REASON_LENGTH - 3]}...'
    return one_line


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    """timezone付き日時をUTCのISO 8601文字列へ変換

    Args:
        value: 変換するtimezone付き日時

    Returns:
        `Z`で終わるUTC日時文字列

    Raises:
        ValueError: timezoneなしの日時が渡された場合
    """

    if value.tzinfo is None:
        raise ValueError('crawl state clock must return an aware datetime')
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')
