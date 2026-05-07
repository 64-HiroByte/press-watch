"""スクレイパーパッケージをCLIとして実行する入口"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .env_press import (
    CHARSET,
    PRESS_INDEX_URL,
    crawl_press_releases,
    fetch_press_index_html,
    parse_archive_month_links,
    parse_press_releases,
)


def main() -> int:
    """報道発表一覧HTMLを取得または読み込み、解析結果をJSONで出力

    Returns:
        正常終了時の終了コード
    """

    parser = argparse.ArgumentParser(
        description='Fetch one Ministry of the Environment press list page.',
    )
    parser.add_argument(
        '--url',
        default=PRESS_INDEX_URL,
        help='Press list page URL to fetch.',
    )
    parser.add_argument(
        '--from-file',
        type=Path,
        help='Parse a saved HTML file instead of fetching.',
    )
    parser.add_argument(
        '--archive-month-limit',
        type=int,
        default=0,
        help='Number of archive month pages to fetch after the index page.',
    )
    args = parser.parse_args()

    if args.archive_month_limit < 0:
        parser.error(
            '--archive-month-limit must be greater than or equal to 0.'
        )
    if args.from_file is not None and args.archive_month_limit > 0:
        parser.error('--from-file cannot be used with --archive-month-limit.')

    if args.archive_month_limit > 0:
        source_url = args.url
        crawl_result = crawl_press_releases(
            start_url=args.url,
            archive_month_limit=args.archive_month_limit,
            fetcher=fetch_press_index_html,
        )
        releases = crawl_result.releases
        archive_month_links = crawl_result.archive_month_links
        fetched_page_urls = crawl_result.fetched_page_urls
    elif args.from_file is not None:
        html = args.from_file.read_text(encoding=CHARSET)
        source_url = str(args.from_file)
        base_url = PRESS_INDEX_URL
        releases = parse_press_releases(html, base_url=base_url)
        archive_month_links = parse_archive_month_links(html, base_url=base_url)
        fetched_page_urls: list[str] = []
    else:
        html = fetch_press_index_html(args.url)
        source_url = args.url
        base_url = args.url
        releases = parse_press_releases(html, base_url=base_url)
        archive_month_links = parse_archive_month_links(html, base_url=base_url)
        fetched_page_urls = [source_url]

    items = [
        {
            **asdict(item),
            'published_at': item.published_at.isoformat(),
        }
        for item in releases
    ]
    archive_month_link_items = [asdict(item) for item in archive_month_links]

    print(
        json.dumps(
            {
                'source_url': source_url,
                'count': len(releases),
                'archive_month_link_count': len(archive_month_links),
                'archive_month_links': archive_month_link_items,
                'fetched_page_urls': fetched_page_urls,
                'items': items,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
