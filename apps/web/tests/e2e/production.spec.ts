import { expect, test } from "@playwright/test";

test("productionでトップページを表示し、Mockを公開しない", async ({ page }) => {
  const homeResponse = await page.goto("/");

  expect(homeResponse?.status()).toBe(200);
  await expect(
    page.getByRole("heading", { name: "環境省の報道発表を確認する土台", exact: true }),
  ).toBeVisible();

  const mockResponse = await page.goto("/mock");

  expect(mockResponse?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "一覧Mockの表示確認" })).toHaveCount(0);
});
