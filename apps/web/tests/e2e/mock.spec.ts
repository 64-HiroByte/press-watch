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

test("共有部品へ移した後もMockの文字サイズとドロワー操作を維持する", async ({ page }) => {
  await page.goto("/mock");
  const sample = page.locator(".mock-robustness");
  await expect(sample).toHaveCSS("margin-top", "40px");
  await expect(sample).toHaveCSS("font-size", "12px");
  await page.getByRole("button", { name: "文字サイズ：大きめ", exact: true }).click();
  await expect(sample).toHaveCSS("font-size", "14px");
  await page.getByRole("button", { name: "ダーク", exact: true }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /検索条件を設定|条件を変更/ }).click();
  const dialog = page.getByRole("dialog", { name: "検索条件" });
  await expect(dialog).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("表示のみの修正");
  await dialog.getByRole("button", { name: "検索", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText("表示のみの修正", { exact: true })).toBeVisible();
});
