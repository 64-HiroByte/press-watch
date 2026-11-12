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

const rateLimitClockFile = process.env.PRESSWATCH_TEST_RATE_LIMIT_CLOCK_FILE;
if (rateLimitClockFile) {
  const performanceNow = performance.now.bind(performance);
  Object.defineProperty(performance, "now", {
    value() {
      try {
        const clock = JSON.parse(readFileSync(rateLimitClockFile, "utf8"));
        return clock.now ?? performanceNow() + clock.offset;
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
        return performanceNow();
      }
    },
  });
}
