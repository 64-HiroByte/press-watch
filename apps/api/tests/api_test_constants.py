"""API unittest で共有するテスト用定数"""

ENV_PRESS_BASE_URL = "https://www.env.go.jp/press"
ENV_PRESS_INDEX_URL = f"{ENV_PRESS_BASE_URL}/index.html"
ENV_PRESS_RELEASE_URL_1 = f"{ENV_PRESS_BASE_URL}/press_00001.html"
ENV_PRESS_RELEASE_URL_2 = f"{ENV_PRESS_BASE_URL}/press_00002.html"
ENV_PRESS_RELEASE_URL_3 = f"{ENV_PRESS_BASE_URL}/press_00003.html"

# 製品側の定数変更による契約違反を検出するため、独立した期待値を保持する。
EXPECTED_MAX_FIXED_CATEGORY_COUNT = 20
EXPECTED_MAX_FIXED_CATEGORY_LENGTH = 100
