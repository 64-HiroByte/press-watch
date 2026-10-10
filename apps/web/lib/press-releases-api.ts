import "server-only";

import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { categorySlug, safeHttpURL, validDate } from "@/lib/press-release-values";

export type CategoryOption = FixedCategoryLabel & { display_order: number };
export type ListData = {
  items: {
    title: string;
    source_url: string;
    published_at: string;
    source_categories: string[] | null;
    fixed_categories: FixedCategoryLabel[];
  }[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number };
};
export type ApiResult<T> = { ok: true; data: T } | { ok: false; dateError: boolean };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function label(value: unknown): value is FixedCategoryLabel {
  return (
    object(value) &&
    typeof value.slug === "string" &&
    value.slug.length <= 100 &&
    categorySlug.test(value.slug) &&
    typeof value.name === "string" &&
    !!value.name.trim() &&
    !value.name.includes("\0")
  );
}

function unique(values: readonly string[]): boolean {
  return new Set(values).size === values.length;
}

function listData(value: unknown): value is ListData {
  if (
    !object(value) ||
    !Array.isArray(value.items) ||
    value.items.length > 50 ||
    !object(value.pagination)
  )
    return false;
  const p = value.pagination;
  if (
    ![p.page, p.page_size, p.total_items, p.total_pages].every(Number.isSafeInteger) ||
    (p.page as number) < 1 ||
    (p.page as number) > 10000 ||
    p.page_size !== 50 ||
    (p.total_items as number) < 0 ||
    p.total_pages !== Math.ceil((p.total_items as number) / 50)
  )
    return false;
  if (
    !value.items.every(
      (item: unknown) =>
        object(item) &&
        typeof item.title === "string" &&
        !!item.title.trim() &&
        !item.title.includes("\0") &&
        typeof item.source_url === "string" &&
        safeHttpURL(item.source_url) &&
        typeof item.published_at === "string" &&
        validDate(item.published_at) &&
        (item.source_categories === null ||
          (Array.isArray(item.source_categories) &&
            item.source_categories.every((entry: unknown) => typeof entry === "string"))) &&
        Array.isArray(item.fixed_categories) &&
        item.fixed_categories.every(label) &&
        unique(item.fixed_categories.map((entry: FixedCategoryLabel) => entry.slug)),
    )
  )
    return false;
  return unique(value.items.map((item) => item.source_url));
}

function categoryData(value: unknown): value is { items: CategoryOption[] } {
  if (!object(value) || !Array.isArray(value.items)) return false;
  return (
    value.items.every(
      (item) =>
        object(item) &&
        Number.isSafeInteger(item.display_order) &&
        (item.display_order as number) > 0 &&
        label(item),
    ) &&
    unique(value.items.map((item) => item.slug)) &&
    unique(value.items.map((item) => String(item.display_order))) &&
    value.items.every(
      (item, index, items) => index === 0 || items[index - 1].display_order < item.display_order,
    )
  );
}

async function get<T>(
  path: string,
  validate: (value: unknown) => value is T,
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const configured = process.env.PRESSWATCH_API_BASE_URL;
    if (!configured || !safeHttpURL(configured)) return { ok: false, dateError: false };
    const base = new URL(configured);
    if (base.search || base.hash) return { ok: false, dateError: false };
    const response = await fetch(`${base.toString().replace(/\/$/, "")}${path}`, {
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
    });
    if (!response.ok) {
      let dateError = false;
      if (response.status === 422) {
        const error: unknown = await response.json();
        dateError =
          object(error) &&
          Array.isArray(error.detail) &&
          error.detail.some(
            (entry: unknown) =>
              object(entry) &&
              Array.isArray(entry.loc) &&
              entry.loc.length === 2 &&
              entry.loc[0] === "query" &&
              ["published_from", "published_to"].includes(entry.loc[1]),
          );
      }
      return { ok: false, dateError };
    }
    if (!/^application\/json(?:;|$)/i.test(response.headers.get("content-type") ?? ""))
      return { ok: false, dateError: false };
    const data: unknown = await response.json();
    if (!validate(data)) return { ok: false, dateError: false };
    return { ok: true, data };
  } catch {
    return { ok: false, dateError: false };
  } finally {
    clearTimeout(timer);
    controller.abort();
  }
}

export async function getList(query = "", invalid = false) {
  const page = Number(new URLSearchParams(query).get("page") ?? 1);
  const [list, categories] = await Promise.allSettled([
    invalid
      ? Promise.resolve(null)
      : get(
          `/press-releases${query ? `?${query}` : ""}`,
          (value): value is ListData => listData(value) && value.pagination.page === page,
        ),
    get("/fixed-categories", categoryData),
  ]);
  const failure = { ok: false, dateError: false } as const;
  return {
    list: list.status === "fulfilled" ? list.value : failure,
    categories: categories.status === "fulfilled" ? categories.value : failure,
  };
}
