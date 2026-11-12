import { expect, test } from "../support/production-test";
import { testBasicAuth } from "../support/basic-auth";

const control = "http://127.0.0.1:3107";
const webURL = "http://127.0.0.1:3106";

test("未認証の一覧要求を拒否しAPIへ送らない", async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);

  const response = await fetch(webURL);

  expect(response.status).toBe(401);
  expect(response.headers.get("www-authenticate")).toMatch(/^Basic realm=/);
  expect(await (await request.get(`${control}/__requests`)).json()).toEqual([]);
});

test("認証設定が空なら一覧とヘルスチェックを503にする", async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);

  for (const path of ["/", "/health"]) {
    const response = await fetch(`http://127.0.0.1:3110${path}`);
    expect(response.status).toBe(503);
  }
  expect(await (await request.get(`${control}/__requests`)).json()).toEqual([]);
});

test("認証済みの取得後も未認証の派生要求を拒否する", async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
  const token = Buffer.from(`${testBasicAuth.username}:${testBasicAuth.password}`).toString(
    "base64",
  );
  const credentials = { authorization: `Basic ${token}` };

  const health = await fetch(`${webURL}/health`);
  expect(health.status).toBe(200);
  expect(await health.text()).toBe("ok\n");
  expect(await (await request.get(`${control}/__requests`)).json()).toEqual([]);

  const allowed = await fetch(webURL, { headers: credentials });
  expect(allowed.status).toBe(200);
  expect(allowed.headers.get("cache-control")).toBe("private, no-store");
  const html = await allowed.text();
  expect(html).toContain("API由来の報道発表");
  const asset = html.match(/\/_next\/static\/[^"\s]+\.(?:css|js)(?=")/)?.[0];
  expect(asset).toBeDefined();
  const paths = ["/third-party-notices.txt", asset!];
  for (const path of paths) {
    const response = await fetch(`${webURL}${path}`, { headers: credentials });
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
  }

  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(2);
  for (const [path, headers] of [
    ["/", { authorization: "Basic aW52YWxpZDppbnZhbGlk" }],
    ["/", {}],
    ["/?_rsc=auth-test", { rsc: "1" }],
    ["/?_rsc=auth-test", { rsc: "1", "next-router-prefetch": "1" }],
    ...paths.map((path) => [path, {}] as const),
  ] as const) {
    const response = await fetch(`${webURL}${path}`, { headers });
    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(await response.text()).toBe("Unauthorized");
  }
  expect(await (await request.get(`${control}/__requests`)).json()).toEqual(calls);
});

test("productionでトップページを表示し、開発画面を公開しない", async ({ page, request }) => {
  await request.post("http://127.0.0.1:3107/__reset", { data: {} });
  const homeResponse = await page.goto("/");

  expect(homeResponse?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeVisible();

  const mockResponse = await page.goto("/mock");

  expect(mockResponse?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "一覧Mockの表示確認" })).toHaveCount(0);
  expect((await page.goto("/ui-foundation"))?.status()).toBe(404);
});

test("通常の一覧操作が実時間の補充で429にならない", async ({ page, request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
  const listResponses: number[] = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.origin === webURL && url.pathname === "/") listResponses.push(response.status());
  });

  await page.goto("/");
  const search = page.getByRole("button", { name: "検索", exact: true });
  const result = page.getByRole("link", { name: "API由来の報道発表" });
  await expect(result).toBeVisible();
  await expect(search).toBeEnabled();
  await page.getByLabel("キーワード", { exact: true }).fill("water");
  await search.click();
  await expect(page).toHaveURL("/?q=water");
  await expect(search).toBeEnabled();

  await page.getByRole("button", { name: "土壌", exact: true }).click();
  await expect(page).toHaveURL("/?q=water&categories=soil");
  await expect(search).toBeEnabled();

  await page.getByLabel("開始日", { exact: true }).fill("2026-01-01");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-05");
  await search.click();
  await expect(page).toHaveURL("/?q=water&categories=soil&from=2026-01-01&to=2026-01-05");
  await expect(search).toBeEnabled();

  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await expect(page).toHaveURL((url) => url.searchParams.get("page") === "2");
  await expect(search).toBeEnabled();
  await page.reload();
  await expect(result).toBeVisible();
  await expect(search).toBeEnabled();

  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(listResponses).not.toContain(429);
  expect(calls).toHaveLength(12);
  console.log(`通常操作の要求数 Web ${listResponses.length}件、模擬API ${calls.length}件`);
});
