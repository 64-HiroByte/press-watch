const { readFileSync } = require("node:fs");
const NativeDate = Date;

// 日跨ぎテスト中だけNext.jsの時刻を変え、通信期限用の時間は進め続ける。
function now() {
  try {
    const clock = JSON.parse(readFileSync(process.env.PRESSWATCH_TEST_CLOCK_FILE, "utf8"));
    return clock.now + NativeDate.now() - clock.startedAt;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    return NativeDate.now();
  }
}

global.Date = class extends NativeDate {
  constructor(...args) {
    super(...(args.length ? args : [now()]));
  }
  static now() {
    return now();
  }
};
