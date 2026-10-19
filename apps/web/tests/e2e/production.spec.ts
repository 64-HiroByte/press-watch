import { expect, test } from "@playwright/test";

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
