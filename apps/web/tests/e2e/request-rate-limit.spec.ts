import { expect, test } from "@playwright/test";
import { testBasicAuth } from "../support/basic-auth";
import {
  advanceFixedRateLimitClock,
  fixedClockFile,
  setRateLimitClock,
} from "../support/rate-limit-clock";

const control = "http://127.0.0.1:3107";
const burstCapacity = 10;
const oneTokenMillis = 1_000;

test("一覧の共有枠を超えた要求は描画前に拒否し、補充後に画面へ戻れる", async ({
  baseURL,
  page,
  request,
}) => {
  const startedAt = await advanceFixedRateLimitClock(burstCapacity * oneTokenMillis);
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
  const token = Buffer.from(`${testBasicAuth.username}:${testBasicAuth.password}`).toString(
    "base64",
  );
  const authorization = `Basic ${token}`;
  expect((await page.goto("/"))?.status()).toBe(200);
  const search = page.getByRole("button", { name: "検索", exact: true });
  await expect(search).toBeEnabled();

  // 初回HTMLと先読み1件の残りを通常の一覧要求で埋める。
  const prefetch = await fetch(`${baseURL}/?_rsc=rate-limit-prefetch`, {
    redirect: "manual",
    headers: { authorization, rsc: "1", "next-router-prefetch": "1" },
  });
  expect(prefetch.status).toBeLessThan(400);
  await prefetch.arrayBuffer();
  for (let index = 0; index < burstCapacity - 2; index++) {
    const allowed = await fetch(`${baseURL}/`, {
      headers: { authorization, "x-forwarded-for": `192.0.2.${index + 1}` },
    });
    expect(allowed.status).toBe(200);
    await allowed.arrayBuffer();
  }

  const calls = await (await request.get(`${control}/__requests`)).json();
  const rejected = await fetch(`${baseURL}/`, {
    headers: { authorization, "x-forwarded-for": "198.51.100.1", forwarded: "for=203.0.113.1" },
  });
  expect(rejected.status).toBe(429);
  expect(rejected.headers.get("retry-after")).toBe("1");
  expect(rejected.headers.get("cache-control")).toBe("private, no-store");

  expect((await fetch(`${baseURL}/`)).status).toBe(401);
  expect((await fetch(`${baseURL}/health`)).status).toBe(200);
  expect((await fetch(`${baseURL}/third-party-notices.txt`)).status).toBe(401);
  expect(
    (await fetch(`${baseURL}/third-party-notices.txt`, { headers: { authorization } })).status,
  ).toBe(200);

  const rsc = page.waitForResponse(
    (response) => response.request().headers().rsc === "1" && response.url().includes("q=limited"),
  );
  const document = page.waitForResponse(
    (response) => response.request().isNavigationRequest() && response.url().includes("q=limited"),
  );
  await page.getByLabel("キーワード", { exact: true }).fill("limited");
  await search.click();
  expect((await rsc).status()).toBe(429);
  expect((await document).status()).toBe(429);
  await expect(
    page.getByText("リクエストが集中しています。少し待ってから再試行してください。"),
  ).toBeVisible();
  expect(await (await request.get(`${control}/__requests`)).json()).toEqual(calls);

  await setRateLimitClock(fixedClockFile, { now: startedAt + oneTokenMillis });
  expect((await page.reload())?.status()).toBe(200);
  await expect(search).toBeEnabled();
});
