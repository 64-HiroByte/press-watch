"""ローカル巡回manifestの形式と値の検証"""

from datetime import UTC, datetime
import re
from typing import Any

from .env_press import _has_same_origin, _resolve_http_url


MANIFEST_VERSION = 1
MANIFEST_FILENAME = 'manifest.json'
PAGES_DIRECTORY_NAME = 'pages'
JSON_ENCODING = 'utf-8'
MAX_FAILURE_REASON_LENGTH = 1000
VALID_STOP_REASONS = {
    'archive_month_limit_reached',
    'duplicate_release_detected',
    'archive_month_links_exhausted',
}
FAILURE_PAGE_STATUS_TO_STAGE = {
    'fetch_failed': 'fetch',
    'save_failed': 'save',
    'parse_failed': 'parse',
    'invalid': 'validate',
}
CREDENTIALS_IN_URL_RE = re.compile(r'(?i)(https?://)[^/@\s]+@')


class CrawlStateError(RuntimeError):
    """巡回stateが安全に利用できない場合の例外"""


def new_page(
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


def archive_page_file(index: int) -> str:
    """月別ページ番号に対応する固定相対パスを生成"""

    return f'{PAGES_DIRECTORY_NAME}/archive-{index:04}.html'


def validate_crawl_conditions(
    archive_month_limit: int,
    all_archive_months: bool,
) -> None:
    """stateを利用できる月別巡回条件か検証

    Args:
        archive_month_limit: 取得する月別ページ数
        all_archive_months: 全月別ページを巡回するかどうか

    Raises:
        CrawlStateError: 全月または正の件数指定になっていない場合
    """

    is_integer_limit = isinstance(archive_month_limit, int) and not isinstance(
        archive_month_limit,
        bool,
    )
    if not is_integer_limit or (
        all_archive_months and archive_month_limit != 0
    ) or (not all_archive_months and archive_month_limit <= 0):
        raise CrawlStateError('crawl conditions are invalid')


def validate_manifest(
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
    if manifest['status'] == 'failed' and not any(
        page['status'] in FAILURE_PAGE_STATUS_TO_STAGE for page in pages
    ):
        raise CrawlStateError('failed crawl state requires a failed page')
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
        else archive_page_file(index)
    )
    if value['id'] != expected_id or value['kind'] != expected_kind:
        raise CrawlStateError('crawl state page identity is invalid')
    if value['file'] != expected_file:
        raise CrawlStateError('crawl state page path is invalid')
    if not isinstance(value['url'], str):
        raise CrawlStateError('crawl state page URL is invalid')
    validated_page_url = validated_url(value['url'])
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
    if (value['status'] in FAILURE_PAGE_STATUS_TO_STAGE) != (
        value['failure'] is not None
    ):
        raise CrawlStateError(
            'crawl state page failure status is inconsistent'
        )
    expected_failure_stage = FAILURE_PAGE_STATUS_TO_STAGE.get(
        value['status']
    )
    if (
        expected_failure_stage is not None
        and value['failure']['stage'] != expected_failure_stage
    ):
        raise CrawlStateError(
            'crawl state failure stage does not match page status'
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


def validated_url(url: str) -> str:
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


def failure_reason(exc: Exception) -> str:
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


def utc_now() -> datetime:
    """現在のUTC日時を取得"""

    return datetime.now(UTC)


def timestamp(value: datetime) -> str:
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
