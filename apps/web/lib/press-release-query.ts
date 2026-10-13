import {
  categorySlug,
  MAX_FIXED_CATEGORY_COUNT,
  MAX_FIXED_CATEGORY_SLUG_LENGTH,
  MAX_SEARCH_KEYWORD_LENGTH,
  validDate,
} from "./press-release-values";
import { tokyoToday } from "./press-release-dates";

export type SearchValues = Record<string, string | string[] | undefined>;
export type Conditions = {
  q: string;
  from: string;
  to: string;
  categories: string[];
  page: number;
};
export type QueryState = {
  conditions: Conditions;
  raw: { q: string; from: string; to: string; categories: string; page: string };
  errors: string[];
  errorFields: QueryField[];
  canonical: string;
  original: string;
};
export type QueryField = keyof QueryState["raw"];
function whitespace(code: number) {
  return (
    (code >= 9 && code <= 13) ||
    (code >= 0x1c && code <= 0x20) ||
    (code >= 0x2000 && code <= 0x200a) ||
    [0x85, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000].includes(code)
  );
}

function trim(value: string) {
  // APIのstr.stripと同じ空白を除き、文字数制限は除去前に適用する。
  let start = 0;
  let end = value.length;
  while (start < end && whitespace(value.charCodeAt(start))) start++;
  while (end > start && whitespace(value.charCodeAt(end - 1))) end--;
  return value.slice(start, end);
}

export function queryString(conditions: Conditions): string {
  const query = new URLSearchParams();
  if (conditions.q) query.set("q", conditions.q);
  for (const slug of conditions.categories) query.append("fixed_category", slug);
  if (conditions.from) query.set("published_from", conditions.from);
  if (conditions.to) query.set("published_to", conditions.to);
  if (conditions.page !== 1) query.set("page", String(conditions.page));
  return query.toString();
}

export function parseQuery(values: SearchValues, now = new Date()): QueryState {
  const original = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    for (const item of typeof value === "string" ? [value] : (value ?? []))
      original.append(key, item);
  const errors: string[] = [];
  const errorFields: QueryField[] = [];
  function error(message: string, ...fields: QueryField[]) {
    errors.push(message);
    errorFields.push(...fields);
  }
  function single(key: string, field: QueryField) {
    const value = values[key];
    if (Array.isArray(value)) error(`${key}を複数指定できません`, field);
    return typeof value === "string" ? value : (value?.[0] ?? "");
  }
  const q = single("q", "q");
  const from = single("published_from", "from");
  const to = single("published_to", "to");
  const page = single("page", "page");
  const size = single("page_size", "page");
  const categoryValues = values.fixed_category;
  const categories = typeof categoryValues === "string" ? [categoryValues] : (categoryValues ?? []);
  if (Array.from(q).length > MAX_SEARCH_KEYWORD_LENGTH || q.includes("\0"))
    error(`キーワードは${MAX_SEARCH_KEYWORD_LENGTH}文字以内で指定してください`, "q");
  if (
    categories.length > MAX_FIXED_CATEGORY_COUNT ||
    categories.some(
      (slug) =>
        Array.from(slug).length > MAX_FIXED_CATEGORY_SLUG_LENGTH ||
        (trim(slug) !== "" && !categorySlug.test(trim(slug))),
    )
  )
    error(
      `カテゴリは正しいslugを${MAX_FIXED_CATEGORY_COUNT}個以内、各${MAX_FIXED_CATEGORY_SLUG_LENGTH}文字以内で指定してください`,
      "categories",
    );
  if (
    (values.published_from !== undefined && !validDate(from)) ||
    (values.published_to !== undefined && !validDate(to))
  )
    error(
      "公開日はYYYY-MM-DDの実在日で指定してください",
      ...(values.published_from !== undefined && !validDate(from) ? ["from" as const] : []),
      ...(values.published_to !== undefined && !validDate(to) ? ["to" as const] : []),
    );
  if (
    values.page !== undefined &&
    (!/^[0-9]+$/.test(page) || Number(page) < 1 || Number(page) > 10000)
  )
    error("ページは1から10000で指定してください", "page");
  if ((size && size !== "50") || (values.page_size !== undefined && size === ""))
    error("page_sizeは50だけを指定できます", "page");
  const conditions: Conditions = {
    q: trim(q),
    from,
    to,
    categories: [...new Set(categories.map(trim).filter(Boolean))].sort(),
    page: Number(page || 1),
  };
  if (!errors.length) {
    if (from && to && from > to) {
      conditions.from = to;
      conditions.to = from;
    } else if (from && !to) {
      const today = tokyoToday(now);
      if (from > today) error("開始日だけを指定する場合は今日以前にしてください", "from");
      else conditions.to = today;
    }
  }
  return {
    conditions,
    raw: { q, from, to, categories: categories.join("\n"), page },
    errors,
    errorFields: [...new Set(errorFields)],
    canonical: queryString(conditions),
    original: original.toString(),
  };
}
