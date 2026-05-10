"""スクレイパーパッケージをCLIとして実行する入口"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

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
        help='Number of archive month pages to fetch after the index page.',
    )
    parser.add_argument(
        '--all-archive-months',
        action='store_true',
        help='Fetch all archive month pages found on the index page.',
    )
    args = parser.parse_args()

    archive_month_limit = args.archive_month_limit
    if archive_month_limit is not None and archive_month_limit < 0:
        parser.error(
            '--archive-month-limit must be greater than or equal to 0.'
        )
    if args.from_file is not None and args.all_archive_months:
        parser.error('--from-file cannot be used with --all-archive-months.')
    has_archive_month_limit = (
        archive_month_limit is not None and archive_month_limit > 0
    )
    if args.from_file is not None and has_archive_month_limit:
        parser.error('--from-file cannot be used with --archive-month-limit.')
    if args.all_archive_months and archive_month_limit is not None:
        parser.error(
            '--archive-month-limit cannot be used with --all-archive-months.'
        )

    error_target = (
        str(args.from_file) if args.from_file is not None else args.url
    )

    # 成功時だけJSONをstdoutへ出す。途中で失敗した場合は、
    # 途中結果を出さずにstderrと終了コードで失敗を伝える。
    try:
        archive_month_limit_value = archive_month_limit or 0
        if args.all_archive_months or archive_month_limit_value > 0:
            source_url = args.url

            def fetcher(url: str) -> str:
                nonlocal error_target

                # 取得に失敗したとき、stderrへそのURLを表示できるようにする。
                error_target = url
                return fetch_press_index_html(url)

            crawl_result = crawl_press_releases(
                start_url=args.url,
                archive_month_limit=archive_month_limit_value,
                all_archive_months=args.all_archive_months,
                fetcher=fetcher,
            )
            releases = crawl_result.releases
            archive_month_links = crawl_result.archive_month_links
            fetched_page_urls = crawl_result.fetched_page_urls
            stop_reason = crawl_result.stop_reason
        elif args.from_file is not None:
            html = args.from_file.read_text(encoding=CHARSET)
            source_url = str(args.from_file)
            base_url = PRESS_INDEX_URL
            releases = parse_press_releases(html, base_url=base_url)
            archive_month_links = parse_archive_month_links(
                html,
                base_url=base_url,
            )
            fetched_page_urls: list[str] = []
            stop_reason = None
        else:
            html = fetch_press_index_html(args.url)
            source_url = args.url
            base_url = args.url
            releases = parse_press_releases(html, base_url=base_url)
            archive_month_links = parse_archive_month_links(
                html,
                base_url=base_url,
            )
            fetched_page_urls = [source_url]
            stop_reason = None

        items = [
            {
                **asdict(item),
                'published_at': item.published_at.isoformat(),
            }
            for item in releases
        ]
        archive_month_link_items = [
            asdict(item) for item in archive_month_links
        ]

        print(
            json.dumps(
                {
                    'source_url': source_url,
                    'count': len(releases),
                    'archive_month_link_count': len(archive_month_links),
                    'archive_month_links': archive_month_link_items,
                    'fetched_page_urls': fetched_page_urls,
                    'stop_reason': stop_reason,
                    'items': items,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        _print_runtime_error(error_target, exc)
        return 1


def _print_runtime_error(target: str, exc: Exception) -> None:
    """実行時エラーをCLI向けの簡潔な形式でstderrへ出力"""

    # 例外メッセージに改行が含まれても、stderrでは1行で読める形にする。
    reason = ' '.join(str(exc).split()) or 'no detail'
    print(
        (
            'error: '
            f'target={target} '
            f'exception={type(exc).__name__} '
            f'reason={reason}'
        ),
        file=sys.stderr,
    )


if __name__ == '__main__':
    raise SystemExit(main())
