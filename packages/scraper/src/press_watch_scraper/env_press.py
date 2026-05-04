from __future__ import annotations

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

SELECTOR_ARCHIVE_MONTH_LINK = f'.{CLASS_ARCHIVE_MONTH_LINK}'
SELECTOR_PRESS_DATE_HEADING = f'.{CLASS_PRESS_DATE_HEADING}'
SELECTOR_PRESS_RELEASE_BLOCK = f'.{CLASS_PRESS_RELEASE_BLOCK}'
SELECTOR_PRESS_RELEASE_LINK = f'.{CLASS_PRESS_RELEASE_LINK}'

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
    """

    title: str
    published_at: date
    url: str


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
