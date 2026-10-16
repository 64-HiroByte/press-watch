import { expect, test } from "@playwright/test";

const control = "http://127.0.0.1:3107";

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("全選択は未定義slugを保持し全解除と無変更操作を区別する", async ({ page, request }) => {
  await page.goto("/?q=適用済み&categories=air,unknown&page=2");
  await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
  const selectAll = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
  const clear = page.getByRole("button", { name: "カテゴリを全解除", exact: true });
  await expect(selectAll).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索");
  await selectAll.click();
  await expect(page).toHaveURL("/?q=適用済み&categories=air,soil,unknown");
  await expect(page.getByText("未定義カテゴリ：unknown")).toBeVisible();
  await expect(page.locator(".release-category-toggle[aria-pressed=true]")).toHaveCount(2);
  await expect(selectAll).toBeDisabled();
  const history = await page.evaluate(() => window.history.length);
  await selectAll.evaluate((button: HTMLButtonElement) => button.click());
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
  expect(await page.evaluate(() => window.history.length)).toBe(history);
  await clear.click();
  await expect(page).toHaveURL("/?q=適用済み");
  await expect(page.locator(".release-category-toggle[aria-pressed=true]")).toHaveCount(0);
  await expect(page.getByText("未定義カテゴリ：unknown")).toHaveCount(0);
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("未検索");
  await expect(clear).toBeDisabled();
  const clearedHistory = await page.evaluate(() => window.history.length);
  await clear.evaluate((button: HTMLButtonElement) => button.click());
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(6);
  expect(await page.evaluate(() => window.history.length)).toBe(clearedHistory);
  await page.goto("/?categories=air,soil&page=2");
  await expect(selectAll).toBeDisabled();
  const before = await (await request.get(`${control}/__requests`)).json();
  const pageHistory = await page.evaluate(() => window.history.length);
  await selectAll.evaluate((button: HTMLButtonElement) => button.click());
  await expect(page).toHaveURL("/?categories=air,soil&page=2");
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(before.length);
  expect(await page.evaluate(() => window.history.length)).toBe(pageHistory);
});

test("カテゴリ指定なしでは全解除を無効にし選択後は再び利用できる", async ({ page, request }) => {
  await page.goto("/?page=2");
  const clear = page.getByRole("button", { name: "カテゴリを全解除", exact: true });
  const air = page.getByRole("button", { name: "大気", exact: true });
  await expect(clear).toBeDisabled();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await air.click();
  await expect(page).toHaveURL("/?categories=air");
  await expect(clear).toBeEnabled();
  await clear.click();
  await expect(page).toHaveURL("/");
  await expect(clear).toBeDisabled();
  await expect(air).toHaveAttribute("aria-pressed", "false");
});

for (const action of ["カテゴリを全選択", "カテゴリを全解除"]) {
  test(`一括操作の完了後もフォーカスを維持して重複操作を停止する ${action}`, async ({
    page,
    request,
  }) => {
    await page.goto("/?categories=air");
    const button = page.getByRole("button", { name: action, exact: true });
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await button.focus();
    await button.press("Enter");
    await expect(page).toHaveURL(action === "カテゴリを全選択" ? "/?categories=air,soil" : "/");
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await expect(button).toBeDisabled();
    await expect(button).toBeFocused();
    const history = await page.evaluate(() => window.history.length);
    await button.press("Enter");
    await button.press("Space");
    await button.evaluate((element: HTMLButtonElement) => element.click());
    expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    await expect(button).toBeFocused();
  });

  test(`一括操作の完了後もEscでドロワーを閉じてフォーカスを戻す ${action}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/?categories=air");
    const trigger = page.getByRole("button", { name: /^(条件を変更|検索条件を設定)$/ });
    await trigger.click();
    const drawer = page.getByRole("dialog", { name: "検索条件", exact: true });
    const button = drawer.getByRole("button", { name: action, exact: true });
    await expect(drawer.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await button.focus();
    await button.press("Enter");
    await expect(page).toHaveURL(action === "カテゴリを全選択" ? "/?categories=air,soil" : "/");
    await expect(drawer.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await expect(button).toBeDisabled();
    await expect(button).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });
}

test("一括カテゴリ操作の補助説明を常時表示せずホバーとフォーカスで示す", async ({ page }) => {
  await page.goto("/?categories=air");
  const tooltip = page.locator(".release-display-tooltip");
  const all = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
  const clear = page.getByRole("button", { name: "カテゴリを全解除", exact: true });
  await expect(page.getByText("分類済みの全カテゴリを対象", { exact: true })).not.toBeVisible();
  await expect(page.getByText("未分類も含めて表示", { exact: true })).not.toBeVisible();
  await expect(all).toHaveAccessibleDescription("分類済みの全カテゴリを対象");
  await expect(clear).toHaveAccessibleDescription("未分類も含めて表示");
  await all.hover();
  await expect(tooltip).toHaveText("分類済みの全カテゴリを対象");
  await page.getByRole("heading", { name: "報道発表一覧", exact: true }).hover();
  await expect(tooltip).toHaveCount(0);
  await clear.focus();
  await expect(tooltip).toHaveText("未分類も含めて表示");
  await clear.press("Escape");
  await expect(tooltip).toHaveCount(0);
  await all.click();
  await expect(all).toBeDisabled();
  await page.getByRole("heading", { name: "報道発表一覧", exact: true }).hover();
  await all.hover();
  await expect(tooltip).toHaveText("分類済みの全カテゴリを対象");
  await clear.click();
  await expect(clear).toBeDisabled();
  await page.getByRole("heading", { name: "報道発表一覧", exact: true }).hover();
  await clear.hover();
  await expect(tooltip).toHaveText("未分類も含めて表示");
  await page.getByRole("heading", { name: "報道発表一覧", exact: true }).hover();
  await expect(tooltip).toHaveCount(0);
});

test("狭い画面でも一括操作の補助説明をドロワーの前面へ表示する", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?categories=air");
  await page.getByRole("button", { name: "条件を変更", exact: true }).click();
  const tooltip = page.locator(".release-display-tooltip");
  const heading = page.getByRole("heading", { name: "検索条件", exact: true });
  const all = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
  const clear = page.getByRole("button", { name: "カテゴリを全解除", exact: true });
  for (const [button, text] of [
    [all, "分類済みの全カテゴリを対象"],
    [clear, "未分類も含めて表示"],
  ] as const) {
    await button.hover();
    await expect(tooltip).toHaveText(text);
    await expect
      .poll(() =>
        tooltip.evaluate((element) => {
          const bounds = element.getBoundingClientRect();
          const front = document.elementFromPoint(
            bounds.x + bounds.width / 2,
            bounds.y + bounds.height / 2,
          );
          return element === front || element.contains(front);
        }),
      )
      .toBe(true);
    await heading.hover();
    await expect(tooltip).toHaveCount(0);
  }
});

test.afterEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("20指定の上限では追加・全選択だけを停止し既知と未定義の解除を維持する", async ({
  page,
  request,
}) => {
  const slugs = ["air", ...Array.from({ length: 19 }, (_, index) => `unknown_${index}`)].sort();
  const url = new URLSearchParams({ categories: slugs.join(",") });
  await page.goto(`/?${url}`);
  await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
  const air = page.getByRole("button", { name: "大気", exact: true });
  const soil = page.getByRole("button", { name: "土壌", exact: true });
  const all = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
  await expect(soil).toBeDisabled();
  await expect(all).toBeDisabled();
  await expect(
    page.getByText("カテゴリは20個まで選択できます。解除してから追加してください。"),
  ).toBeVisible();
  await expect(air).toBeEnabled();
  await expect(page.getByRole("button", { name: "カテゴリを全解除", exact: true })).toBeEnabled();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await air.click();
  await expect(soil).toBeEnabled();
  await soil.click();
  await expect(soil).toHaveAttribute("aria-pressed", "true");
  await expect(air).toBeDisabled();
  await page.getByRole("button", { name: "unknown_0を解除", exact: true }).click();
  await expect(all).toBeEnabled();
  await all.click();
  await expect(air).toHaveAttribute("aria-pressed", "true");
  expect(new URL(page.url()).searchParams.get("categories")?.split(",") ?? []).toEqual(
    ["air", "soil", ...slugs.filter((slug) => slug !== "air" && slug !== "unknown_0")].sort(),
  );
});

for (const count of [20, 21]) {
  test(`全選択の上限と選択肢全体の件数 ${count}`, async ({ page, request }) => {
    await request.post(`${control}/__configure`, {
      data: {
        "/fixed-categories": {
          body: {
            items: Array.from({ length: count }, (_, index) => ({
              slug: `category_${index}`,
              name: `カテゴリ${index}`,
              display_order: index + 1,
            })),
          },
        },
      },
    });
    await page.goto("/");
    const all = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
    if (count === 21) {
      await expect(all).toBeDisabled();
      await expect(
        page.getByText("全選択は20個を超えるため利用できません。個別に選択してください。"),
      ).toBeVisible();
      expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
    } else {
      await expect(all).toBeEnabled();
      await all.click();
      await expect(page.locator(".release-category-toggle[aria-pressed=true]")).toHaveCount(20);
      expect(new URL(page.url()).searchParams.get("categories")?.split(",") ?? []).toEqual(
        Array.from({ length: 20 }, (_, index) => `category_${index}`).sort(),
      );
    }
  });
}

for (const [label, scenario, enabled, invalid] of [
  ["選択肢失敗", { "/fixed-categories": { status: 500 } }, false, false],
  ["選択肢0件", { "/fixed-categories": { body: { items: [] } } }, false, false],
  ["一覧失敗", { "/press-releases": { status: 500 } }, true, false],
  [
    "結果0件",
    {
      "/press-releases": {
        body: {
          items: [],
          pagination: { page: 1, page_size: 50, total_items: 0, total_pages: 0 },
        },
      },
    },
    true,
    false,
  ],
  [
    "日付422",
    {
      "/press-releases": {
        status: 422,
        body: { detail: [{ loc: ["query", "published_to"] }] },
      },
    },
    false,
    false,
  ],
  ["不正URL", {}, false, true],
] as const) {
  test(`カテゴリ操作の可否と再取得・修正による復旧 ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__configure`, { data: scenario });
    await page.goto(`/?categories=unknown&to=${invalid ? "invalid" : "2026-01-05"}`);
    await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
    const all = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
    const clear = page.getByRole("button", { name: "カテゴリを全解除", exact: true });
    for (const button of [all, clear]) {
      if (enabled) await expect(button).toBeEnabled();
      else await expect(button).toBeDisabled();
    }
    const keyword = page.getByLabel("キーワード", { exact: true });
    await keyword.fill("保持する下書き");
    const before = await (await request.get(`${control}/__requests`)).json();
    expect(before).toHaveLength(invalid ? 1 : 2);
    if (enabled) {
      await all.click();
      await expect(page).toHaveURL("/?categories=air,soil,unknown&to=2026-01-05");
      await expect(keyword).toHaveValue("保持する下書き");
    } else {
      await request.post(`${control}/__configure`, {
        data: { "/press-releases": {}, "/fixed-categories": {} },
      });
      if (invalid) {
        await page.getByLabel("終了日", { exact: true }).fill("2026-01-05");
        await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
        await expect(keyword).toHaveValue("保持する下書き");
      } else {
        await page.getByRole("button", { name: "再取得", exact: true }).click();
        await expect(keyword).toHaveValue("保持する下書き");
      }
      await expect(all).toBeEnabled();
      await expect(clear).toBeEnabled();
      await expect(page.getByRole("button", { name: "unknownを解除", exact: true })).toBeEnabled();
    }
  });
}

test("カテゴリ変更は送信前の入力エラーと下書きを保持する", async ({ page }) => {
  await page.goto("/?q=適用済み&categories=unknown");
  await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("あ".repeat(101));
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
  await page.getByRole("button", { name: "大気", exact: true }).click();
  await expect(page).toHaveURL("/?q=適用済み&categories=air,unknown");
  await expect(keyword).toHaveValue("あ".repeat(101));
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("キーワードは100文字以内で指定してください")).toBeVisible();
  await page.getByRole("button", { name: "unknownを解除", exact: true }).click();
  await expect(page).toHaveURL("/?q=適用済み&categories=air");
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
});

test("カテゴリ変更中は重複操作を止め移動したフォーカスと下書きを奪わない", async ({
  page,
  request,
}) => {
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": [{}, { hold: "gate" }] },
  });
  await page.goto("/?categories=air");
  const soil = page.getByRole("button", { name: "土壌", exact: true });
  await soil.evaluate((button: HTMLButtonElement) => {
    button.focus();
    button.click();
    button.click();
  });
  await expect(page.getByRole("status").filter({ hasText: "カテゴリを更新中" })).toContainText(
    "カテゴリを更新中",
  );
  await expect(soil).toBeFocused();
  await expect(soil).toHaveAttribute("aria-disabled", "true");
  await soil.press("Enter");
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("取得中の下書き");
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  const calls = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
  });
  await expect(soil).toHaveAttribute("aria-pressed", "true");
  await expect(soil).toHaveAttribute("aria-disabled", "false");
  await expect(keyword).toHaveValue("取得中の下書き");
  await expect(keyword).toBeFocused();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
});

for (const [action, status] of [
  ["カテゴリを全選択", 200],
  ["カテゴリを全解除", 500],
] as const) {
  test(`カテゴリ一括変更中は旧一覧を薄く残し完了後の結果へ切り替える ${action}`, async ({
    page,
    request,
  }) => {
    await request.post(`${control}/__configure`, {
      data: {
        "/press-releases": [
          {},
          {
            hold: "gate",
            status,
            body: {
              items: [
                {
                  title: "更新後の記事",
                  source_url: "https://example.invalid/updated",
                  published_at: "2026-01-02",
                  source_categories: null,
                  fixed_categories: [],
                },
              ],
              pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1 },
            },
          },
        ],
      },
    });
    await page.goto("/?categories=air");
    const oldArticle = page.locator(".release-title").filter({ hasText: "API由来の報道発表" });
    await expect(oldArticle).toBeVisible();
    const before = await oldArticle.boundingBox();
    await page.getByRole("button", { name: action, exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "カテゴリを更新中" })).toContainText(
      "カテゴリを更新中",
    );
    await expect(page.getByRole("status").filter({ hasText: "カテゴリを更新中" })).toContainText(
      "更新前の結果",
    );
    await expect(page.locator(".release-skeleton")).toHaveCount(0);
    await expect(oldArticle).toBeVisible();
    expect(await oldArticle.boundingBox()).toEqual(before);
    const retained = page.locator(".release-results-body");
    await expect(retained).toHaveCSS("opacity", "0.5");
    await expect(retained).toHaveAttribute("inert", "");
    await expect(retained).toHaveAttribute("aria-hidden", "true");
    await oldArticle.evaluate((link: HTMLAnchorElement) => link.focus());
    await expect(oldArticle).not.toBeFocused();
    await expect(page.locator(".release-results-summary")).toBeHidden();
    await expect(page.locator(".release-pagination")).toBeHidden();
    await expect
      .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
      .toBe(4);
    const calls = await (await request.get(`${control}/__requests`)).json();
    await request.post(`${control}/__release`, {
      data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
    });
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await expect(page.getByText("カテゴリを更新中", { exact: false })).toHaveCount(0);
    await expect(oldArticle).toHaveCount(0);
    if (status === 200) {
      await expect(page.getByRole("link", { name: "更新後の記事" })).toBeVisible();
      await expect(retained).not.toHaveAttribute("inert", "");
      await expect(retained).toHaveCSS("opacity", "1");
    } else {
      await expect(retained.getByRole("alert")).toContainText("報道発表を取得できませんでした");
    }
    expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
  });
}

test("カテゴリ変更とページ送り・履歴・再読込で選択と適用条件を復元する", async ({ page }) => {
  await page.goto("/?q=適用済み&categories=air,soil&to=2026-01-05");
  const soil = page.getByRole("button", { name: "土壌", exact: true });
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("未検索");
  await soil.click();
  await expect(page).toHaveURL("/?q=適用済み&categories=air&to=2026-01-05");
  await expect(soil).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await expect(page).toHaveURL("/?q=適用済み&categories=air&to=2026-01-05&page=2");
  await expect(keyword).toHaveValue("未検索");
  await page.goBack();
  await expect(page).toHaveURL("/?q=適用済み&categories=air&to=2026-01-05");
  await expect(keyword).toHaveValue("適用済み");
  await page.goBack();
  await expect(soil).toHaveAttribute("aria-pressed", "true");
  await page.goForward();
  await expect(soil).toHaveAttribute("aria-pressed", "false");
  await page.reload();
  await expect(soil).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByLabel("終了日", { exact: true })).toHaveValue("2026-01-05");
  await expect(keyword).toHaveValue("適用済み");
});

test("個別カテゴリ変更は適用済み条件へ作用し下書き・期間・ドロワーを保持する", async ({
  page,
  request,
}) => {
  await page.clock.setFixedTime(new Date("2026-10-07T03:00:00Z"));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?q=適用済み&categories=air,unknown&from=2026-01-01&to=2026-01-05&page=2");
  await page.getByRole("button", { name: "条件を変更", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "検索条件" });
  const soil = panel.getByRole("button", { name: "土壌", exact: true });
  await expect(soil).toBeEnabled();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索");
  await page.getByLabel("期間", { exact: true }).selectOption("week");
  await soil.focus();
  await soil.press("Space");
  await expect(page).toHaveURL(
    "/?q=適用済み&categories=air,soil,unknown&from=2026-01-01&to=2026-01-05",
  );
  await expect(soil).toHaveAttribute("aria-pressed", "true");
  await expect(soil).toBeFocused();
  await expect(panel).toBeVisible();
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("未検索");
  await expect(page.getByLabel("期間", { exact: true })).toHaveValue("week");
  await expect(page.getByLabel("開始日", { exact: true })).toHaveValue("2026-10-01");
  await expect(page.getByLabel("終了日", { exact: true })).toHaveValue("2026-10-07");
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(4);
  const sent = new URLSearchParams(
    calls.filter((call: { path: string }) => call.path === "/press-releases").at(-1).query,
  );
  expect([...sent.entries()]).toEqual([
    ["q", "適用済み"],
    ["fixed_category", "air"],
    ["fixed_category", "soil"],
    ["fixed_category", "unknown"],
    ["published_from", "2026-01-01"],
    ["published_to", "2026-01-05"],
  ]);
  await soil.press("Enter");
  await expect(page).toHaveURL("/?q=適用済み&categories=air,unknown&from=2026-01-01&to=2026-01-05");
  await expect(soil).toHaveAttribute("aria-pressed", "false");
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(page).toHaveURL("/?q=未検索&categories=air,unknown&from=2026-10-01&to=2026-10-07");
  await expect(panel).toBeHidden();
});
