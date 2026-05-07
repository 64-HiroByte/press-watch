from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import re
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
    """

    releases: tuple[PressRelease, ...]
    archive_month_links: tuple[ArchiveMonthLink, ...]
    fetched_page_urls: tuple[str, ...]


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
    fetcher: Callable[[str], str] = fetch_press_index_html,
) -> PressReleaseCrawlResult:
    """月別アーカイブページを指定件数だけ巡回して報道発表を取得

    Args:
        start_url: 月別リンクを抽出する報道発表一覧ページURL
        archive_month_limit: 取得する月別アーカイブページ数
        fetcher: URLを受け取りHTMLを返す取得関数

    Returns:
        月別アーカイブページから取得した報道発表と巡回情報

    Raises:
        ValueError: archive_month_limitが負の場合
    """

    if archive_month_limit < 0:
        raise ValueError(
            'archive_month_limit must be greater than or equal to 0'
        )

    index_html = fetcher(start_url)
    archive_month_links = parse_archive_month_links(
        index_html,
        base_url=start_url,
    )
    selected_archive_links = _unique_archive_month_links(
        archive_month_links,
        limit=archive_month_limit,
    )

    releases: list[PressRelease] = []
    fetched_page_urls: list[str] = []
    seen_release_urls: set[str] = set()

    for archive_link in selected_archive_links:
        html = fetcher(archive_link.url)
        fetched_page_urls.append(archive_link.url)

        for release in parse_press_releases(html, base_url=archive_link.url):
            if release.url in seen_release_urls:
                continue
            seen_release_urls.add(release.url)
            releases.append(release)

    return PressReleaseCrawlResult(
        releases=tuple(releases),
        archive_month_links=tuple(archive_month_links),
        fetched_page_urls=tuple(fetched_page_urls),
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


def _unique_archive_month_links(
    archive_month_links: list[ArchiveMonthLink],
    limit: int,
) -> list[ArchiveMonthLink]:
    """月別リンクの表示順を保ちながらURL重複を除外

    Args:
        archive_month_links: 月別リンク候補
        limit: 返す月別リンク数

    Returns:
        URL重複を除外した月別リンク
    """

    items: list[ArchiveMonthLink] = []
    seen_urls: set[str] = set()

    for link in archive_month_links:
        if len(items) >= limit:
            break
        if link.url in seen_urls:
            continue
        seen_urls.add(link.url)
        items.append(link)

    return items


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
