import { expect, test } from "@playwright/test";
import { mkdir, rename, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { ListData } from "@/lib/press-releases-api";

const control = "http://127.0.0.1:3107";

test("正規化待ちのHTMLで選択肢の取得失敗を誤表示しない", async ({ request }) => {
  const response = await request.get("http://127.0.0.1:3106/?q=%20a%20");
  const html = await response.text();
  expect(html).toContain("報道発表を読み込んでいます");
  expect(html.includes("カテゴリ選択肢を取得できませんでした")).toBe(false);
  expect(await (await request.get(`${control}/__requests`)).json()).toEqual([]);
});
function result(
  total = 1,
  items: ListData["items"] = [
    {
      title: "安全な記事",
      source_url: "https://example.invalid/safe",
      published_at: "2026-01-01",
      source_categories: null,
      fixed_categories: [],
    },
  ],
  page = 1,
) {
  return {
    items,
    pagination: { page, page_size: 50, total_items: total, total_pages: Math.ceil(total / 50) },
  };
}

function pagedResult(total: number, page: number) {
  const count = Math.max(0, Math.min(50, total - (page - 1) * 50));
  return result(
    total,
    Array.from({ length: count }, (_, index) => ({
      ...result().items[0]!,
      title: `${page}ページの記事${index + 1}`,
      source_url: `https://example.invalid/page/${page}/${index + 1}`,
    })),
    page,
  );
}

test("ページ送りで先頭・中間・最終のAPI値と移動先を表示する", async ({ page, request }) => {
  await request.post(`${control}/__configure`, {
    data: {
      "/press-releases": [1, 2, 3].map((number) => ({ body: pagedResult(123, number) })),
    },
  });
  await page.goto("/");
  const paging = page.getByRole("navigation", { name: "ページ送り" });
  await expect(paging).toBeVisible();
  await expect(paging.getByLabel("前のページへ")).toHaveAttribute("aria-disabled", "true");
  await expect(paging.getByLabel("1ページ目", { exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByText("中 1–50件", { exact: false })).toBeVisible();
  await paging.getByLabel("次のページへ").click();
  await expect(page).toHaveURL((url) => url.searchParams.get("page") === "2");
  await expect(paging.getByLabel("2ページ目", { exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("list", { name: "報道発表一覧" }).locator("li")).toHaveCount(50);
  await expect(page.getByRole("link", { name: "2ページの記事1", exact: true })).toBeVisible();
  await expect(page.getByText("中 51–100件", { exact: false })).toBeVisible();
  await paging.getByLabel("3ページ目", { exact: true }).click();
  await expect(page).toHaveURL((url) => url.searchParams.get("page") === "3");
  await expect(page.getByRole("list", { name: "報道発表一覧" }).locator("li")).toHaveCount(23);
  await expect(page.getByText("中 101–123件", { exact: false })).toBeVisible();
  await expect(paging.getByLabel("次のページへ")).toHaveAttribute("aria-disabled", "true");
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(6);
  expect(
    calls
      .filter((call: { path: string }) => call.path === "/press-releases")
      .map((call: { query: string }) => new URLSearchParams(call.query).get("page")),
  ).toEqual([null, "2", "3"]);
});

for (const [total, number, labels] of [
  [1, 1, [1]],
  [250, 3, [1, 2, 3, 4, 5]],
  [300, 1, [1, 2, 3, 6]],
  [800, 1, [1, 2, 3, 16]],
  [800, 8, [1, 7, 8, 9, 16]],
  [800, 16, [1, 14, 15, 16]],
  [500050, 10000, [1, 9998, 9999, 10000]],
] as const) {
  test(`ページ送りの番号と上限を守る ${number}/${Math.ceil(total / 50)}`, async ({
    page,
    request,
  }) => {
    await request.post(`${control}/__configure`, {
      data: { "/press-releases": { body: pagedResult(total, number) } },
    });
    await page.goto(number === 1 ? "/" : `/?page=${number}`);
    const paging = page.getByRole("navigation", { name: "ページ送り" });
    await expect(paging).toBeVisible();
    expect(await paging.locator('[aria-label$="ページ目"]').allTextContents()).toEqual(
      labels.map(String),
    );
    await expect(paging.getByLabel(`${number}ページ目`, { exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const last = Math.min(10000, Math.ceil(total / 50));
    if (number === 1) await expect(paging.getByLabel("前のページへ")).not.toHaveAttribute("href");
    if (number === last)
      await expect(paging.getByLabel("次のページへ")).not.toHaveAttribute("href");
    await expect(
      page.getByText(`${number} / ${Math.ceil(total / 50)}ページ`, { exact: true }),
    ).toBeVisible();
    if (last === 10000)
      await expect(
        page.getByText("移動できるのは10000ページ目までです", { exact: true }),
      ).toBeVisible();
    const calls = await (await request.get(`${control}/__requests`)).json();
    expect(calls).toHaveLength(2);
  });
}

for (const width of [1280, 390, 767, 768]) {
  test(`ページ送り後に見出しと一覧先頭へ戻る 幅${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 720 });
    await request.post(`${control}/__configure`, {
      data: { "/press-releases": [1, 2].map((number) => ({ body: pagedResult(123, number) })) },
    });
    const params = new URLSearchParams({ q: "長い条件".repeat(25) });
    for (let index = 0; index < 20; index++)
      params.append(
        "fixed_category",
        `category_${String(index).padStart(2, "0")}_${"x".repeat(80)}`,
      );
    await page.goto(`/?${params}`);
    const header = page.locator(".release-header-body");
    if (width >= 768) {
      await header.evaluate((element) => {
        element.scrollTop = element.scrollHeight;
      });
      expect(await header.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    }
    await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
    await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeFocused();
    await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeInViewport();
    await expect(page.getByRole("link", { name: "2ページの記事1", exact: true })).toBeInViewport();
    if (width >= 768) expect(await header.evaluate((element) => element.scrollTop)).toBe(0);
  });
}

for (const failed of [false, true]) {
  test(`ページ送り待ちの入力にフォーカスを戻さない ${failed ? "失敗" : "成功"}`, async ({
    page,
    request,
  }) => {
    await request.post(`${control}/__configure`, {
      data: {
        "/press-releases": [
          { body: pagedResult(62, 1) },
          { hold: "gate", status: failed ? 500 : 200, body: pagedResult(62, 2) },
        ],
      },
    });
    await page.goto("/");
    await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
    await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "ページ送り" })).toHaveCount(0);
    await expect(page.getByText("1 / 2ページ", { exact: true })).toHaveCount(0);
    const keyword = page.getByLabel("キーワード", { exact: true });
    await keyword.fill("待機中の下書き");
    await expect
      .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
      .toBe(4);
    const calls = await (await request.get(`${control}/__requests`)).json();
    await request.post(`${control}/__release`, {
      data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
    });
    await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
    await expect(keyword).toBeFocused();
    await expect(keyword).toHaveValue("待機中の下書き");
    if (failed) {
      await expect(page.getByText("報道発表を取得できませんでした")).toBeVisible();
      await expect(page.getByRole("navigation", { name: "ページ送り" })).toHaveCount(0);
    } else {
      await expect(page.getByText("2 / 2ページ", { exact: true })).toBeVisible();
    }
  });
}

test("ページ送りは適用済み条件と下書きを分けて保持し履歴で入力を復元する", async ({
  page,
  request,
}) => {
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": [1, 2, 1, 2].map((number) => ({ body: pagedResult(62, number) })) },
  });
  const original =
    "/?q=大気&fixed_category=air&fixed_category=unknown&published_from=2026-01-01&published_to=2026-01-05";
  await page.goto(original);
  const keyword = page.getByLabel("キーワード", { exact: true });
  const from = page.getByLabel("開始日", { exact: true });
  await keyword.fill("未検索の下書き");
  await from.fill("2026-01-02");
  const paging = page.getByRole("navigation", { name: "ページ送り" });
  const historyLength = await page.evaluate(() => history.length);
  await paging.getByLabel("1ページ目", { exact: true }).click();
  await paging.getByLabel("次のページへ").hover();
  await paging.getByLabel("次のページへ").focus();
  expect(await page.evaluate(() => history.length)).toBe(historyLength);
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  await paging.getByLabel("次のページへ").press("Enter");
  await expect(page.getByText("2 / 2ページ", { exact: true })).toBeVisible();
  await expect(keyword).toHaveValue("未検索の下書き");
  await expect(from).toHaveValue("2026-01-02");
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(4);
  const listCall = calls.find(
    (call: { path: string; query: string }) =>
      call.path === "/press-releases" && new URLSearchParams(call.query).get("page") === "2",
  );
  const params = new URLSearchParams(listCall.query);
  expect(params.get("q")).toBe("大気");
  expect(params.get("published_from")).toBe("2026-01-01");
  expect(params.get("published_to")).toBe("2026-01-05");
  expect(params.getAll("fixed_category")).toEqual(["air", "unknown"]);
  expect(new URL(page.url()).searchParams.has("page_size")).toBe(false);
  expect(await page.evaluate(() => history.length)).toBe(historyLength + 1);
  await page.goBack({ waitUntil: "commit" });
  await expect(page.getByText("1 / 2ページ", { exact: true })).toBeVisible();
  await expect(keyword).toHaveValue("大気");
  await expect(from).toHaveValue("2026-01-01");
  expect(new URL(page.url()).searchParams.has("page")).toBe(false);
  await page.goForward({ waitUntil: "commit" });
  await expect(page.getByText("2 / 2ページ", { exact: true })).toBeVisible();
  await expect(keyword).toHaveValue("大気");
  await expect(from).toHaveValue("2026-01-01");
});

for (const closeBeforeResponse of [false, true]) {
  test(`ページ送り待ちに開いたドロワーへフォーカスを保つ ${closeBeforeResponse ? "応答前に閉じる" : "応答後に閉じる"}`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await request.post(`${control}/__configure`, {
      data: {
        "/press-releases": [
          { body: pagedResult(62, 1) },
          { hold: "gate", body: pagedResult(62, 2) },
          { body: pagedResult(62, 2) },
        ],
      },
    });
    await page.goto("/");
    await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
    await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
    const trigger = page.getByRole("button", { name: "検索条件を設定", exact: true });
    await trigger.click();
    const drawer = page.getByRole("dialog", { name: "検索条件", exact: true });
    await expect(drawer).toBeVisible();
    const keyword = drawer.getByLabel("キーワード", { exact: true });
    await keyword.fill("ドロワーの下書き");
    if (closeBeforeResponse) {
      await drawer.getByRole("button", { name: "検索条件を閉じる" }).click();
      await expect(trigger).toBeFocused();
    }
    await expect
      .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
      .toBe(4);
    const calls = await (await request.get(`${control}/__requests`)).json();
    await request.post(`${control}/__release`, {
      data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
    });
    await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
    if (closeBeforeResponse) await expect(trigger).toBeFocused();
    else {
      await expect(keyword).toBeFocused();
      await expect(keyword).toHaveValue("ドロワーの下書き");
      await drawer.getByRole("button", { name: "検索条件を閉じる" }).click();
      await expect(trigger).toBeFocused();
    }
    await page.getByRole("button", { name: "再取得", exact: true }).click();
    await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
    await expect(
      page.getByRole("heading", { name: "報道発表一覧", exact: true }),
    ).not.toBeFocused();
  });
}

test("ページ送りの連打を停止し失敗が確定したら復旧見出しへ戻す", async ({ page, request }) => {
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": [{ body: pagedResult(62, 1) }, { hold: "gate", status: 500 }] },
  });
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "ページ送り" })
    .getByLabel("次のページへ")
    .evaluate((link: HTMLAnchorElement) => {
      link.click();
      link.click();
    });
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  const calls = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
  });
  await expect(page.getByText("報道発表を取得できませんでした")).toBeVisible();
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeFocused();
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeInViewport();
  await expect(page.getByRole("navigation", { name: "ページ送り" })).toHaveCount(0);
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
});

test("狭い画面で大きい文字と5桁のページ番号を折り返して操作できる", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 720 });
  await request.post(`${control}/__configure`, {
    data: {
      "/press-releases": [
        { body: pagedResult(500000, 9999) },
        { body: pagedResult(500000, 10000) },
      ],
    },
  });
  await page.goto("/?page=9999");
  await page.getByRole("button", { name: "大きい文字サイズ", exact: true }).click();
  const paging = page.getByRole("navigation", { name: "ページ送り" });
  await paging.scrollIntoViewIfNeeded();
  const overflow = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth > innerWidth,
    pagination:
      document.querySelector(".release-pagination")!.scrollWidth >
      document.querySelector(".release-pagination")!.clientWidth,
  }));
  expect(overflow).toEqual({ page: false, pagination: false });
  await paging.getByLabel("次のページへ").focus();
  await paging.getByLabel("次のページへ").press("Enter");
  await expect(page.getByText("10000 / 10000ページ", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeFocused();
  await expect(paging.getByLabel("次のページへ")).toHaveAttribute("tabindex", "-1");
});

test("ページ送りの完了時点の幅に合わせて一覧先頭へ戻す", async ({ page, request }) => {
  await request.post(`${control}/__configure`, {
    data: {
      "/press-releases": [{ body: pagedResult(62, 1) }, { hold: "gate", body: pagedResult(62, 2) }],
    },
  });
  await page.goto("/");
  await page.getByRole("navigation", { name: "ページ送り" }).getByLabel("次のページへ").click();
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 720 });
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  const calls = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
  });
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeFocused();
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeInViewport();
  await expect(page.getByRole("link", { name: "2ページの記事1", exact: true })).toBeInViewport();
});

test("ページ送りを履歴で中断した後の古い応答は表示とフォーカスを奪わない", async ({
  page,
  request,
}) => {
  await request.post(`${control}/__configure`, {
    data: {
      "/press-releases": [
        { body: pagedResult(123, 1) },
        { body: pagedResult(123, 2) },
        { hold: "gate", body: pagedResult(123, 3) },
      ],
    },
  });
  await page.goto("/");
  const paging = page.getByRole("navigation", { name: "ページ送り" });
  await paging.getByLabel("次のページへ").click();
  await expect(page.getByText("2 / 3ページ", { exact: true })).toBeVisible();
  await paging.getByLabel("次のページへ").click();
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(6);
  const calls = await (await request.get(`${control}/__requests`)).json();
  const old = calls.find(
    (call: { path: string; query: string }) =>
      call.path === "/press-releases" && new URLSearchParams(call.query).get("page") === "3",
  );
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": { body: pagedResult(123, 1) } },
  });
  await page.goBack({ waitUntil: "commit" });
  await expect(page.getByText("1 / 3ページ", { exact: true })).toBeVisible();
  const keyword = page.getByLabel("キーワード", { exact: true });
  await keyword.fill("履歴復元後の下書き");
  await request.post(`${control}/__release`, { data: { ids: [old.id] } });
  await expect
    .poll(
      async () =>
        (await (await request.get(`${control}/__requests`)).json()).find(
          (call: { id: number }) => call.id === old.id,
        )?.finished,
    )
    .toBe(true);
  await expect(page.getByText("1 / 3ページ", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "3ページの記事1", exact: true })).toHaveCount(0);
  await expect(keyword).toBeFocused();
  await expect(keyword).toHaveValue("履歴復元後の下書き");
});

for (const count of [0, 1, 50]) {
  test(`記事数と手動再取得で要求数が増えない ${count}件`, async ({ page, request }) => {
    const items = Array.from({ length: count }, (_, index) => ({
      ...result().items[0]!,
      title: `記事${index}`,
      source_url: `https://example.invalid/item/${index}`,
    }));
    await request.post(`${control}/__reset`, {
      data: { "/press-releases": { body: result(count, items) } },
    });
    await page.goto("/");
    await expect(page.getByRole("list", { name: "報道発表一覧" }).locator("li")).toHaveCount(count);
    const calls = async () => await (await request.get(`${control}/__requests`)).json();
    expect((await calls()).map((call: { path: string }) => call.path).sort()).toEqual([
      "/fixed-categories",
      "/press-releases",
    ]);
    await page.getByRole("button", { name: "再取得", exact: true }).click();
    await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
    expect((await calls()).map((call: { path: string }) => call.path).sort()).toEqual([
      "/fixed-categories",
      "/fixed-categories",
      "/press-releases",
      "/press-releases",
    ]);
  });
}

for (const [label, scenario] of [
  ["選択肢失敗", { status: 500 }],
  ["選択肢0件", { body: { items: [] } }],
] as const) {
  test(`選択肢が使えない間の操作を停止し再取得で復旧する ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__reset`, {
      data: {
        "/fixed-categories": [scenario, {}],
        "/press-releases": { body: pagedResult(62, 1) },
      },
    });
    await page.goto("/?fixed_category=unknown");
    await page.getByLabel("キーワード", { exact: true }).fill("保持する下書き");
    await expect(page.getByRole("button", { name: "すべての条件を解除" })).toBeDisabled();
    const paging = page.getByRole("navigation", { name: "ページ送り" });
    await expect(page.getByText("1 / 2ページ", { exact: true })).toBeVisible();
    for (const link of await paging.locator("a").all()) {
      await expect(link).not.toHaveAttribute("href");
      await expect(link).toHaveAttribute("tabindex", "-1");
    }
    if (label === "選択肢0件")
      await expect(page.getByRole("button", { name: "unknownを解除" })).toBeDisabled();
    await page.getByRole("button", { name: "再取得", exact: true }).click();
    await expect(page.getByRole("button", { name: "すべての条件を解除" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "unknownを解除" })).toBeEnabled();
    await expect(paging.getByLabel("次のページへ")).toHaveAttribute(
      "href",
      "/?fixed_category=unknown&page=2",
    );
    await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("保持する下書き");
    expect(new URL(page.url()).searchParams.get("fixed_category")).toBe("unknown");
  });
}

test("両方確定するまでは成功側も表示せず再試行を重ねない", async ({ page, request }) => {
  await request.post(`${control}/__reset`, {
    data: { "/fixed-categories": [{ hold: "gate" }, { hold: "gate" }] },
  });
  await page.goto("/", { waitUntil: "commit" });
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toHaveCount(0);
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(2);
  const first = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: first.map((call: { id: number }) => call.id) },
  });
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  await page
    .getByRole("button", { name: "再取得", exact: true })
    .evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeDisabled();
  const second = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: second.slice(2).map((call: { id: number }) => call.id) },
  });
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
});

for (const [label, status, response] of [
  ["422", 422, {}],
  ["500", 500, {}],
  ["非JSON", 200, { raw: "not-json", contentType: "text/plain" }],
  ["redirect", 302, { headers: { location: "http://127.0.0.1:3107/redirect-target" } }],
] as const) {
  test(`HTTP失敗と不正応答を空結果へ置き換えない ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__reset`, {
      data: { "/press-releases": { status, ...response } },
    });
    await page.goto("/");
    await expect(page.getByText("報道発表を取得できませんでした")).toBeVisible();
    await expect(page.getByText("報道発表はまだありません")).toHaveCount(0);
    expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(2);
  });
}

test("履歴変更後の再取得を古い応答が上書きせず下書きを維持する", async ({ page, request }) => {
  const named = (title: string, count: number) => result(count, [{ ...result().items[0]!, title }]);
  await request.post(`${control}/__reset`, {
    data: { "/press-releases": { body: named("履歴の一覧", 3) } },
  });
  await page.goto("/?q=履歴&fixed_category=unknown");
  await page.getByRole("button", { name: "unknownを解除" }).click();
  await expect(page).toHaveURL((url) => !url.searchParams.has("fixed_category"));
  await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
  await page.getByLabel("キーワード", { exact: true }).fill("履歴で破棄する下書き");
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": { hold: "gate", body: named("古い遅延応答", 7) } },
  });
  await page.getByRole("button", { name: "再取得", exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(6);
  const oldCalls = await (await request.get(`${control}/__requests`)).json();
  const oldID =
    oldCalls.at(-2).path === "/press-releases" ? oldCalls.at(-2).id : oldCalls.at(-1).id;
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": { body: named("履歴の一覧", 3) } },
  });
  await page.goBack({ waitUntil: "commit" });
  await expect(page).toHaveURL((url) => url.searchParams.get("fixed_category") === "unknown");
  await expect(page.getByRole("link", { name: "履歴の一覧" })).toBeVisible();
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("履歴");
  await page.getByLabel("キーワード", { exact: true }).fill("最新の下書き");
  const before = (await (await request.get(`${control}/__requests`)).json()).length;
  await request.post(`${control}/__configure`, {
    data: { "/press-releases": { hold: "gate", body: named("最新の応答", 11) } },
  });
  await page.getByRole("button", { name: "再取得", exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(before + 2);
  const latestCalls = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, { data: { ids: [oldID] } });
  await expect
    .poll(async () => {
      const calls = await (await request.get(`${control}/__requests`)).json();
      return calls.find((call: { id: number }) => call.id === oldID)?.finished;
    })
    .toBe(true);
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await expect(page.getByRole("link", { name: "古い遅延応答" })).toHaveCount(0);
  await expect(page.getByText("7", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeDisabled();
  await request.post(`${control}/__release`, {
    data: { ids: latestCalls.slice(before).map((call: { id: number }) => call.id) },
  });
  await expect(page.getByRole("link", { name: "最新の応答" })).toBeVisible();
  await expect(page.getByText("11", { exact: true })).toBeVisible();
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("最新の下書き");
  await request.post(`${control}/__configure`, { data: { "/press-releases": {} } });
  await page.goForward({ waitUntil: "commit" });
  await expect(page).toHaveURL((url) => !url.searchParams.has("fixed_category"));
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("履歴");
  await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
});

test("日付をまたぐ履歴復元の正規化後に一覧と再取得が使える", async ({ page }) => {
  const clockFile = resolve("../../tmp/playwright/server-clock.json");
  async function setDate(date: string) {
    const now = Date.parse(date);
    await mkdir(dirname(clockFile), { recursive: true });
    await writeFile(`${clockFile}.tmp`, JSON.stringify({ now, startedAt: Date.now() }));
    await rename(`${clockFile}.tmp`, clockFile);
    await page.clock.setFixedTime(new Date(now));
  }
  try {
    await setDate("2026-10-10T03:00:00Z");
    await page.goto("/?published_from=2026-10-11");
    await expect(page.getByText("開始日だけを指定する場合は今日以前にしてください")).toBeVisible();
    await page.getByRole("button", { name: "すべての条件を解除", exact: true }).click();
    await expect(page).toHaveURL((url) => url.search === "");
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();

    await setDate("2026-10-11T03:00:00Z");
    await page.goBack({ waitUntil: "commit" });
    await expect
      .poll(
        async () =>
          new URL(page.url()).searchParams.has("published_to") ||
          (await page.getByText("開始日だけを指定する場合は今日以前にしてください").isVisible()),
      )
      .toBe(true);
    // 履歴キャッシュに前日の入力エラーが残る場合も、利用者の再取得で復旧する。
    if (!new URL(page.url()).searchParams.has("published_to"))
      await page.getByRole("button", { name: "再取得", exact: true }).click();
    await expect(page).toHaveURL((url) => url.searchParams.get("published_to") === "2026-10-11");
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    await expect(page.getByLabel("終了日", { exact: true })).toHaveValue("2026-10-11");
    const canonicalURL = page.url();
    await page.getByLabel("キーワード", { exact: true }).fill("保持する下書き");
    await page.getByRole("button", { name: "再取得", exact: true }).click();
    await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("保持する下書き");
    expect(page.url()).toBe(canonicalURL);

    await page.goForward({ waitUntil: "commit" });
    await expect(page).toHaveURL((url) => url.search === "");
    await setDate("2026-10-12T03:00:00Z");
    await page.goBack({ waitUntil: "commit" });
    await expect(page).toHaveURL(canonicalURL);
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    await expect(page.getByLabel("終了日", { exact: true })).toHaveValue("2026-10-11");
  } finally {
    await rm(clockFile, { force: true });
    await rm(`${clockFile}.tmp`, { force: true });
  }
});

test("不正URLでは一覧取得せず修正を案内する", async ({ page, request }) => {
  await page.goto("/?q=one&q=two&published_from=2026-02-30&page=0");
  await expect(page.getByText("URLの検索条件を修正してください")).toBeVisible();
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls.map((call: { path: string }) => call.path)).toEqual(["/fixed-categories"]);
});

test("正規化完了後にだけ正規条件を取得する", async ({ page, request }) => {
  await page.goto(
    "/?q=%20大気%20&fixed_category=%20soil%20&fixed_category=air&fixed_category=air&page=1&page_size=50&irrelevant=value&published_from=2026-01-05&published_to=2026-01-01",
  );
  await expect(page).toHaveURL(
    /\?q=.*&fixed_category=air&fixed_category=soil&published_from=2026-01-01&published_to=2026-01-05$/,
  );
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  const calls = await (await request.get(`${control}/__requests`)).json();
  expect(calls).toHaveLength(2);
  expect(
    new URLSearchParams(
      calls.find((call: { path: string }) => call.path === "/press-releases").query,
    ).get("q"),
  ).toBe("大気");
});

for (const [label, query, body, message] of [
  ["条件なし0件", "", result(0, []), "報道発表はまだありません"],
  ["条件あり0件", "?q=存在しない", result(0, []), "条件に一致する報道発表がありません"],
  ["範囲内件数差", "", result(1, []), "表示件数と一覧が一致しません。再取得してください"],
  ["範囲外", "?page=3", result(62, [], 3), "指定したページは範囲外です"],
] as const) {
  test(`正常な空応答を区別する ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__reset`, { data: { "/press-releases": { body } } });
    await page.goto(`/${query}`);
    await expect(page.getByText(message)).toBeVisible();
    await expect(page.getByRole("navigation", { name: "ページ送り" })).toHaveCount(
      label === "範囲内件数差" ? 1 : 0,
    );
  });
}

test("カテゴリ選択肢0件を失敗と区別する", async ({ page, request }) => {
  await request.post(`${control}/__reset`, {
    data: { "/fixed-categories": { body: { items: [] } } },
  });
  await page.goto("/");
  await expect(page.getByText("カテゴリ選択肢が未登録です")).toBeVisible();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
});

for (const [label, query, scenario] of [
  ["取得失敗", "", { status: 503 }],
  ["データなし", "", { body: result(0, []) }],
  ["検索結果なし", "?q=存在しない", { body: result(0, []) }],
] as const) {
  test(`採用済みの状態表示を引き継ぎ線画を装飾として扱う ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__reset`, { data: { "/press-releases": scenario } });
    await page.goto(`/${query}`);
    const decoration = page.locator(".release-results-decoration");
    await expect(decoration).toHaveCount(1);
    await expect(decoration).toHaveAttribute("aria-hidden", "true");
    await expect(decoration).toHaveAttribute("focusable", "false");
  });
}

test("同じURLで両APIを再取得し旧表示を隠して下書きを維持する", async ({ page, request }) => {
  await request.post(`${control}/__reset`, {
    data: {
      "/press-releases": [{}, { hold: "gate", body: result(1) }],
      "/fixed-categories": [{}, { hold: "gate" }],
    },
  });
  await page.goto("/?q=適用済み");
  await expect(page.getByLabel("キーワード", { exact: true })).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索の下書き");
  const url = page.url();
  await page.getByRole("button", { name: "再取得", exact: true }).click();
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toHaveCount(0);
  await expect(page.getByText("62", { exact: true })).toHaveCount(0);
  await expect(page.getByText("1 / 2ページ")).toHaveCount(0);
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  const calls = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
  });
  await expect(page.getByRole("link", { name: "安全な記事" })).toBeVisible();
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("未検索の下書き");
  expect(page.url()).toBe(url);
  expect(
    calls
      .filter((call: { path: string; query: string }) => call.path === "/press-releases")
      .every((call: { query: string }) => new URLSearchParams(call.query).get("q") === "適用済み"),
  ).toBe(true);
});

test("件数差からの再取得は現在条件と下書きと履歴を維持する", async ({ page, request }) => {
  await request.post(`${control}/__reset`, {
    data: { "/press-releases": [{ body: result(1, []) }, { hold: "gate" }] },
  });
  await page.goto("/?q=適用済み");
  await expect(page.getByText("表示件数と一覧が一致しません。再取得してください")).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("未検索の下書き");
  const url = page.url();
  const history = await page.evaluate(() => window.history.length);
  await page.getByRole("button", { name: "再取得", exact: true }).click();
  await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
  await expect
    .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
    .toBe(4);
  const calls = await (await request.get(`${control}/__requests`)).json();
  await request.post(`${control}/__release`, {
    data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
  });
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  expect(page.url()).toBe(url);
  expect(await page.evaluate(() => window.history.length)).toBe(history);
  await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue("未検索の下書き");
  expect(
    calls
      .filter((call: { path: string }) => call.path === "/press-releases")
      .every((call: { query: string }) => new URLSearchParams(call.query).get("q") === "適用済み"),
  ).toBe(true);
});

for (const action of ["すべての条件を解除", "unknownを解除", "1ページ目へ戻る"]) {
  test(`復旧操作でも取得中の旧情報を隠す ${action}`, async ({ page, request }) => {
    const range = action === "1ページ目へ戻る";
    await request.post(`${control}/__reset`, {
      data: { "/press-releases": [range ? { body: result(62, [], 3) } : {}, { hold: "gate" }] },
    });
    await page.goto(range ? "/?q=適用済み&page=3" : "/?q=適用済み&fixed_category=unknown");
    await expect(page.getByRole("button", { name: action, exact: true })).toBeEnabled();
    await page.getByLabel("キーワード", { exact: true }).fill("未検索の下書き");
    await page.getByRole("button", { name: action, exact: true }).click();
    await expect(page.getByText("報道発表を読み込んでいます")).toBeVisible();
    await expect(page.getByText("62", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/\/ 2ページ/)).toHaveCount(0);
    await expect
      .poll(async () => (await (await request.get(`${control}/__requests`)).json()).length)
      .toBe(4);
    const calls = await (await request.get(`${control}/__requests`)).json();
    await request.post(`${control}/__release`, {
      data: { ids: calls.slice(2).map((call: { id: number }) => call.id) },
    });
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    const cleared = action === "すべての条件を解除";
    await expect(page.getByLabel("キーワード", { exact: true })).toHaveValue(
      cleared ? "" : "未検索の下書き",
    );
    expect(new URL(page.url()).searchParams.get("q")).toBe(cleared ? null : "適用済み");
  });
}

test("不正条件を修正しページ1へ履歴追加する", async ({ page, request }) => {
  await page.goto("/?q=one&q=two&fixed_category=Invalid&page=0");
  await expect(page.getByRole("button", { name: "条件を修正して適用" })).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("修正値");
  await page.getByLabel("カテゴリslug（1行に1個）", { exact: true }).fill("soil");
  await page.getByLabel("ページ", { exact: true }).fill("1");
  await page.getByRole("button", { name: "条件を修正して適用" }).click();
  await expect(page).toHaveURL(
    (url) => url.searchParams.get("q") === "修正値" && !url.searchParams.has("page"),
  );
  expect(new URL(page.url()).searchParams.get("q")).toBe("修正値");
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  expect(new URL(page.url()).searchParams.getAll("fixed_category")).toEqual(["soil"]);
  const calls = await (await request.get(`${control}/__requests`)).json();
  const listCall = calls.find((call: { path: string }) => call.path === "/press-releases");
  expect(new URLSearchParams(listCall.query).getAll("fixed_category")).toEqual(["soil"]);
});

test("ドロワー内の修正は不正時に保持し成功時に閉じる", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?q=one&q=two&page=0");
  await expect(page.getByRole("button", { name: "条件を変更", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "条件を変更", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "検索条件" });
  await expect(dialog).toBeVisible();
  await page.getByLabel("キーワード", { exact: true }).fill("a".repeat(101));
  await page.getByLabel("ページ", { exact: true }).fill("1");
  const original = page.url();
  await page.getByRole("button", { name: "条件を修正して適用" }).click();
  await expect(dialog.getByText("キーワードは100文字以内で指定してください")).toBeVisible();
  await expect(dialog).toBeVisible();
  expect(page.url()).toBe(original);
  expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(1);
  await page.getByLabel("キーワード", { exact: true }).fill("修正値");
  await page.getByRole("button", { name: "条件を修正して適用" }).click();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: "条件を変更", exact: true })).toBeFocused();
});

for (const path of ["/press-releases", "/fixed-categories"]) {
  for (const hold of ["headers", "body"]) {
    test(`本文を含む10秒期限で中断し成功側を保持する ${path} ${hold}`, async ({
      page,
      request,
    }) => {
      test.setTimeout(20000);
      await request.post(`${control}/__reset`, { data: { [path]: { hold } } });
      const started = Date.now();
      await page.goto("/", { waitUntil: "commit" });
      const message =
        path === "/press-releases"
          ? "報道発表を取得できませんでした"
          : "カテゴリ選択肢を取得できませんでした";
      await expect(page.getByText(message)).toBeVisible({ timeout: 12500 });
      expect(Date.now() - started).toBeLessThan(13000);
      await expect
        .poll(async () => {
          const calls = await (await request.get(`${control}/__requests`)).json();
          return calls.find((call: { path: string }) => call.path === path)?.aborted;
        })
        .toBe(true);
      const calls = await (await request.get(`${control}/__requests`)).json();
      expect(calls).toHaveLength(2);
      const stopped = calls.find((call: { path: string }) => call.path === path);
      expect(stopped.cleanup).toBe(false);
      expect(stopped.finished).toBe(false);
      expect(stopped.closedAt - stopped.arrivedAt).toBeGreaterThanOrEqual(9500);
      expect(stopped.closedAt - stopped.arrivedAt).toBeLessThan(12000);
      if (path === "/fixed-categories")
        await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
      else await expect(page.getByRole("button", { name: "大気", exact: true })).toBeVisible();
      await request.post(`${control}/__configure`, { data: { [path]: {} } });
      await page.getByRole("button", { name: "再取得", exact: true }).click();
      await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
      await expect(page.getByRole("button", { name: "再取得", exact: true })).toBeEnabled();
      expect(await (await request.get(`${control}/__requests`)).json()).toHaveLength(4);
    });
  }
}

test("未定義カテゴリを保持し個別解除できる", async ({ page }) => {
  await page.goto("/?fixed_category=air&fixed_category=unknown&page=2");
  await expect(page.getByText("未定義カテゴリ：unknown")).toBeVisible();
  await page.getByRole("button", { name: "unknownを解除" }).click();
  await expect(page).toHaveURL(/\?fixed_category=air$/);
});

test("範囲外から他条件を維持してページ1へ戻る", async ({ page, request }) => {
  await request.post(`${control}/__reset`, {
    data: { "/press-releases": [{ body: result(62, [], 3) }, {}] },
  });
  await page.goto("/?q=大気&page=3");
  await expect(page.getByRole("button", { name: "1ページ目へ戻る" })).toBeVisible();
  await page.getByRole("button", { name: "1ページ目へ戻る" }).click();
  await expect(page).toHaveURL(/\?q=.*$/);
  expect(new URL(page.url()).searchParams.get("q")).toBe("大気");
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "報道発表一覧", exact: true })).toBeFocused();
});

test("日付422を両入力へ関連付け修正する", async ({ page, request }) => {
  await request.post(`${control}/__reset`, {
    data: {
      "/press-releases": [
        {
          status: 422,
          body: {
            detail: [{ loc: ["query", "published_to"], msg: "秘密の内部文言", input: "内部入力" }],
          },
        },
        {},
      ],
    },
  });
  await page.goto("/?published_from=2026-01-01&published_to=2026-01-05");
  await expect(page.getByLabel("開始日", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("終了日", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await page.getByLabel("終了日", { exact: true }).fill("2026-01-06");
  await page.getByRole("button", { name: "条件を修正して適用" }).click();
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  await expect(page.getByText("秘密の内部文言")).toHaveCount(0);
});

for (const remaining of [[], ["air"]]) {
  test(`日付422の修正で解除済みカテゴリを復活させない ${remaining.length ? "既知カテゴリを維持" : "カテゴリ指定なし"}`, async ({
    page,
    request,
  }) => {
    await request.post(`${control}/__reset`, {
      data: {
        "/press-releases": [
          {},
          { status: 422, body: { detail: [{ loc: ["query", "published_to"] }] } },
          {},
        ],
      },
    });
    const query = new URLSearchParams();
    for (const slug of [...remaining, "unknown"]) query.append("fixed_category", slug);
    query.set("published_from", "2026-01-01");
    query.set("published_to", "2026-01-05");
    await page.goto(`/?${query}`);
    await page.getByRole("button", { name: "unknownを解除", exact: true }).click();
    await expect(page.getByLabel("終了日", { exact: true })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(new URL(page.url()).searchParams.getAll("fixed_category")).toEqual(remaining);
    await page.getByLabel("終了日", { exact: true }).fill("2026-01-06");
    await page.getByRole("button", { name: "条件を修正して適用", exact: true }).click();
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    expect(new URL(page.url()).searchParams.getAll("fixed_category")).toEqual(remaining);
    const calls = await (await request.get(`${control}/__requests`)).json();
    const last = calls.filter((call: { path: string }) => call.path === "/press-releases").at(-1);
    const sent = new URLSearchParams(last.query);
    expect(sent.getAll("fixed_category")).toEqual(remaining);
    expect(sent.get("published_to")).toBe("2026-01-06");
  });
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${control}/__reset`, { data: {} });
  expect(response.ok()).toBe(true);
});

test.afterEach(async ({ request }) => {
  expect((await request.post(`${control}/__reset`, { data: {} })).ok()).toBe(true);
});

test("実API値のタイトル・件数・全所属を表示する", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  await expect(page.getByText("62", { exact: true })).toBeVisible();
  const list = page.getByRole("list", { name: "報道発表一覧" });
  await expect(list.getByText("大気", { exact: true })).toBeVisible();
  await expect(list.getByText("土壌", { exact: true })).toBeVisible();
  await expect(page.getByText("表示しない取得元カテゴリ")).toHaveCount(0);
  const response = await request.get(`${control}/__requests`);
  const calls = await response.json();
  expect(calls.map((call: { path: string }) => call.path).sort()).toEqual([
    "/fixed-categories",
    "/press-releases",
  ]);
});

for (const failed of ["/press-releases", "/fixed-categories", "both"]) {
  test(`取得失敗を個別表示し成功側を保持する ${failed}`, async ({ page, request }) => {
    const scenario = Object.fromEntries(
      ["/press-releases", "/fixed-categories"]
        .filter((path) => failed === "both" || path === failed)
        .map((path) => [path, { status: 503, raw: "内部接続情報は表示しない" }]),
    );
    await request.post(`${control}/__reset`, { data: scenario });
    await page.goto("/");
    if (failed !== "/fixed-categories")
      await expect(page.getByText("報道発表を取得できませんでした")).toBeVisible();
    else await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    if (failed !== "/press-releases")
      await expect(page.getByText("カテゴリ選択肢を取得できませんでした")).toBeVisible();
    else await expect(page.getByText("大気", { exact: true })).toBeVisible();
    await expect(page.getByText("内部接続情報は表示しない")).toHaveCount(0);
  });
}

for (const [label, params, invalid] of [
  ["キーワード100", { q: "a".repeat(100) }, false],
  ["キーワード101", { q: " " + "a".repeat(100) }, true],
  ["キーワードNUL", { q: "a\0b" }, true],
  ["Unicode100", { q: "𠮷".repeat(100) }, false],
  ["20重複", { fixed_category: Array(20).fill("air") }, false],
  ["21重複", { fixed_category: Array(21).fill("air") }, true],
  ["20空要素", { fixed_category: Array(20).fill("") }, false],
  ["21空要素", { fixed_category: Array(21).fill("") }, true],
  ["カテゴリ100", { fixed_category: " " + "a".repeat(98) + " " }, false],
  ["カテゴリ101", { fixed_category: " " + "a".repeat(99) + " " }, true],
  ["前後空白", { fixed_category: [" air ", "　soil　", "", "air"] }, false],
  ["全空白", { fixed_category: ["", "　", " "] }, false],
  ["不正slug混在", { fixed_category: ["air", "Soil"] }, true],
  ["slug末尾改行", { fixed_category: "air\ninvalid" }, true],
  ["ページ10000", { page: "10000" }, false],
  ["ページ10001", { page: "10001" }, true],
  ["ページ空値", { page: "" }, true],
  ["ページ重複", { page: ["1", "2"] }, true],
  ["page_size重複", { page_size: ["50", "50"] }, true],
  ["page_size10", { page_size: "10" }, true],
  ["日付全角", { published_to: "２０２６-01-01" }, true],
  ["日付空白", { published_to: " 2026-01-01" }, true],
  ["日付空値", { published_to: "" }, true],
  ["日付重複", { published_to: ["2026-01-01", "2026-01-02"] }, true],
  ["未来開始日だけ", { published_from: "9999-12-31" }, true],
  ["終了日だけ", { published_to: "2026-01-01" }, false],
] as const) {
  test(`URL入力の境界を守る ${label}`, async ({ page, request }) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params))
      for (const item of typeof value === "string" ? [value] : value) search.append(key, item);
    await page.goto(`/?${search}`);
    if (invalid) await expect(page.getByText("URLの検索条件を修正してください")).toBeVisible();
    else if (label === "ページ10000")
      await expect(page.getByText("指定したページは範囲外です")).toBeVisible();
    else await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
    const calls = await (await request.get(`${control}/__requests`)).json();
    expect(calls).toHaveLength(invalid ? 1 : 2);
    if (invalid) expect(calls[0].path).toBe("/fixed-categories");
    else
      expect(
        calls.filter((call: { path: string }) => call.path === "/press-releases"),
      ).toHaveLength(1);
  });
}

for (const [label, body] of [
  [
    "空userinfo",
    result(1, [
      {
        title: "安全な記事",
        source_url: "https://@example.invalid/safe",
        published_at: "2026-01-01",
        source_categories: null,
        fixed_categories: [],
      },
    ]),
  ],
  [
    "slug末尾改行",
    {
      ...result(),
      items: [{ ...result().items[0]!, fixed_categories: [{ slug: "air\n", name: "大気" }] }],
    },
  ],
  [
    "危険なリンク",
    result(1, [
      {
        title: "安全な記事",
        source_url: "javascript:alert(1)",
        published_at: "2026-01-01",
        source_categories: null,
        fixed_categories: [],
      },
    ]),
  ],
  [
    "不正日付",
    result(1, [
      {
        title: "安全な記事",
        source_url: "https://example.invalid/safe",
        published_at: "2026-02-30",
        source_categories: null,
        fixed_categories: [],
      },
    ]),
  ],
  [
    "不正件数",
    { ...result(), pagination: { page: 1, page_size: 50, total_items: -1, total_pages: 1 } },
  ],
  ["重複リンク", result(2, [result().items[0]!, result().items[0]!])],
  [
    "要求ページの不一致",
    { ...result(), pagination: { page: 2, page_size: 50, total_items: 1, total_pages: 1 } },
  ],
  [
    "件数が文字列",
    { ...result(), pagination: { page: 1, page_size: 50, total_items: "1", total_pages: 1 } },
  ],
] as const) {
  test(`不正な成功応答を取得失敗として扱う ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__reset`, { data: { "/press-releases": { body } } });
    await page.goto("/");
    await expect(page.getByText("報道発表を取得できませんでした")).toBeVisible();
    await expect(page.getByRole("link", { name: "安全な記事" })).toHaveCount(0);
  });
}

for (const [label, items] of [
  [
    "順序逆転",
    [
      { slug: "soil", name: "土壌", display_order: 2 },
      { slug: "air", name: "大気", display_order: 1 },
    ],
  ],
  [
    "重複slug",
    [
      { slug: "air", name: "大気", display_order: 1 },
      { slug: "air", name: "大気", display_order: 2 },
    ],
  ],
  ["順序0", [{ slug: "air", name: "大気", display_order: 0 }]],
  ["空名称", [{ slug: "air", name: "", display_order: 1 }]],
] as const) {
  test(`不正な選択肢を利用せず成功した一覧を保持する ${label}`, async ({ page, request }) => {
    await request.post(`${control}/__reset`, {
      data: { "/fixed-categories": { body: { items } } },
    });
    await page.goto("/");
    await expect(page.getByText("カテゴリ選択肢を取得できませんでした")).toBeVisible();
    await expect(page.getByRole("link", { name: "API由来の報道発表" })).toBeVisible();
  });
}

test("APIのタイトルとカテゴリ名をHTMLとして実行しない", async ({ page, request }) => {
  const text = '<img src="https://example.invalid/unsafe" onerror="alert(1)">';
  const item = {
    ...result().items[0]!,
    title: text,
    fixed_categories: [{ slug: "air", name: text }],
  };
  await request.post(`${control}/__reset`, {
    data: {
      "/press-releases": { body: result(1, [item]) },
      "/fixed-categories": { body: { items: [{ slug: "air", name: text, display_order: 1 }] } },
    },
  });
  let dialogs = 0;
  const external: string[] = [];
  page.on("dialog", async (dialog) => {
    dialogs++;
    await dialog.dismiss();
  });
  page.on("request", (call) => {
    if (new URL(call.url()).origin !== "http://127.0.0.1:3106") external.push(call.url());
  });
  await page.goto("/");
  await expect(page.getByRole("link", { name: text })).toHaveText(text);
  await expect(page.locator(".release-category")).toHaveText(text);
  expect(dialogs).toBe(0);
  expect(external).toEqual([]);
});
