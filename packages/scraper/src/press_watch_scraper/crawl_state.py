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
