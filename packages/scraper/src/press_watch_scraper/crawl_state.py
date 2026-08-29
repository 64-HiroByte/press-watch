"""ローカル月別巡回stateの保存と再開"""

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from ._crawl_state_manifest import (
    CrawlStateError,
    JSON_ENCODING,
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    PAGES_DIRECTORY_NAME,
    archive_page_file,
    failure_reason,
    new_page,
    timestamp,
    utc_now,
    validate_crawl_conditions,
    validate_manifest,
    validated_url,
)
from ._crawl_state_storage import (
    atomic_write,
    prepare_new_state_directory,
    read_manifest,
    validate_existing_state_directory,
    validate_state_file,
    validated_cleanup_entries,
)
from .env_press import (
    ArchiveMonthLink,
    CrawlStopReason,
    _has_same_origin,
)


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
        """manifestを保持する巡回stateを初期化

        Args:
            root: stateディレクトリ
            manifest: 読み書きするmanifest
            refetch_invalid_pages: 検証不能ページを再取得するかどうか
            clock: manifest日時の生成に使う時計
        """

        self.root = root
        self._manifest = manifest
        self._refetch_invalid_pages = refetch_invalid_pages
        self._clock = clock or utc_now

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

        validate_crawl_conditions(
            archive_month_limit,
            all_archive_months,
        )
        validated_start_url = validated_url(start_url)
        prepare_new_state_directory(root)

        now = timestamp((clock or utc_now)())
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
            'archive_plan_registered': False,
            'status': 'in_progress',
            'stop_reason': None,
            'created_at': now,
            'updated_at': now,
            'completed_at': None,
            'pages': [
                new_page(
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

        validate_crawl_conditions(
            archive_month_limit,
            all_archive_months,
        )
        validate_existing_state_directory(root)
        manifest_value = read_manifest(root / MANIFEST_FILENAME)

        validated_start_url = validated_url(start_url)
        expected_mode = (
            'all_archive_months'
            if all_archive_months
            else 'archive_month_limit'
        )
        expected_limit = None if all_archive_months else archive_month_limit
        validate_manifest(
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

        validated_archive_links = tuple(
            ArchiveMonthLink(
                year=link.year,
                month=link.month,
                url=validated_url(link.url),
            )
            for link in archive_links
        )
        existing_archive_pages = self._manifest['pages'][1:]
        if self._manifest['archive_plan_registered']:
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
                    archive_page_file(index),
                )
                for index, link in enumerate(
                    validated_archive_links,
                    start=1,
                )
            ]
            if actual != expected:
                mismatch_error = CrawlStateError(
                    'archive page plan does not match crawl state manifest'
                )
                self._record_failure(
                    self._manifest['pages'][0],
                    'invalid',
                    'validate',
                    mismatch_error,
                )
                raise mismatch_error
            return

        now = self._now()
        for index, link in enumerate(validated_archive_links, start=1):
            if not _has_same_origin(self._manifest['start_url'], link.url):
                raise CrawlStateError(
                    'archive page URL must use the crawl start origin'
                )
            self._manifest['pages'].append(
                new_page(
                    page_id=f'archive-{index:04}',
                    kind='archive',
                    year=link.year,
                    month=link.month,
                    url=link.url,
                    file_path=archive_page_file(index),
                    updated_at=now,
                )
            )
        self._manifest['archive_plan_registered'] = True
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
            atomic_write(page_path, html_bytes)
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

        if not self._manifest['archive_plan_registered']:
            raise CrawlStateError(
                'crawl state cannot complete before archive plan registration'
            )
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
        validate_state_file(
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
            'reason': failure_reason(exc),
            'occurred_at': now,
        }
        page['updated_at'] = now
        self._manifest['status'] = 'failed'
        self._manifest['stop_reason'] = None
        self._manifest['completed_at'] = None
        self._touch(now)
        self._write_manifest()

    def _now(self) -> str:
        """現在時刻をmanifest用のUTC文字列で取得"""

        return timestamp(self._clock())

    def _touch(self, timestamp: str) -> None:
        """manifest全体の更新日時を設定

        Args:
            timestamp: 設定するUTC日時文字列
        """

        self._manifest['updated_at'] = timestamp

    def _write_manifest(self) -> None:
        """現在のmanifestをJSONとして原子的に保存"""

        payload = json.dumps(
            self._manifest,
            ensure_ascii=False,
            indent=2,
        )
        atomic_write(
            self.root / MANIFEST_FILENAME,
            f'{payload}\n'.encode(JSON_ENCODING),
        )


def cleanup_crawl_state(root: Path) -> None:
    """検証済みの完了巡回stateを削除

    削除対象をすべて検証してから、manifestで管理するHTML、内部一時
    ファイル、manifest、空ディレクトリの順に削除する。

    Args:
        root: 削除するstateディレクトリ

    Raises:
        CrawlStateError: 未完了、破損、管理外ファイルなどを検出した場合
    """

    validate_existing_state_directory(root)
    manifest_path = root / MANIFEST_FILENAME
    manifest = read_manifest(manifest_path)
    start_url = manifest.get('start_url')
    crawl_mode = manifest.get('crawl_mode')
    archive_month_limit = manifest.get('archive_month_limit')
    if not isinstance(start_url, str) or not isinstance(crawl_mode, str):
        raise CrawlStateError('crawl state manifest fields are invalid')
    validated_start_url = validated_url(start_url)
    validate_manifest(
        manifest,
        expected_start_url=validated_start_url,
        expected_mode=crawl_mode,
        expected_limit=archive_month_limit,
    )
    if manifest['status'] != 'complete':
        raise CrawlStateError('crawl state is not complete')
    if any(page['status'] != 'parsed' for page in manifest['pages']):
        raise CrawlStateError('completed crawl state has unparsed pages')

    state = CrawlState(root, manifest)
    for page in manifest['pages']:
        state._read_valid_page(page)

    page_paths, temporary_paths = validated_cleanup_entries(root, manifest)
    for path in [*page_paths, *temporary_paths]:
        path.unlink()
    manifest_path.unlink()
    (root / PAGES_DIRECTORY_NAME).rmdir()
    root.rmdir()
