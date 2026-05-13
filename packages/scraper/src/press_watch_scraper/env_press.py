from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date
import re
from time import sleep
from typing import Literal
from urllib.parse import urljoin
from urllib.request import Request, urlopen

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


def fetch_press_index_html(
    url: str = PRESS_INDEX_URL,
    timeout: float = 20.0,
) -> str:
    """報道発表一覧ページのHTMLを取得

    Args:
        url: 取得対象のURL
        timeout: HTTPリクエストのタイムアウト秒数

    Returns:
        レスポンスの文字コードに従ってデコードしたHTML
    """

    request = Request(url, headers={USER_AGENT_HEADER: USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or CHARSET
        return response.read().decode(charset, errors='replace')


def crawl_press_releases(
    start_url: str = PRESS_INDEX_URL,
    archive_month_limit: int = 0,
    all_archive_months: bool = False,
    fetcher: Callable[[str], str] = fetch_press_index_html,
    known_release_urls: Collection[str] | None = None,
    request_interval_seconds: float = REQUEST_INTERVAL_SECONDS,
    sleeper: Callable[[float], None] = sleep,
) -> PressReleaseCrawlResult:
    """月別アーカイブページを巡回して報道発表を取得

    Args:
        start_url: 月別リンクを抽出する報道発表一覧ページURL
        archive_month_limit: 取得する月別アーカイブページ数
        all_archive_months: 月別リンク候補をすべて巡回するかどうか
        fetcher: URLを受け取りHTMLを返す取得関数
        known_release_urls: 取得済みとして扱う報道発表詳細ページURL
        request_interval_seconds: ページ取得の間に空ける秒数
        sleeper: 待機処理を行う関数

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

    # 月別巡回では、index.htmlからは月別リンクだけを拾う。
    # 報道発表データは各月別ページから取得する。
    index_html = fetcher(start_url)
    archive_month_links = parse_archive_month_links(
        index_html,
        base_url=start_url,
    )
    unique_archive_links = _unique_archive_month_links(archive_month_links)
    selected_archive_links = _select_archive_month_links(
        archive_month_links,
        limit=None if all_archive_months else archive_month_limit,
    )

    releases: list[PressRelease] = []
    fetched_page_urls: list[str] = []
    known_urls = set(known_release_urls or set())
    # 同じ発表かどうかは、タイトルや日付ではなく詳細ページURLで判断する。
    seen_release_urls: set[str] = set(known_urls)
    stop_reason: CrawlStopReason | None = None

    for archive_link in selected_archive_links:
        # 環境省サイトへ連続アクセスしないよう、ページ取得の間隔を空ける。
        sleeper(request_interval_seconds)

        page_releases = _fetch_archive_page_releases(
            archive_link,
            fetcher,
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

            items.append(
                PressRelease(
                    title=title,
                    published_at=published_at,
                    url=urljoin(base_url, href),
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

        year = int(match.group('year'))
        month = int(match.group('month'))
        items.append(
            ArchiveMonthLink(
                year=year,
                month=month,
                url=urljoin(base_url, href),
            )
        )

    return items


def _fetch_archive_page_releases(
    archive_link: ArchiveMonthLink,
    fetcher: Callable[[str], str],
) -> list[PressRelease]:
    """月別ページを取得して報道発表を抽出

    Args:
        archive_link: 取得対象の月別リンク
        fetcher: URLを受け取りHTMLを返す取得関数

    Returns:
        月別ページから抽出した報道発表
    """

    html = fetcher(archive_link.url)
    return parse_press_releases(html, base_url=archive_link.url)


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
