import { expect, test } from "@playwright/test";

const control = "http://127.0.0.1:3107";

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test.afterEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("通常検索は下書きだけを適用しカテゴリを保持して先頭ページへ戻る", async ({
  page,
  request,
}) => {
  await page.goto("/?q=適用済み&fixed_category=air&fixed_category=unknown&page=2");
  const search = page.getByRole("button", { name: "検索", exact: true });
  await expect(search).toBeEnabled();
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("　土壌 %_&+　");
  await page.getByLabel("開始日", { exact: true }).fill("2026-01-05");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-01");
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await search.click();
  await expect(page).toHaveURL((url) => url.searchParams.get("q") === "土壌 %_&+");
  await expect(search).toBeEnabled();
  const params = new URL(page.url()).searchParams;
  expect(params.getAll("fixed_category")).toEqual(["air", "unknown"]);
  expect(params.has("page")).toBe(false);
  expect(params.get("published_from")).toBe("2026-01-01");
  expect(params.get("published_to")).toBe("2026-01-05");
  await expect(keyword).toHaveValue("土壌 %_&+");
  await expect(page.getByLabel("開始日", { exact: true })).toHaveValue("2026-01-01");
  await expect(page.getByLabel("終了日", { exact: true })).toHaveValue("2026-01-05");
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(4);
  expect(
    new URLSearchParams(
      calls.filter((call: { path: string }) => call.path === "/press-releases").at(-1).query,
    ).get("q"),
  ).toBe("土壌 %_&+");
  const history = await page.evaluate(() => window.history.length);
  await keyword.press("Enter");
  await expect(search).toBeEnabled();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(6);
  expect(await page.evaluate(() => window.history.length)).toBe(history);
});

test("リセットはカテゴリを保持し下書きを消してドロワーを開いたままにする", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(
    "/?q=適用済み&fixed_category=air&published_from=2026-01-01&published_to=2026-01-05&page=2",
  );
  await page.getByRole("button", { name: "条件を変更", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "検索条件" });
  const reset = dialog.getByRole("button", { name: "リセット", exact: true });
  await expect(reset).toBeEnabled();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索");
  await reset.click();
  await expect(page).toHaveURL("/?fixed_category=air");
  await expect(reset).toBeEnabled();
  await expect(dialog).toBeVisible();
  for (const label of ["キーワード", "開始日", "終了日"])
    await expect(page.getByLabel(label, { exact: true })).toHaveValue("");
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
  const history = await page.evaluate(() => window.history.length);
  await reset.click();
  expect(await page.evaluate(() => window.history.length)).toBe(history);
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
});

for (const [now, period, from, to] of [
  ["2026-10-06T15:05:00Z", "week", "2026-10-01", "2026-10-07"],
  ["2026-03-31T03:00:00Z", "month1", "2026-02-28", "2026-03-31"],
  ["2028-05-31T03:00:00Z", "month3", "2028-02-29", "2028-05-31"],
  ["2026-08-31T03:00:00Z", "month6", "2026-02-28", "2026-08-31"],
  ["2028-02-29T03:00:00Z", "year", "2027-02-28", "2028-02-29"],
] as const) {
  test(`期間選択は日本時間と暦で日付欄だけを補う ${period}`, async ({ page, request }) => {
    await page.clock.setFixedTime(new Date(now));
    await page.goto("/?fixed_category=air");
    const select = page.getByLabel("期間", { exact: true });
    await expect(select).toBeVisible();
    await select.selectOption(period);
    await expect(page.getByLabel("開始日", { exact: true })).toHaveValue(from);
    await expect(page.getByLabel("終了日", { exact: true })).toHaveValue(to);
    expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
    expect(new URL(page.url()).searchParams.has("published_from")).toBe(false);
    await select.selectOption("custom");
    await expect(page.getByLabel("開始日", { exact: true })).toHaveValue(from);
    await select.selectOption(period);
    await page.getByLabel("開始日", { exact: true }).fill("2026-01-01");
    await expect(select).toHaveValue("custom");
    await page.getByRole("button", { name: "検索", exact: true }).click();
    await expect(page).toHaveURL((url) => url.searchParams.get("published_from") === "2026-01-01");
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    expect(new URL(page.url()).searchParams.get("published_to")).toBe(to);
    await page.getByRole("button", { name: "リセット", exact: true }).click();
    await expect(page).toHaveURL("/?fixed_category=air");
    await expect(select).toHaveValue("custom");
  });
}

test("IMEの変換確定Enterは送信せず通常Enterだけで検索する", async ({ page, request }) => {
  await page.goto("/");
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("日本語");
  await keyword.evaluate((input) => {
    input.addEventListener("keyup", (event) => {
      if (event instanceof KeyboardEvent && event.key === "Enter")
        input.setAttribute("data-enter-finished", "true");
    });
    input.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true }));
  });
  const before = page.url();
  await keyword.press("Enter");
  await expect(keyword).toHaveAttribute("data-enter-finished", "true");
  expect(page.url()).toBe(before);
  await keyword.dispatchEvent("compositionend");
  await keyword.press("Enter");
  await expect(page).toHaveURL((url) => url.searchParams.get("q") === "日本語");
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
});

test("入力エラーは欄へ関連付けてフォーカスし条件と直前の一覧を保持する", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?q=適用済み");
  await page.getByRole("button", { name: "条件を変更", exact: true }).click();
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill(" " + "𠮷".repeat(100));
  const before = page.url();
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
  await expect(keyword).toHaveAttribute("aria-describedby", "release-input-errors");
  await expect(page.locator("#release-input-errors")).toContainText("100文字以内");
  await expect(keyword).toBeFocused();
  await expect(page.getByRole("dialog", { name: "検索条件" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "API由来の報道発表", includeHidden: true }),
  ).toHaveCount(1);
  expect(page.url()).toBe(before);
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await page.getByRole("button", { name: "リセット", exact: true }).click();
  await expect(page).toHaveURL("/");
  await expect(keyword).not.toHaveAttribute("aria-invalid", "true");
});

test("空白・Unicode上限・NULとHTML文字列を入力値として扱う", async ({ page, request }) => {
  await page.goto("/?q=元の検索");
  const keyword = page.getByLabel("キーワード", { exact: true });
  const search = page.getByRole("button", { name: "検索", exact: true });
  for (const value of ["𠮷".repeat(100), '<img src=x onerror="window.searchXSS=true"> %_&+']) {
    await keyword.fill(value);
    await search.click();
    await expect(page).toHaveURL((url) => url.searchParams.get("q") === value);
    await expect(search).toBeEnabled();
    await expect(keyword).toHaveValue(value);
  }
  expect(await page.evaluate(() => "searchXSS" in window)).toBe(false);
  await keyword.fill("不正\0文字");
  await search.click();
  await expect(keyword).toHaveAttribute("aria-invalid", "true");
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(6);
  await keyword.fill("\u0085　\t ");
  await search.click();
  await expect(page).toHaveURL("/");
  await expect(keyword).toHaveValue("");
  await expect(search).toBeEnabled();
});

test("片側日付は検索日の日本時間で補い未来の開始日を拒否する", async ({ page, request }) => {
  await page.clock.setFixedTime(new Date("2026-10-06T15:05:00Z"));
  await page.goto("/?fixed_category=air");
  const from = page.getByLabel("開始日", { exact: true });
  const to = page.getByLabel("終了日", { exact: true });
  const search = page.getByRole("button", { name: "検索", exact: true });
  await from.fill("2026-10-08");
  await search.click();
  await expect(from).toHaveAttribute("aria-invalid", "true");
  await expect(from).toBeFocused();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await from.fill("2026-10-01");
  await search.click();
  await expect(page).toHaveURL((url) => url.searchParams.get("published_to") === "2026-10-07");
  await expect(search).toBeEnabled();
  await expect(to).toHaveValue("2026-10-07");
  await from.fill("");
  await to.fill("2026-01-05");
  await search.click();
  await expect(page).toHaveURL("/?fixed_category=air&published_to=2026-01-05");
  await expect(search).toBeEnabled();
  await to.fill("");
  await search.click();
  await expect(page).toHaveURL("/?fixed_category=air");
  await expect(search).toBeEnabled();
});

test("期間の日付は選択時に確定し翌日の検索・再読込・履歴でも再計算しない", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-06T15:05:00Z"));
  await page.goto("/?fixed_category=air");
  const select = page.getByLabel("期間", { exact: true });
  const from = page.getByLabel("開始日", { exact: true });
  const to = page.getByLabel("終了日", { exact: true });
  const search = page.getByRole("button", { name: "検索", exact: true });
  await select.selectOption("week");
  await page.clock.setFixedTime(new Date("2026-10-07T15:05:00Z"));
  await search.click();
  await expect(page).toHaveURL(
    "/?fixed_category=air&published_from=2026-10-01&published_to=2026-10-07",
  );
  await expect(search).toBeEnabled();
  await expect(select).toHaveValue("week");
  const appliedURL = page.url();
  await page.reload();
  await expect(select).toHaveValue("custom");
  await expect(from).toHaveValue("2026-10-01");
  await expect(to).toHaveValue("2026-10-07");
  await page.getByRole("button", { name: "リセット", exact: true }).click();
  await expect(page).toHaveURL("/?fixed_category=air");
  await expect(search).toBeEnabled();
  await page.getByLabel("キーワード", { exact: true }).fill("履歴で破棄");
  await page.goBack();
  await expect(page).toHaveURL(appliedURL);
  await expect(select).toHaveValue("custom");
  await expect(from).toHaveValue("2026-10-01");
  await expect(to).toHaveValue("2026-10-07");
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("");
  await page.goForward();
  await expect(page).toHaveURL("/?fixed_category=air");
  await expect(from).toHaveValue("");
});

for (const [label, scenario, enabled] of [
  ["選択肢失敗", { "/fixed-categories": { status: 500 } }, false],
  ["選択肢0件", { "/fixed-categories": { body: { items: [] } } }, false],
  ["一覧失敗", { "/press-releases": { status: 500 } }, true],
  [
    "結果0件",
    {
      "/press-releases": {
        body: { items: [], pagination: { page: 1, page_size: 50, total_items: 0, total_pages: 0 } },
      },
    },
    true,
  ],
  [
    "日付422",
    { "/press-releases": { status: 422, body: { detail: [{ loc: ["query", "published_to"] }] } } },
    true,
  ],
] as const) {
  test(`検索・リセットの操作可否 ${label}`, async ({ page, request }) => {
    expect((await request.post(`${control}/__configure`, { data: scenario })).ok()).toBe(true);
    await page.goto("/?q=大気&fixed_category=air&published_to=2026-01-05");
    for (const name of ["検索", "リセット"]) {
      const button = page.getByRole("button", { name, exact: true });
      if (enabled) await expect(button).toBeEnabled();
      else await expect(button).toBeDisabled();
    }
    if (enabled) {
      expect(
        (await request.post(`${control}/__configure`, { data: { "/press-releases": {} } })).ok(),
      ).toBe(true);
      await page.getByRole("button", { name: "リセット", exact: true }).click();
      await expect(page).toHaveURL("/?fixed_category=air");
      await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    }
  });
}

test("不正URLでは通常検索・リセットを停止し修正操作を維持する", async ({ page }) => {
  await page.goto("/?published_from=2026-02-30");
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "リセット", exact: true })).toBeDisabled();
  const from = page.getByLabel("開始日", { exact: true });
  await from.fill("2026-02-29");
  await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
  await expect(from).toHaveAttribute("aria-invalid", "true");
  await expect(from).toBeFocused();
  await from.fill("2026-02-28");
  await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
});

test("検索中は操作を止め下書き編集を保持しドロワー成功時にトリガーへ戻る", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "検索条件を設定", exact: true });
  await trigger.click();
  await page.getByLabel("キーワード", { exact: true }).fill("適用する検索");
  expect(
    (
      await request.post(`${control}/__configure`, {
        data: { "/press-releases": { hold: "gate" } },
      })
    ).ok(),
  ).toBe(true);
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "検索条件" })).toBeHidden();
  await expect(trigger).toBeFocused();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeHidden();
  await page.getByRole("button", { name: "検索条件を設定", exact: true }).click();
  for (const name of ["検索", "リセット"])
    await expect(page.getByRole("button", { name, exact: true })).toBeDisabled();
  await page.getByLabel("キーワード", { exact: true }).fill("待機中の下書き");
  await page.getByLabel("キーワード", { exact: true }).press("Enter");
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(
    (
      await request.post(`${control}/__release`, {
        data: { ids: calls.map((call: { id: number }) => call.id) },
      })
    ).ok(),
  ).toBe(true);
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("待機中の下書き");
  await expect(page).toHaveURL((url) => url.searchParams.get("q") === "適用する検索");
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
});

test("日付欄の未完成入力を空欄扱いにせず検索を停止する", async ({ page, request }) => {
  await page.goto("/?q=保持する検索");
  const from = page.getByLabel("開始日", { exact: true });
  await from.fill("2026-01-01");
  await from.press("ArrowLeft");
  await from.press("Backspace");
  expect(await from.evaluate((input) => (input as HTMLInputElement).validity.badInput)).toBe(true);
  await page.getByRole("button", { name: "検索", exact: true }).click();
  await expect(from).toHaveAttribute("aria-invalid", "true");
  await expect(from).toBeFocused();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  expect(new URL(page.url()).searchParams.get("q")).toBe("保持する検索");
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await page.getByRole("button", { name: "リセット", exact: true }).click();
  await expect(from).toHaveValue("");
  expect(await from.evaluate((input) => (input as HTMLInputElement).validity.badInput)).toBe(false);
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
  for (const action of ["リセット", "履歴", "すべての条件を解除"]) {
    await from.fill("2026-01-01");
    await from.press("ArrowLeft");
    await from.press("Backspace");
    expect(await from.evaluate((input) => (input as HTMLInputElement).validity.badInput)).toBe(
      true,
    );
    if (action === "履歴") {
      await page.goBack();
      await expect(page).toHaveURL((url) => url.searchParams.get("q") === "保持する検索");
    } else await page.getByRole("button", { name: action, exact: true }).click();
    await expect(page.getByRole("button", { name: "検索", exact: true })).toBeEnabled();
    await expect(from).toHaveValue("");
    expect(await from.evaluate((input) => (input as HTMLInputElement).validity.badInput)).toBe(
      false,
    );
  }
});

test("composition状態がなくてもIMEのEnterフラグと229を抑止する", async ({ page, request }) => {
  await page.goto("/");
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("日本語");
  for (const init of [{ isComposing: true }, { keyCode: 229 }]) {
    expect(
      await keyword.evaluate((input, props) => {
        const event = new KeyboardEvent("keydown", {
          key: "Enter",
          bubbles: true,
          cancelable: true,
          ...props,
        });
        input.dispatchEvent(event);
        return event.defaultPrevented;
      }, init),
    ).toBe(true);
  }
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
});
