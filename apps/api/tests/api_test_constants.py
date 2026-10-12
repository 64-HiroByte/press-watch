"""API unittest で共有するテスト用定数"""

ENV_ORIGIN_URL = "https://www.env.go.jp"
ENV_PRESS_BASE_URL = f"{ENV_ORIGIN_URL}/press"
ENV_PRESS_INDEX_URL = f"{ENV_PRESS_BASE_URL}/index.html"
ENV_PRESS_RELEASE_URL_1 = f"{ENV_PRESS_BASE_URL}/press_00001.html"
ENV_PRESS_RELEASE_URL_2 = f"{ENV_PRESS_BASE_URL}/press_00002.html"
ENV_PRESS_RELEASE_URL_3 = f"{ENV_PRESS_BASE_URL}/press_00003.html"

EXAMPLE_BASE_URL = "https://example.com"

# 製品の伏字処理から期待値を作らず、入力と期待する出力を独立して保持する。
DIAGNOSTIC_SAFE_URL = "https://safe.test"
DIAGNOSTIC_USERNAME = "review-user"
DIAGNOSTIC_PASSWORD = "review-secret"
DIAGNOSTIC_CREDENTIAL_URL = (
    f"//{DIAGNOSTIC_USERNAME}:{DIAGNOSTIC_PASSWORD}@host/path"
)
DIAGNOSTIC_REDACTED_URL = "//[redacted]@host/path"

# 入力の制御文字と、診断の一行化後に保持する接頭辞を独立した期待値で示す。
DIAGNOSTIC_URL_PREFIX_CASES = (
    ("https://", "https://"),
    ("//", "//"),
    ("HTTP://", "HTTP://"),
    ("https:/\n/", "https:/ /"),
    ("https:/\r/", "https:/ /"),
    ("https:/\t/", "https:/ /"),
    ("http:\t//", "http: //"),
    ("/\r\n/", "/ /"),
    ("h\tt\nt\rps:\r/\t/", "h t t ps: / /"),
)

# HTML解析でCR・CRLFはLFとなる。診断では解析後の制御文字をエスケープ表記で保持する。
DIAGNOSTIC_HTML_URL_PREFIX_CASES = (
    ("https://", "https://"),
    ("//", "//"),
    ("HTTP://", "HTTP://"),
    ("https:/\n/", r"https:/\n/"),
    ("https:/\r/", r"https:/\n/"),
    ("https:/\t/", r"https:/\t/"),
    ("http:\t//", r"http:\t//"),
    ("/\r\n/", r"/\n/"),
    ("h\tt\nt\rps:\r/\t/", r"h\tt\nt\nps:\n/\t/"),
)

# 製品側の定数変更による契約違反を検出するため、独立した期待値を保持する。
EXPECTED_MAX_FIXED_CATEGORY_COUNT = 20
EXPECTED_MAX_FIXED_CATEGORY_LENGTH = 100
