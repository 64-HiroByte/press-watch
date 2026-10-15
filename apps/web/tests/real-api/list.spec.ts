import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

type Item = {
  title: string;
  source_url: string;
  published_at: string;
  fixed_categories: { slug: string; name: string }[];
};

function createAPIComparison(page: Page, request: APIRequestContext) {
  const rows = page.getByRole("list", { name: "報道発表一覧" }).locator("li");
  return async (query: string, count: number) => {
    await expect(page).toHaveURL(query ? `/?${query}` : "/");
    const response = await request.get(`http://127.0.0.1:8001/press-releases?${query}`);
    expect(response.ok()).toBe(true);
    const data: { items: Item[]; pagination: { total_items: number } } = await response.json();
    expect(data.pagination.total_items).toBe(count);
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await expect(page.locator(".release-results-summary strong")).toHaveText(String(count));
    await expect(rows).toHaveCount(data.items.length);
    for (const [index, item] of data.items.entries()) {
      const row = rows.nth(index);
      await expect(row.getByRole("link")).toHaveText(item.title);
      await expect(row.getByRole("link")).toHaveAttribute("href", item.source_url);
      await expect(row.locator("time")).toHaveAttribute("datetime", item.published_at);
      expect(await row.locator(".release-category").allTextContents()).toEqual(
        item.fixed_categories.map((category) => category.name),
      );
      if (item.fixed_categories.length === 0)
        await expect(row.getByText("カテゴリなし")).toBeVisible();
    }
    return data;
  };
}

test("カテゴリ操作のOR・検索とのAND・全選択と全解除を既存実APIで照合する", async ({
  page,
  request,
}) => {
  const external: string[] = [];
  page.on("request", (call) => {
    if (new URL(call.url()).origin !== "http://127.0.0.1:3108") external.push(call.url());
  });
  const rows = page.getByRole("list", { name: "報道発表一覧" }).locator("li");
  const filters = page.locator(".release-sidebar-categories");
  const air = filters.getByRole("button", { name: "大気", exact: true });
  const soil = filters.getByRole("button", { name: "土壌", exact: true });
  const keyword = page.getByLabel("キーワード", { exact: true });
  const compare = createAPIComparison(page, request);
  await page.goto("/");
  await air.click();
  await compare("fixed_category=air", 52);
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await compare("fixed_category=air&page=2", 52);
  await soil.click();
  await compare("fixed_category=air&fixed_category=soil", 53);
  await keyword.fill("土壌");
  await page.getByLabel("開始日", { exact: true }).fill("2026-01-02");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-04");
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await compare(
    "q=土壌&fixed_category=air&fixed_category=soil&published_from=2026-01-02&published_to=2026-01-04",
    2,
  );
  await keyword.fill("未検索");
  await soil.click();
  await compare("q=土壌&fixed_category=air&published_from=2026-01-02&published_to=2026-01-04", 1);
  await expect(keyword).toHaveValue("未検索");
  await expect(rows.getByText("大気", { exact: true })).toBeVisible();
  await expect(rows.getByText("土壌", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "リセット", exact: true }).click();
  await filters.getByRole("button", { name: "カテゴリを全選択", exact: true }).click();
  const selected = [
    "fixed_category=air",
    "fixed_category=common",
    "fixed_category=effluent",
    "fixed_category=environmental_water",
    "fixed_category=noise",
    "fixed_category=odor",
    "fixed_category=other",
    "fixed_category=soil",
    "fixed_category=tap_water",
    "fixed_category=vibration",
  ].join("&");
  await compare(selected, 61);
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await compare(`${selected}&page=2`, 61);
  await expect(rows.getByText("カテゴリなし")).toHaveCount(0);
  await filters.getByRole("button", { name: "カテゴリを全解除", exact: true }).click();
  await compare("", 62);
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await compare("page=2", 62);
  await expect(rows.getByText("カテゴリなし")).toHaveCount(1);
  await page.goto("/?fixed_category=unknown");
  await compare("fixed_category=unknown", 0);
  await air.click();
  await compare("fixed_category=air&fixed_category=unknown", 52);
  await page.getByRole("button", { name: "unknownを解除", exact: true }).click();
  await expect(page).toHaveURL("/?fixed_category=air");
  expect(external).toEqual([]);
});

test("専用実APIのページ送りを往復し順序・全文タイトル・リンク・日付・全所属と未分類を表示する", async ({
  page,
  request,
}) => {
  const external: string[] = [];
  page.on("request", (call) => {
    if (new URL(call.url()).origin !== "http://127.0.0.1:3108") external.push(call.url());
  });
  const categories = await (await request.get("http://127.0.0.1:8001/fixed-categories")).json();
  expect(categories.items).toHaveLength(10);
  const compare = createAPIComparison(page, request);
  await page.goto("/");
  for (const [index, number] of [1, 2, 1].entries()) {
    if (index > 0) {
      await page
        .getByRole("navigation", { name: "ページ送り" })
        .getByLabel(number === 2 ? "次のページへ" : "前のページへ")
        .click();
      await expect(page).toHaveURL(number === 1 ? "/" : "/?page=2");
      await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeFocused();
    }
    const data = await compare(number === 1 ? "" : "page=2", 62);
    expect(data.items).toHaveLength(number === 1 ? 50 : 12);
    expect(await page.locator(".release-category-pill").allTextContents()).toEqual(
      categories.items.map((category: { name: string }) => category.name),
    );
    await expect(page.getByText(`${number} / 2ページ`)).toBeVisible();
    await expect(
      page
        .getByRole("navigation", { name: "ページ送り" })
        .getByLabel(`${number}ページ目`, { exact: true }),
    ).toHaveAttribute("aria-current", "page");
  }
  await page.goto("/?q=土壌&fixed_category=air");
  const row = page.getByRole("list", { name: "報道発表一覧" }).locator("li");
  await expect(row).toHaveCount(1);
  await expect(row.getByText("大気", { exact: true })).toBeVisible();
  await expect(row.getByText("土壌", { exact: true })).toBeVisible();
  await page.goto("/?q=存在しない検証用キーワード");
  await expect(page.getByText("条件に一致する報道発表がありません")).toBeVisible();
  await expect(page.getByText("0", { exact: true })).toBeVisible();
  expect(external).toEqual([]);
});

test("通常検索と公開日・リセットを実APIへ接続しカテゴリ付き検索をページ送りする", async ({
  page,
  request,
}) => {
  const external: string[] = [];
  page.on("request", (call) => {
    if (new URL(call.url()).origin !== "http://127.0.0.1:3108") external.push(call.url());
  });
  const search = page.getByRole("button", { name: "検索", exact: true });
  const keyword = page.getByLabel("キーワード", { exact: true });
  const rows = page.getByRole("list", { name: "報道発表一覧" }).locator("li");
  const compare = createAPIComparison(page, request);
  await page.goto("/?fixed_category=air&page=2");
  await keyword.fill("　土壌　");
  await search.click();
  await expect(page).toHaveURL(
    (url) => url.searchParams.get("q") === "土壌" && !url.searchParams.has("page"),
  );
  await compare("q=土壌&fixed_category=air", 1);
  await expect(rows.getByText("土壌", { exact: true })).toBeVisible();
  await expect(rows.getByText("大気", { exact: true })).toBeVisible();
  await keyword.fill("ページ");
  await search.click();
  await expect(page).toHaveURL((url) => url.searchParams.get("q") === "ページ");
  await compare("q=ページ&fixed_category=air", 51);
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get("page") === "2" &&
      url.searchParams.get("q") === "ページ" &&
      url.searchParams.get("fixed_category") === "air",
  );
  await compare("q=ページ&fixed_category=air&page=2", 51);
  await expect(rows).toHaveCount(1);
  await page.getByLabel("開始日", { exact: true }).fill("2026-01-04");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-02");
  await search.click();
  await expect(page).toHaveURL(
    (url) =>
      !url.searchParams.has("page") && url.searchParams.get("published_from") === "2026-01-02",
  );
  await compare(
    "q=ページ&fixed_category=air&published_from=2026-01-02&published_to=2026-01-04",
    51,
  );
  await page.getByLabel("開始日", { exact: true }).fill("2026-01-03");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-03");
  await search.click();
  await expect(page).toHaveURL((url) => url.searchParams.get("published_to") === "2026-01-03");
  await compare(
    "q=ページ&fixed_category=air&published_from=2026-01-03&published_to=2026-01-03",
    51,
  );
  await page.getByLabel("開始日", { exact: true }).fill("2026-01-04");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-05");
  await search.click();
  await expect(page).toHaveURL((url) => url.searchParams.get("published_to") === "2026-01-05");
  await compare("q=ページ&fixed_category=air&published_from=2026-01-04&published_to=2026-01-05", 0);
  await page.getByRole("button", { name: "リセット", exact: true }).click();
  await expect(page).toHaveURL("/?fixed_category=air");
  await compare("fixed_category=air", 52);
  await keyword.fill("%_");
  await search.click();
  await expect(page).toHaveURL((url) => url.searchParams.get("q") === "%_");
  await compare("q=%25_&fixed_category=air", 0);
  await expect(page.getByText("条件に一致する報道発表がありません")).toBeVisible();
  await page.getByRole("button", { name: "リセット", exact: true }).click();
  await expect(page).toHaveURL("/?fixed_category=air");
  await compare("fixed_category=air", 52);
  for (const label of ["キーワード", "開始日", "終了日"])
    await expect(page.getByLabel(label, { exact: true })).toHaveValue("");
  expect(external).toEqual([]);
});
