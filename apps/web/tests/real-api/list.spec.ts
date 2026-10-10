import { expect, test } from "@playwright/test";

type Item = {
  title: string;
  source_url: string;
  published_at: string;
  fixed_categories: { slug: string; name: string }[];
};

test("専用実APIの順序・全文タイトル・リンク・日付・全所属と未分類を表示する", async ({
  page,
  request,
}) => {
  const external: string[] = [];
  page.on("request", (call) => {
    if (new URL(call.url()).origin !== "http://127.0.0.1:3108") external.push(call.url());
  });
  const categories = await (await request.get("http://127.0.0.1:8001/fixed-categories")).json();
  expect(categories.items).toHaveLength(10);
  for (const number of [1, 2]) {
    const response = await request.get(`http://127.0.0.1:8001/press-releases?page=${number}`);
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data.pagination.total_items).toBe(62);
    expect(data.items).toHaveLength(number === 1 ? 50 : 12);
    await page.goto(number === 1 ? "/" : "/?page=2");
    await expect(page.getByText("62", { exact: true })).toBeVisible();
    const rows = page.getByRole("list", { name: "報道発表一覧" }).locator("li");
    await expect(rows).toHaveCount(data.items.length);
    for (let index = 0; index < data.items.length; index++) {
      const item: Item = data.items[index];
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
    expect(await page.locator(".release-category-pill").allTextContents()).toEqual(
      categories.items.map((category: { name: string }) => category.name),
    );
    await expect(page.getByText(`${number} / 2ページ`)).toBeVisible();
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
