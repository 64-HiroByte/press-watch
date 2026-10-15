import { expect, test } from "@playwright/test";

const control = "http://127.0.0.1:3107";

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("全選択は未定義slugを保持し全解除と無変更操作を区別する", async ({ page, request }) => {
  await page.goto("/?q=適用済み&fixed_category=air&fixed_category=unknown&page=2");
  await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
  const selectAll = page.getByRole("button", { name: "カテゴリを全選択", exact: true });
  const clear = page.getByRole("button", { name: "カテゴリを全解除", exact: true });
  await expect(selectAll).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索");
  await selectAll.click();
  await expect(page).toHaveURL(
    "/?q=適用済み&fixed_category=air&fixed_category=soil&fixed_category=unknown",
  );
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
  await page.goto("/?fixed_category=air&fixed_category=soil&page=2");
  await expect(selectAll).toBeDisabled();
  const before = await (await request.get(`${control}/__requests`)).json();
  const pageHistory = await page.evaluate(() => window.history.length);
  await selectAll.evaluate((button: HTMLButtonElement) => button.click());
  await expect(page).toHaveURL("/?fixed_category=air&fixed_category=soil&page=2");
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
  await expect(page).toHaveURL("/?fixed_category=air");
  await expect(clear).toBeEnabled();
  await clear.click();
  await expect(page).toHaveURL("/");
  await expect(clear).toBeDisabled();
  await expect(air).toHaveAttribute("aria-pressed", "false");
});

test("一括カテゴリ操作の補助説明を常時表示せずホバーとフォーカスで示す", async ({ page }) => {
  await page.goto("/?fixed_category=air");
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

test.afterEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("20指定の上限では追加・全選択だけを停止し既知と未定義の解除を維持する", async ({
  page,
  request,
}) => {
  const slugs = ["air", ...Array.from({ length: 19 }, (_, index) => `unknown_${index}`)].sort();
  const url = new URLSearchParams(slugs.map((slug) => ["fixed_category", slug]));
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
  expect(new URL(page.url()).searchParams.getAll("fixed_category")).toEqual(
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
      expect(new URL(page.url()).searchParams.getAll("fixed_category")).toEqual(
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
    await page.goto(`/?fixed_category=unknown&published_to=${invalid ? "invalid" : "2026-01-05"}`);
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
      await expect(page).toHaveURL(
        "/?fixed_category=air&fixed_category=soil&fixed_category=unknown&published_to=2026-01-05",
      );
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
  await page.goto("/?q=適用済み&fixed_category=unknown");
  await page.getByRole("button", { name: "条件の詳細", exact: true }).click();
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("あ".repeat(101));
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
  await page.getByRole("button", { name: "大気", exact: true }).click();
  await expect(page).toHaveURL("/?q=適用済み&fixed_category=air&fixed_category=unknown");
  await expect(keyword).toHaveValue("あ".repeat(101));
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("キーワードは100文字以内で指定してください")).toBeVisible();
  await page.getByRole("button", { name: "unknownを解除", exact: true }).click();
  await expect(page).toHaveURL("/?q=適用済み&fixed_category=air");
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
});

test("カテゴリ変更中は重複操作を止め移動したフォーカスと下書きを奪わない", async ({
  page,
  request,
}) => {
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": [{}, { hold: "gate" }] },
  });
  await page.goto("/?fixed_category=air");
  const soil = page.getByRole("button", { name: "土壌", exact: true });
  await soil.evaluate((button: HTMLButtonElement) => {
    button.focus();
    button.click();
    button.click();
  });
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
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

test("カテゴリ変更とページ送り・履歴・再読込で選択と適用条件を復元する", async ({ page }) => {
  await page.goto("/?q=適用済み&fixed_category=air&fixed_category=soil&published_to=2026-01-05");
  const soil = page.getByRole("button", { name: "土壌", exact: true });
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("未検索");
  await soil.click();
  await expect(page).toHaveURL("/?q=適用済み&fixed_category=air&published_to=2026-01-05");
  await expect(soil).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await expect(page).toHaveURL("/?q=適用済み&fixed_category=air&published_to=2026-01-05&page=2");
  await expect(keyword).toHaveValue("未検索");
  await page.goBack();
  await expect(page).toHaveURL("/?q=適用済み&fixed_category=air&published_to=2026-01-05");
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
  await page.goto(
    "/?q=適用済み&fixed_category=air&fixed_category=unknown&published_from=2026-01-01&published_to=2026-01-05&page=2",
  );
  await page.getByRole("button", { name: "条件を変更", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "検索条件" });
  const soil = panel.getByRole("button", { name: "土壌", exact: true });
  await expect(soil).toBeEnabled();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索");
  await page.getByLabel("期間", { exact: true }).selectOption("week");
  await soil.focus();
  await soil.press("Space");
  await expect(page).toHaveURL(
    "/?q=適用済み&fixed_category=air&fixed_category=soil&fixed_category=unknown&published_from=2026-01-01&published_to=2026-01-05",
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
  await expect(page).toHaveURL(
    "/?q=適用済み&fixed_category=air&fixed_category=unknown&published_from=2026-01-01&published_to=2026-01-05",
  );
  await expect(soil).toHaveAttribute("aria-pressed", "false");
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(page).toHaveURL(
    "/?q=未検索&fixed_category=air&fixed_category=unknown&published_from=2026-10-01&published_to=2026-10-07",
  );
  await expect(panel).toBeHidden();
});
