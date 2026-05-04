from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .env_press import (
    PRESS_INDEX_URL,
    fetch_press_index_html,
    parse_archive_month_links,
    parse_press_releases,
)


def main() -> int:
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
        '--limit',
        type=int,
        default=5,
        help='Number of parsed items to print.',
    )
    args = parser.parse_args()

    if args.from_file is not None:
        html = args.from_file.read_text(encoding='utf-8')
        source_url = str(args.from_file)
    else:
        html = fetch_press_index_html(args.url)
        source_url = args.url

    releases = parse_press_releases(html)
    archive_month_links = parse_archive_month_links(html)
    items = [
        {
            **asdict(item),
            'published_at': item.published_at.isoformat(),
        }
        for item in releases[: max(args.limit, 0)]
    ]

    print(
        json.dumps(
            {
                'source_url': source_url,
                'count': len(releases),
                'archive_month_link_count': len(archive_month_links),
                'items': items,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
