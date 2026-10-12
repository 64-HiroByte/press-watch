"""scraper unittestで共有するテスト用URLと診断の合成値"""

EXAMPLE_BASE_URL = 'https://example.com'
EXAMPLE_INDEX_URL = f'{EXAMPLE_BASE_URL}/press/index.html'
MAY_ARCHIVE_PATH = '/press/202605.html'
EXAMPLE_MAY_ARCHIVE_URL = f'{EXAMPLE_BASE_URL}{MAY_ARCHIVE_PATH}'
EXAMPLE_APRIL_ARCHIVE_URL = f'{EXAMPLE_BASE_URL}/press/202604.html'
EXAMPLE_MAY_RELEASE_URL = f'{EXAMPLE_BASE_URL}/press/may.html'
ENV_HOST = 'www.env.go.jp'
ENV_ORIGIN_URL = f'https://{ENV_HOST}'

# 製品の伏字処理から期待値を作らず、入力と期待する出力を独立して保持する。
DIAGNOSTIC_SAFE_URL = 'https://safe.test'
DIAGNOSTIC_USERNAME = 'review-user'
DIAGNOSTIC_PASSWORD = 'review-secret'
DIAGNOSTIC_CREDENTIAL_URL = (
    f'//{DIAGNOSTIC_USERNAME}:{DIAGNOSTIC_PASSWORD}@host/path'
)
DIAGNOSTIC_REDACTED_URL = '//[redacted]@host/path'
