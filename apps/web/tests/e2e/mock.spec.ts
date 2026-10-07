import { expect, test } from "@playwright/test";

test("developmentで通常一覧のMockを表示できる", async ({ page }) => {
  const response = await page.goto("/mock");

  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "一覧Mockの表示確認" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeVisible();
  const results = page.getByRole("region", { name: "報道発表の表示", exact: true });
  await expect(
    results.getByRole("list", { name: "報道発表一覧", exact: true }).getByRole("listitem"),
  ).toHaveCount(8);
  await expect(results.getByText("1 / 16ページ", { exact: true })).toBeVisible();
});

test("既存の表示状態切替で取得失敗のメッセージを表示できる", async ({ page }) => {
  await page.goto("/mock");
  await page.getByLabel("表示状態", { exact: true }).selectOption("error");

  const results = page.getByRole("region", { name: "報道発表の表示", exact: true });
  await expect(results.getByRole("alert")).toContainText("報道発表を取得できませんでした");
  await expect(results.getByRole("alert")).toContainText("時間をおいて、もう一度お試しください。");
  await expect(results.getByRole("listitem")).toHaveCount(0);
});
