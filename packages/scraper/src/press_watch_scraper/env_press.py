from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date
import http.client
import re
from time import monotonic, sleep
from typing import Any, Literal, NoReturn, Protocol
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)

from bs4 import BeautifulSoup
from bs4.element import AttributeValueList, Tag


BASE_URL = 'https://www.env.go.jp'
PRESS_INDEX_URL = f'{BASE_URL}/press/index.html'
USER_AGENT = (
    'PressWatchScraper/0.1 '
    '(+https://www.env.go.jp/press/index.html)'
)

ATTR_ARIA_LABEL = 'aria-label'
ATTR_CLASS = 'class'
ATTR_HREF = 'href'
CHARSET = 'utf-8'
USER_AGENT_HEADER = 'User-Agent'
PARSER = 'lxml'
REQUEST_INTERVAL_SECONDS = 3.0
HTTP_URL_SCHEMES = frozenset({'http', 'https'})
UNSAFE_ASCII_URL_CHARACTERS = frozenset('<>"\\^`{|}')
UNSAFE_REDIRECT_REASON = 'redirect target rejected'
INVALID_PERCENT_ESCAPE_RE = re.compile(r'%(?![0-9A-Fa-f]{2})')
CREDENTIALS_IN_URL_RE = re.compile(
    r'(?i)(https?://)[^/@\s]+@'
)
MAX_DIAGNOSTIC_VALUE_LENGTH = 200

CLASS_ARCHIVE_MONTH_LINK = 'c-table-month__col__link'
CLASS_PRESS_DATE_HEADING = 'p-press-release-list__heading'
CLASS_PRESS_RELEASE_BLOCK = 'p-press-release-list__block'
CLASS_PRESS_RELEASE_LINK = 'c-news-link__link'
CLASS_SOURCE_CATEGORY_TAG = 'p-news-link__tag'

SELECTOR_ARCHIVE_MONTH_LINK = f'.{CLASS_ARCHIVE_MONTH_LINK}'
SELECTOR_PRESS_DATE_HEADING = f'.{CLASS_PRESS_DATE_HEADING}'
SELECTOR_PRESS_RELEASE_BLOCK = f'.{CLASS_PRESS_RELEASE_BLOCK}'
SELECTOR_PRESS_RELEASE_LINK = f'.{CLASS_PRESS_RELEASE_LINK}'
SELECTOR_SOURCE_CATEGORY_TAG = f'.{CLASS_SOURCE_CATEGORY_TAG}'

_YEAR_PATTERN = r'(?P<year>\d{4})年'
_MONTH_PATTERN = r'(?P<month>0?[1-9]|1[0-2])月'
_DAY_PATTERN = r'(?P<day>0?[1-9]|[12]\d|3[01])日'

_DATE_HEADING_RE = re.compile(
    rf'{_YEAR_PATTERN}{_MONTH_PATTERN}{_DAY_PATTERN}発表'
)
_MONTH_LINK_RE = re.compile(rf'{_YEAR_PATTERN}{_MONTH_PATTERN}')

CrawlStopReason = Literal[
    'archive_month_limit_reached',
    'duplicate_release_detected',
    'archive_month_links_exhausted',
]
UrlValidationReason = Literal[
    'unsupported_scheme',
    'credentials_not_allowed',
    'non_ascii_character',
    'unsafe_character',
    'invalid_percent_escape',
    'invalid_host_or_port',
]


class _RequestRateLimiter:
    """HTTP要求の開始間隔を制御する内部rate limiter"""

    def __init__(
        self,
        interval_seconds: float = REQUEST_INTERVAL_SECONDS,
        *,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        """要求間隔と時刻・待機処理を保持

        Args:
            interval_seconds: 連続する要求開始の最小間隔
            clock: 経過時間の計測に使う単調増加時計
            sleeper: 不足時間の待機に使う関数
            progress: 待機と要求開始を通知する関数

        Raises:
            ValueError: 要求間隔が0秒以下の場合
        """

        if interval_seconds <= 0:
            raise ValueError(
                'interval_seconds must be greater than 0'
            )
        self._interval_seconds = interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._progress = progress
        self._first_request_started_at: float | None = None
        self._last_request_started_at: float | None = None
        self._request_count = 0

    def wait(self, target_url: str = '') -> None:
        """次のHTTP要求を開始できるまで待機

        Args:
            target_url: 次に要求を送るURL
        """

        request_number = self._request_count + 1
        while self._last_request_started_at is not None:
            elapsed_seconds = self._clock() - self._last_request_started_at
            remaining_seconds = self._interval_seconds - elapsed_seconds
            if remaining_seconds <= 0:
                break
            self._notify_progress(
                f'waiting {remaining_seconds:g}s before request '
                f'{request_number}: {target_url}'
            )
            self._sleeper(remaining_seconds)

        progress_time = self._clock()
        first_request_started_at = (
            self._first_request_started_at
            if self._first_request_started_at is not None
            else progress_time
        )
        elapsed_since_first = progress_time - first_request_started_at
        self._notify_progress(
            f'request {request_number} started at '
            f'+{elapsed_since_first:.3f}s: {target_url}'
        )
        request_started_at = self._clock()
        if self._first_request_started_at is None:
            self._first_request_started_at = request_started_at
        self._last_request_started_at = request_started_at
        self._request_count = request_number

    def _notify_progress(self, message: str) -> None:
        """設定されている場合だけ進捗を通知

        Args:
            message: 待機または要求開始の進捗メッセージ
        """

        if self._progress is not None:
            self._progress(message)


class _RateLimitedHTTPHandler(HTTPHandler):
    """HTTP送信直前に共有rate limiterを通すhandler"""

    def __init__(self, rate_limiter: _RequestRateLimiter) -> None:
        super().__init__()
        self._rate_limiter = rate_limiter

    def http_open(self, req: Request) -> Any:
        """HTTP要求を送信

        Args:
            req: 送信対象のHTTP Request

        Returns:
            HTTPレスポンス
        """

        self._rate_limiter.wait(req.full_url)
        return self.do_open(http.client.HTTPConnection, req)


class _RateLimitedHTTPSHandler(HTTPSHandler):
    """HTTPS送信直前に共有rate limiterを通すhandler"""

    def __init__(self, rate_limiter: _RequestRateLimiter) -> None:
        super().__init__()
        self._rate_limiter = rate_limiter

    def https_open(self, req: Request) -> Any:
        """HTTPS要求を送信

        Args:
            req: 送信対象のHTTPS Request

        Returns:
            HTTPSレスポンス
        """

        self._rate_limiter.wait(req.full_url)
        return self.do_open(
            http.client.HTTPSConnection,
            req,
            context=self._context,
        )


class _InvalidUrlError(ValueError):
    """URL検証の固定理由コードを保持する内部例外"""

    def __init__(self, reason: UrlValidationReason) -> None:
        """URL検証理由を保持

        Args:
            reason: URLを拒否した固定理由コード
        """

        self.reason = reason
        super().__init__(reason)


class InvalidFetchUrlError(ValueError):
    """HTTP取得対象URLが不正な場合の例外"""


class InvalidPressReleaseUrlError(ValueError):
    """報道発表詳細ページURLが不正な場合の例外"""


class InvalidArchiveMonthUrlError(ValueError):
    """月別アーカイブURLが不正な場合の例外"""


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    """同一オリジンのHTTPリダイレクトだけを許可するhandler"""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        """リダイレクト先を検証して次のRequestを生成

        Args:
            req: リダイレクト元のRequest
            fp: リダイレクト元のレスポンス
            code: HTTPステータスコード
            msg: HTTPステータスメッセージ
            headers: リダイレクト元のレスポンスヘッダー
            newurl: Locationヘッダーから解決された遷移先URL

        Returns:
            同一オリジンへのリダイレクトRequest

        Raises:
            HTTPError: 遷移先URLが不正または異なるオリジンの場合
        """

        try:
            redirect_url = _resolve_http_url(req.full_url, newurl)
        except _InvalidUrlError as exc:
            self._raise_redirect_error(
                fp,
                code,
                headers,
                newurl,
                exc.reason,
            )
        if not _has_same_origin(
            req.full_url,
            redirect_url,
        ):
            self._raise_redirect_error(
                fp,
                code,
                headers,
                newurl,
                'cross_origin',
            )
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            redirect_url,
        )

    @staticmethod
    def _raise_redirect_error(
        fp: Any,
        code: int,
        headers: Any,
        newurl: str,
        reason: str,
    ) -> NoReturn:
        """拒否するリダイレクトのレスポンスを閉じて例外を送出

        Args:
            fp: リダイレクト元のレスポンス
            code: HTTPステータスコード
            headers: リダイレクト元のレスポンスヘッダー
            newurl: 拒否したリダイレクト先URL
            reason: リダイレクトを拒否した固定理由コード

        Raises:
            HTTPError: リダイレクトを拒否する場合
        """

        if fp is not None:
            fp.close()
        raise HTTPError(
            newurl,
            code,
            f'{UNSAFE_REDIRECT_REASON}: validation={reason}',
            headers,
            None,
        )


@dataclass(frozen=True)
class PressRelease:
    """環境省の報道発表一覧ページから取得した報道発表

    Attributes:
        title: 報道発表のタイトル
        published_at: 報道発表日
        url: 報道発表詳細ページの絶対URL
        source_categories: 取得元ページに表示されているカテゴリ
    """

    title: str
    published_at: date
    url: str
    source_categories: tuple[str, ...]


@dataclass(frozen=True)
class ArchiveMonthLink:
    """環境省の報道発表一覧ページから取得した月別リンク

    Attributes:
        year: アーカイブ対象の年
        month: アーカイブ対象の月
        url: 月別アーカイブページの絶対URL
    """

    year: int
    month: int
    url: str


@dataclass(frozen=True)
class PressReleaseCrawlResult:
    """月別アーカイブページ巡回で取得した報道発表

    Attributes:
        releases: 月別アーカイブページから取得した報道発表
        archive_month_links: 巡回候補として抽出した月別リンク
        fetched_page_urls: 報道発表の取得対象として解析した月別ページURL
        stop_reason: 正常に巡回を終了した理由
    """

    releases: tuple[PressRelease, ...]
    archive_month_links: tuple[ArchiveMonthLink, ...]
    fetched_page_urls: tuple[str, ...]
    stop_reason: CrawlStopReason


class CrawlStateObserver(Protocol):
    """月別巡回のページ計画と解析状態を受け取るobserver"""

    def register_archive_pages(
        self,
        archive_links: tuple[ArchiveMonthLink, ...],
    ) -> None:
        """巡回対象の月別ページを登録

        Args:
            archive_links: 実際に巡回する年月降順の月別リンク
        """

        ...

    def mark_parsing(self, url: str) -> None:
        """ページ解析開始を記録

        Args:
            url: 解析を開始するページURL
        """

        ...

    def mark_parsed(self, url: str) -> None:
        """ページ解析成功を記録

        Args:
            url: 解析に成功したページURL
        """

        ...

    def mark_parse_failed(self, url: str, exc: Exception) -> None:
        """ページ解析失敗を記録

        Args:
            url: 解析に失敗したページURL
            exc: 解析処理が送出した例外
        """

        ...


def fetch_press_page_html(
    url: str = PRESS_INDEX_URL,
    timeout: float = 20.0,
    *,
    rate_limiter: _RequestRateLimiter | None = None,
) -> str:
    """報道発表ページのHTMLを取得

    Args:
        url: 取得対象のURL
        timeout: HTTPリクエストのタイムアウト秒数
        rate_limiter: 同じ取得処理内で共有する要求間隔制御

    Returns:
        レスポンスの文字コードに従ってデコードしたHTML

    Raises:
        InvalidFetchUrlError: 取得対象URLが取得条件を満たさない場合
    """

    try:
        validated_url = _resolve_http_url(url, '')
    except _InvalidUrlError as exc:
        raise InvalidFetchUrlError(
            'invalid fetch URL: '
            f'validation={exc.reason} '
            f'url={_diagnostic_value(url)}'
        ) from exc

    request = Request(
        validated_url,
        headers={USER_AGENT_HEADER: USER_AGENT},
    )
    rate_limiter = rate_limiter or _RequestRateLimiter()
    with _open_same_origin_url(
        request,
        timeout,
        rate_limiter=rate_limiter,
    ) as response:
        charset = response.headers.get_content_charset() or CHARSET
        return response.read().decode(charset, errors='replace')


def crawl_press_releases(
    start_url: str = PRESS_INDEX_URL,
    archive_month_limit: int = 0,
    all_archive_months: bool = False,
    fetcher: Callable[[str], str] | None = None,
    known_release_urls: Collection[str] | None = None,
    request_interval_seconds: float = REQUEST_INTERVAL_SECONDS,
    sleeper: Callable[[float], None] = sleep,
    progress: Callable[[str], None] | None = None,
    observer: CrawlStateObserver | None = None,
) -> PressReleaseCrawlResult:
    """月別アーカイブページを巡回して報道発表を取得

    Args:
        start_url: 月別リンクを抽出する報道発表一覧ページURL
        archive_month_limit: 取得する月別アーカイブページ数
        all_archive_months: 月別リンク候補をすべて巡回するかどうか
        fetcher: URLを受け取りHTMLを返す取得関数
        known_release_urls: 取得済みとして扱う報道発表詳細ページURL
        request_interval_seconds: HTTP要求開始の最小間隔
        sleeper: 不足する要求間隔の待機に使う関数
        progress: 月別ページの処理状況を通知する関数
        observer: ページ計画と解析状態を通知するobserver

    Returns:
        月別アーカイブページから取得した報道発表と巡回情報

    Raises:
        ValueError: 月別ページ数または待機秒数の指定が不正な場合
    """

    if archive_month_limit < 0:
        raise ValueError(
            'archive_month_limit must be greater than or equal to 0'
        )
    if all_archive_months and archive_month_limit > 0:
        raise ValueError(
            'archive_month_limit cannot be used with all_archive_months'
        )
    if request_interval_seconds <= 0:
        raise ValueError(
            'request_interval_seconds must be greater than 0'
        )
    if fetcher is None:
        rate_limiter = _RequestRateLimiter(
            interval_seconds=request_interval_seconds,
            sleeper=sleeper,
            progress=progress,
        )

        def fetcher(url: str) -> str:
            return fetch_press_page_html(
                url,
                rate_limiter=rate_limiter,
            )

    # 月別巡回では、index.htmlからは月別リンクだけを拾う。
    # 報道発表データは各月別ページから取得する。
    index_html = fetcher(start_url)
    if observer is not None:
        observer.mark_parsing(start_url)
    try:
        archive_month_links = parse_archive_month_links(
            index_html,
            base_url=start_url,
        )
    except Exception as exc:
        if observer is not None:
            observer.mark_parse_failed(start_url, exc)
        raise
    if observer is not None:
        observer.mark_parsed(start_url)
    unique_archive_links = _unique_archive_month_links(archive_month_links)
    selected_archive_links = _select_archive_month_links(
        archive_month_links,
        limit=None if all_archive_months else archive_month_limit,
    )
    if observer is not None:
        observer.register_archive_pages(tuple(selected_archive_links))

    releases: list[PressRelease] = []
    fetched_page_urls: list[str] = []
    known_urls = set(known_release_urls or set())
    # 同じ発表かどうかは、タイトルや日付ではなく詳細ページURLで判断する。
    seen_release_urls: set[str] = set(known_urls)
    stop_reason: CrawlStopReason | None = None

    archive_page_count = len(selected_archive_links)
    for page_number, archive_link in enumerate(
        selected_archive_links,
        start=1,
    ):
        if progress is not None:
            progress(
                f'archive page {page_number}/{archive_page_count}: '
                f'{archive_link.url}'
            )
        page_releases = _fetch_archive_page_releases(
            archive_link,
            fetcher,
            observer=observer,
        )
        fetched_page_urls.append(archive_link.url)

        # 新しい月から順に見るため、既知URLだけの月に着いたら
        # それより古い月も取得済みとみなして巡回を止める。
        if _contains_only_known_releases(page_releases, known_urls):
            stop_reason = 'duplicate_release_detected'
            break

        _append_unseen_releases(
            releases,
            page_releases,
            seen_release_urls,
        )

    # stop_reasonには正常に止まった理由だけを入れる。
    # 取得や解析の失敗は、ここでは止めずに呼び出し元へ伝える。
    if stop_reason is None:
        stop_reason = _crawl_stop_reason_after_selected_pages(
            selected_archive_links,
            unique_archive_links,
        )

    return PressReleaseCrawlResult(
        releases=tuple(releases),
        archive_month_links=tuple(archive_month_links),
        fetched_page_urls=tuple(fetched_page_urls),
        stop_reason=stop_reason,
    )


def parse_press_releases(
    html: str,
    base_url: str = BASE_URL,
) -> list[PressRelease]:
    """環境省の報道発表一覧HTMLから報道発表を抽出

    Args:
        html: 報道発表一覧ページのHTML
        base_url: 相対URLを絶対URLへ変換するための基準URL

    Returns:
        抽出した報道発表のリスト

    Raises:
        InvalidPressReleaseUrlError: 発表リンクのURLが保存条件を満たさない場合
    """

    soup = BeautifulSoup(html, PARSER)
    items: list[PressRelease] = []

    for block in soup.select(SELECTOR_PRESS_RELEASE_BLOCK):
        # 日付見出しがないブロックは、発表日の判断ができないため扱わない。
        heading = block.select_one(SELECTOR_PRESS_DATE_HEADING)
        if heading is None:
            continue

        published_at = _parse_heading_date(_tag_text(heading))
        if published_at is None:
            continue

        for link in block.select(SELECTOR_PRESS_RELEASE_LINK):
            title = _tag_text(link)
            href = _attr_value(link, ATTR_HREF)
            if not title or href is None:
                continue
            try:
                release_url = _resolve_http_url(base_url, href)
            except _InvalidUrlError as exc:
                raise InvalidPressReleaseUrlError(
                    'invalid press release URL: '
                    f'validation={exc.reason} '
                    f'page_url={_diagnostic_value(base_url)} '
                    f'title={_diagnostic_value(title)} '
                    f'href={_diagnostic_value(href)}'
                ) from exc

            items.append(
                PressRelease(
                    title=title,
                    published_at=published_at,
                    url=release_url,
                    source_categories=_source_categories_for_link(
                        link,
                        block,
                    ),
                )
            )

    return items


def parse_archive_month_links(
    html: str,
    base_url: str = BASE_URL,
) -> list[ArchiveMonthLink]:
    """環境省の報道発表一覧HTMLから月別リンクを抽出

    Args:
        html: 報道発表一覧ページのHTML
        base_url: 相対URLを絶対URLへ変換するための基準URL

    Returns:
        抽出した月別アーカイブリンクのリスト

    Raises:
        InvalidArchiveMonthUrlError: 月別リンクが巡回条件を満たさない場合
    """

    soup = BeautifulSoup(html, PARSER)
    items: list[ArchiveMonthLink] = []

    for link in soup.select(SELECTOR_ARCHIVE_MONTH_LINK):
        href = _attr_value(link, ATTR_HREF)
        aria_label = _attr_value(link, ATTR_ARIA_LABEL) or ''
        # 巡回順を決めるため、aria-labelの年月表記を使う。
        match = _MONTH_LINK_RE.fullmatch(aria_label)
        if href is None or match is None:
            continue
        try:
            archive_url = _resolve_http_url(base_url, href)
        except _InvalidUrlError as exc:
            raise InvalidArchiveMonthUrlError(
                'invalid archive month URL: '
                f'validation={exc.reason} '
                f'page_url={_diagnostic_value(base_url)} '
                f'archive_month={_year_month_label(match)} '
                f'href={_diagnostic_value(href)}'
            ) from exc
        if not _has_same_origin(
            base_url,
            archive_url,
        ):
            raise InvalidArchiveMonthUrlError(
                'invalid archive month URL: '
                'validation=cross_origin '
                f'page_url={_diagnostic_value(base_url)} '
                f'archive_month={_year_month_label(match)} '
                f'href={_diagnostic_value(href)}'
            )

        year = int(match.group('year'))
        month = int(match.group('month'))
        items.append(
            ArchiveMonthLink(
                year=year,
                month=month,
                url=archive_url,
            )
        )

    return items


def _fetch_archive_page_releases(
    archive_link: ArchiveMonthLink,
    fetcher: Callable[[str], str],
    *,
    observer: CrawlStateObserver | None = None,
) -> list[PressRelease]:
    """月別ページを取得して報道発表を抽出

    Args:
        archive_link: 取得対象の月別リンク
        fetcher: URLを受け取りHTMLを返す取得関数
        observer: ページ解析状態を通知するobserver

    Returns:
        月別ページから抽出した報道発表
    """

    html = fetcher(archive_link.url)
    if observer is not None:
        observer.mark_parsing(archive_link.url)
    try:
        releases = parse_press_releases(html, base_url=archive_link.url)
    except Exception as exc:
        if observer is not None:
            observer.mark_parse_failed(archive_link.url, exc)
        raise
    if observer is not None:
        observer.mark_parsed(archive_link.url)
    return releases


def _contains_only_known_releases(
    releases: list[PressRelease],
    known_release_urls: Collection[str],
) -> bool:
    """月別ページ内の発表がすべて取得済みか判定

    Args:
        releases: 月別ページから抽出した報道発表
        known_release_urls: 取得済みとして扱う報道発表詳細ページURL

    Returns:
        発表が1件以上あり、すべて取得済みURLの場合はTrue
    """

    return bool(releases) and all(
        release.url in known_release_urls for release in releases
    )


def _append_unseen_releases(
    destination: list[PressRelease],
    releases: list[PressRelease],
    seen_release_urls: set[str],
) -> None:
    """未見の報道発表だけを追加

    Args:
        destination: 追加先の報道発表リスト
        releases: 追加候補の報道発表
        seen_release_urls: 追加済みとして扱う報道発表詳細ページURL
    """

    for release in releases:
        if release.url in seen_release_urls:
            continue
        seen_release_urls.add(release.url)
        destination.append(release)


def _crawl_stop_reason_after_selected_pages(
    selected_archive_links: list[ArchiveMonthLink],
    archive_month_links: list[ArchiveMonthLink],
) -> CrawlStopReason:
    """選択済み月別ページを巡回し終えた場合の停止理由を判定

    Args:
        selected_archive_links: 実際に巡回対象として選んだ月別リンク
        archive_month_links: URL重複を除外した月別リンク候補

    Returns:
        月別ページ数上限または候補枯渇を表す停止理由
    """

    if len(selected_archive_links) < len(archive_month_links):
        return 'archive_month_limit_reached'
    return 'archive_month_links_exhausted'


def _unique_archive_month_links(
    archive_month_links: list[ArchiveMonthLink],
) -> list[ArchiveMonthLink]:
    """月別リンクの表示順を保ちながらURL重複を除外

    Args:
        archive_month_links: 月別リンク候補

    Returns:
        URL重複を除外した月別リンク
    """

    items: list[ArchiveMonthLink] = []
    seen_urls: set[str] = set()

    for link in archive_month_links:
        # 同じ月別ページが複数箇所に出ても、取得は1回だけにする。
        if link.url in seen_urls:
            continue
        seen_urls.add(link.url)
        items.append(link)

    return items


def _select_archive_month_links(
    archive_month_links: list[ArchiveMonthLink],
    limit: int | None,
) -> list[ArchiveMonthLink]:
    """年月の新しい順で巡回対象の月別リンクを選択

    Args:
        archive_month_links: 月別リンク候補
        limit: 返す月別リンク数、Noneの場合は全件

    Returns:
        URL重複を除外し、年月降順に並べた月別リンク
    """

    unique_links = _unique_archive_month_links(archive_month_links)
    # HTML上の並びに依存せず、年月の新しい順に巡回する。
    latest_first_links = sorted(
        unique_links,
        key=lambda link: (link.year, link.month),
        reverse=True,
    )
    if limit is None:
        return latest_first_links
    return latest_first_links[:limit]


def _resolve_http_url(base_url: str, href: str) -> str:
    """相対URLをHTTPまたはHTTPSの絶対URLへ変換

    Args:
        base_url: 相対URLを解決する基準URL
        href: HTMLのhref属性値

    Returns:
        HTTPまたはHTTPSの絶対URL

    Raises:
        _InvalidUrlError: URLが保存・取得条件を満たさない場合
    """

    for value in (base_url, href):
        reason = _unsafe_url_reason(value)
        if reason is not None:
            raise _InvalidUrlError(reason)

    try:
        resolved_url = urljoin(base_url, href)
        parsed_url = urlsplit(resolved_url)
        _ = parsed_url.port
    except ValueError as exc:
        raise _InvalidUrlError('invalid_host_or_port') from exc

    if parsed_url.scheme.lower() not in HTTP_URL_SCHEMES:
        raise _InvalidUrlError('unsupported_scheme')
    if parsed_url.username is not None or parsed_url.password is not None:
        raise _InvalidUrlError('credentials_not_allowed')
    if parsed_url.hostname is None or '%' in parsed_url.netloc:
        raise _InvalidUrlError('invalid_host_or_port')
    return resolved_url


def _unsafe_url_reason(value: str) -> UrlValidationReason | None:
    """ASCII URIとして扱わない理由を判定

    Args:
        value: URLまたはhref属性値

    Returns:
        URLを拒否する固定理由コード、有効な文字列の場合はNone
    """

    if not value.isascii():
        return 'non_ascii_character'
    if any(
        character.isspace()
        or ord(character) < 0x20
        or ord(character) == 0x7F
        or character in UNSAFE_ASCII_URL_CHARACTERS
        for character in value
    ):
        return 'unsafe_character'
    if INVALID_PERCENT_ESCAPE_RE.search(value) is not None:
        return 'invalid_percent_escape'
    return None


def _diagnostic_value(value: str) -> str:
    """エラー表示用の値を伏字・1行・最大長付きで整形

    Args:
        value: エラーの調査情報として表示する値

    Returns:
        認証情報を伏せて1行へ正規化した文字列
    """

    redacted_value = CREDENTIALS_IN_URL_RE.sub(
        r'\1[redacted]@',
        value,
    )
    one_line_value = ' '.join(redacted_value.split())
    rendered_value = repr(one_line_value)
    if len(rendered_value) > MAX_DIAGNOSTIC_VALUE_LENGTH:
        rendered_value = (
            rendered_value[:MAX_DIAGNOSTIC_VALUE_LENGTH - 4]
            + '...'
            + rendered_value[0]
        )
    return rendered_value


def _year_month_label(match: re.Match[str]) -> str:
    """月別リンクの正規表現結果を年月表示へ変換

    Args:
        match: 月別リンクのaria-labelに一致した正規表現結果

    Returns:
        `YYYY-MM` 形式の年月
    """

    return f"{int(match.group('year')):04}-{int(match.group('month')):02}"


def _has_same_origin(base_url: str, target_url: str) -> bool:
    """2つのURLが同一オリジンか判定

    Args:
        base_url: 比較基準のURL
        target_url: 比較対象のURL

    Returns:
        スキーム、ホスト、ポートが一致する場合はTrue
    """

    base_origin = _url_origin(base_url)
    target_origin = _url_origin(target_url)
    return base_origin is not None and base_origin == target_origin


def _url_origin(url: str) -> tuple[str, str, int] | None:
    """URLから同一オリジン判定用の値を取得

    Args:
        url: 判定対象のURL

    Returns:
        スキーム、ホスト、ポートの組、不正なURLの場合はNone
    """

    try:
        parsed_url = urlsplit(url)
        scheme = parsed_url.scheme.lower()
        hostname = parsed_url.hostname
        if scheme not in HTTP_URL_SCHEMES or hostname is None:
            return None
        port = parsed_url.port
    except ValueError:
        return None

    if port is None:
        port = 443 if scheme == 'https' else 80
    return scheme, hostname, port


def _open_same_origin_url(
    request: Request,
    timeout: float,
    *,
    rate_limiter: _RequestRateLimiter,
) -> Any:
    """同一オリジンのリダイレクトだけを許可してURLを開く

    Args:
        request: 取得対象のHTTP Request
        timeout: HTTPリクエストのタイムアウト秒数
        rate_limiter: 初回要求とredirect先で共有する要求間隔制御

    Returns:
        context managerとして利用できるHTTPレスポンス
    """

    opener = build_opener(
        _SameOriginRedirectHandler(),
        _RateLimitedHTTPHandler(rate_limiter),
        _RateLimitedHTTPSHandler(rate_limiter),
    )
    return opener.open(request, timeout=timeout)


def _attr_value(tag: Tag, name: str) -> str | None:
    """BeautifulSoupの属性値を文字列として取得

    Args:
        tag: 属性を取得するHTMLタグ
        name: 取得する属性名

    Returns:
        文字列化した属性値、属性がない場合はNone
    """

    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, AttributeValueList):
        return ' '.join(str(part) for part in value)
    return None


def _normalize_text(value: str) -> str:
    """スクレイピングした文字列の連続空白を1つに整理

    Args:
        value: 正規化する文字列

    Returns:
        連続空白を整理した文字列
    """

    return ' '.join(value.split())


def _tag_text(tag: Tag) -> str:
    """HTMLタグから表示テキストを抽出して正規化

    Args:
        tag: テキストを抽出するHTMLタグ

    Returns:
        正規化した表示テキスト
    """

    return _normalize_text(tag.get_text(separator=' ', strip=True))


def _source_categories_for_link(link: Tag, block: Tag) -> tuple[str, ...]:
    """報道発表リンクに対応する取得元カテゴリを抽出

    Args:
        link: 報道発表詳細ページへのリンク
        block: 日付ごとの報道発表ブロック

    Returns:
        リンクに近い発表要素内のカテゴリ一覧
    """

    container = _press_release_container(link, block)
    return tuple(
        category
        for tag in container.select(SELECTOR_SOURCE_CATEGORY_TAG)
        if (category := _tag_text(tag))
    )


def _press_release_container(link: Tag, block: Tag) -> Tag:
    """報道発表リンクに対応する最小のHTML要素を取得

    Args:
        link: 報道発表詳細ページへのリンク
        block: 日付ごとの報道発表ブロック

    Returns:
        リンクを含むli要素、見つからない場合はリンク自身
    """

    for parent in link.parents:
        if parent is block:
            break
        if isinstance(parent, Tag) and parent.name == 'li':
            return parent

    return link


def _parse_heading_date(value: str) -> date | None:
    """報道発表日の見出し文字列から日付を抽出

    Args:
        value: 報道発表日の見出し文字列

    Returns:
        抽出した日付、無効な日付の場合はNone
    """

    match = _DATE_HEADING_RE.fullmatch(value)
    if not match:
        return None

    year = int(match.group('year'))
    month = int(match.group('month'))
    day = int(match.group('day'))

    try:
        return date(year, month, day)
    except ValueError:
        return None
