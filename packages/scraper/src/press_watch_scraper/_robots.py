"""単一の共通User-agentに対するrobots.txtの限定的な解析"""

import re
from urllib.robotparser import RobotFileParser


class RobotsCheckError(RuntimeError):
    """robotsの禁止または確認不能を表す例外"""


def parse_robots(body: bytes) -> RobotFileParser:
    """対応する行だけを検証・整理して標準パーサーで解析

    Args:
        body: UTF-8のrobots.txt本文

    Returns:
        共通User-agentの禁止ルールを保持するパーサー

    Raises:
        RobotsCheckError: 本文が不正または未対応の形式の場合
    """
    try:
        text = body.decode('utf-8-sig')
    except UnicodeError as exc:
        raise RobotsCheckError('robots check failed: invalid UTF-8') from exc
    lines: list[str] = []
    seen_agent = False
    for raw_line in text.splitlines():
        line = raw_line.partition('#')[0].strip()
        if not line:
            continue
        field, separator, value = line.partition(':')
        field, value = field.strip().lower(), value.strip()
        if not separator:
            raise RobotsCheckError('robots check failed: invalid directive')
        if field == 'user-agent':
            if seen_agent or value != '*':
                raise RobotsCheckError('robots check failed: unsupported user-agent group')
            seen_agent = True
            lines.append('User-agent: *')
        elif field == 'disallow':
            if not seen_agent:
                raise RobotsCheckError('robots check failed: rule without user-agent')
            if not value:
                continue
            if (
                not value.startswith('/')
                or any(
                    char.isspace()
                    or ord(char) < 32
                    or ord(char) == 127
                    or char in '*$'
                    for char in value
                )
                or re.search(r'%(?![0-9a-fA-F]{2})', value)
            ):
                raise RobotsCheckError('robots check failed: unsupported disallow path')
            lines.append(f'Disallow: {value}')
        elif field in {'sitemap', 'crawl-delay', 'request-rate'}:
            continue
        else:
            raise RobotsCheckError('robots check failed: unsupported directive')
    parser = RobotFileParser()
    parser.parse(lines)
    return parser
