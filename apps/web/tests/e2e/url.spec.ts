import { expect, test } from "@playwright/test";

const control = "http://127.0.0.1:3107";

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test.afterEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("新Web URLの条件とページを従来のAPI形式へ送る", async ({ page, request }) => {
  const url = "/?q=water&categories=air,unknown&from=2026-01-01&to=2026-01-05&page=2";
  await page.goto(url);
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
  await expect(page).toHaveURL(url);
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("water");
  await expect(page.getByLabel("開始日", { exact: true })).toHaveValue("2026-01-01");
  await expect(page.getByLabel("終了日", { exact: true })).toHaveValue("2026-01-05");
  await expect(page.getByText("2 / 2ページ", { exact: true })).toBeVisible();
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(2);
  expect(calls.map((call: { path: string }) => call.path).sort()).toEqual([
    "/fixed-categories",
    "/press-releases",
  ]);
  const sent = calls.find((call: { path: string }) => call.path === "/press-releases");
  expect([...new URLSearchParams(sent.query).entries()]).toEqual([
    ["q", "water"],
    ["fixed_category", "air"],
    ["fixed_category", "unknown"],
    ["published_from", "2026-01-01"],
    ["published_to", "2026-01-05"],
    ["page", "2"],
  ]);
});

for (const separator of [",", "%2C"]) {
  test(`カテゴリの区切り${separator}で再検索・ページ送り・履歴復元が使える`, async ({
    page,
    request,
  }) => {
    await page.goto(`/?categories=air${separator}unknown`);
    const search = page.getByRole("button", { name: "検索", exact: true });
    await expect(search).toBeEnabled();
    await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
    await expect(page.getByText("未定義カテゴリ：unknown")).toBeVisible();
    const history = await page.evaluate(() => window.history.length);
    await search.click();
    await expect(search).toBeEnabled();
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
    await page.getByLabel("キーワード", { exact: true }).fill("未検索");
    await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
    await expect(page).toHaveURL("/?categories=air,unknown&page=2");
    await expect(search).toBeEnabled();
    await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("未検索");
    expect(await page.evaluate(() => window.history.length)).toBe(history + 1);
    await page.goBack({ waitUntil: "commit" });
    await expect(search).toBeEnabled();
    await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("");
    expect(new URL(page.url()).searchParams.get("categories")).toBe("air,unknown");
    await page.reload();
    await expect(search).toBeEnabled();
    await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
    await expect(page.getByText("未定義カテゴリ：unknown")).toBeVisible();
  });
}

test("旧Webキーを検証や検索条件に使わず除去する", async ({ page, request }) => {
  await page.goto(
    "/?q=kept&categories=air&fixed_category=Invalid&published_from=bad&published_to=bad&page=2&tracking=value",
  );
  await expect(page).toHaveURL("/?q=kept&categories=air&page=2");
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
  await expect(page.getByLabel("開始日", { exact: true })).toHaveValue("");
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(2);
  const sent = calls.find((call: { path: string }) => call.path === "/press-releases");
  expect([...new URLSearchParams(sent.query).entries()]).toEqual([
    ["q", "kept"],
    ["fixed_category", "air"],
    ["page", "2"],
  ]);
});

for (const key of ["q", "categories", "from", "to", "page", "page_size"] as const) {
  test(`単一キー${key}の同値重複では一覧を取得せず修正できる`, async ({ page, request }) => {
    const value = {
      q: "water",
      categories: "air",
      from: "2026-01-01",
      to: "2026-01-05",
      page: "1",
      page_size: "50",
    }[key];
    await page.goto(`/?${key}=${value}&${key}=${value}`);
    await expect(page.getByText("URLの検索条件を修正してください")).toBeVisible();
    const calls = await (await request.get(`${control}/__requests`)).json();
    expect(calls.map((call: { path: string }) => call.path)).toEqual(["/fixed-categories"]);
    await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  });
}

test("URLの区切りを修正フォームの1行1slugへ持ち込まない", async ({ page, request }) => {
  await page.goto("/?categories=Invalid");
  await expect(page.getByText("URLの検索条件を修正してください")).toBeVisible();
  await page.getByLabel("カテゴリslug（1行に1個）").fill("air,soil");
  await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
  await expect(page.getByLabel("カテゴリslug（1行に1個）")).toHaveAttribute("aria-invalid", "true");
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(1);
  await page.getByLabel("カテゴリslug（1行に1個）").fill("air\nsoil");
  await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
  await expect(page).toHaveURL("/?categories=air,soil");
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
});
