import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export const smokeClockFile = resolve("../../tmp/playwright/rate-limit-smoke-clock.json");
export const fixedClockFile = resolve("../../tmp/playwright/rate-limit-fixed-clock.json");
const initialFixedTime = 1_000_000;

export async function setRateLimitClock(file: string, clock: { offset: number } | { now: number }) {
  await mkdir(dirname(file), { recursive: true });
  await writeFile(`${file}.tmp`, JSON.stringify(clock));
  await rename(`${file}.tmp`, file);
}

export async function advanceFixedRateLimitClock(milliseconds: number) {
  let previousTime = initialFixedTime;
  try {
    ({ now: previousTime } = JSON.parse(await readFile(fixedClockFile, "utf8")));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  const now = previousTime + milliseconds;
  await setRateLimitClock(fixedClockFile, { now });
  return now;
}

export async function refillSmokeBucket() {
  let offset = 0;
  try {
    ({ offset } = JSON.parse(await readFile(smokeClockFile, "utf8")));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  // 現在の時計からWebの10件分が補充される時間だけ進める。
  await setRateLimitClock(smokeClockFile, { offset: offset + 10_000 });
}
