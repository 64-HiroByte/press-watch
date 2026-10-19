import {
  categorySlug,
  LIST_PAGE_SIZE,
  MAX_FIXED_CATEGORY_COUNT,
  MAX_FIXED_CATEGORY_SLUG_LENGTH,
  MAX_LIST_PAGE,
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
export type ConditionState = Pick<QueryState, "conditions" | "raw" | "errors" | "errorFields">;
type ConditionValues = {
  q?: string;
  from?: string;
  to?: string;
  categories: string[];
  page?: string;
  pageSize?: string;
};
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

function webSearchString(query: URLSearchParams): string {
  return [...query]
    .map(([key, value]) => {
      const encoded = new URLSearchParams([[key, value]]).toString();
      // カテゴリの区切りだけを表示し、検索語などのエンコードは維持する。
      return key === "categories" ? encoded.replaceAll("%2C", ",") : encoded;
    })
    .join("&");
}

export function webQueryString(conditions: Conditions): string {
  const query = new URLSearchParams();
  if (conditions.q) query.set("q", conditions.q);
  if (conditions.categories.length) query.set("categories", conditions.categories.join(","));
  if (conditions.from) query.set("from", conditions.from);
  if (conditions.to) query.set("to", conditions.to);
  if (conditions.page !== 1) query.set("page", String(conditions.page));
  return webSearchString(query);
}

export function parseQuery(values: SearchValues, now = new Date()): QueryState {
  const original = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    for (const item of typeof value === "string" ? [value] : (value ?? []))
      original.append(key, item);
  const errors: string[] = [];
  const errorFields: QueryField[] = [];
  function single(key: string, field: QueryField) {
    const value = values[key];
    if (Array.isArray(value)) {
      errors.push(`${key}を複数指定できません`);
      errorFields.push(field);
    }
    return typeof value === "string" ? value : value?.[0];
  }
  const q = single("q", "q");
  const from = single("from", "from");
  const to = single("to", "to");
  const page = single("page", "page");
  const pageSize = single("page_size", "page");
  const categories = single("categories", "categories")?.split(",") ?? [];
  const state = validateValues(
    { q, from, to, categories, page, pageSize },
    now,
    errors,
    errorFields,
  );
  return {
    ...state,
    canonical: webQueryString(state.conditions),
    original: webSearchString(original),
  };
}

export function validateForm(raw: QueryState["raw"], now = new Date()): ConditionState {
  return validateValues(
    {
      q: raw.q,
      from: raw.from || undefined,
      to: raw.to || undefined,
      categories: raw.categories.split("\n"),
      page: raw.page || undefined,
    },
    now,
  );
}

function validateValues(
  values: ConditionValues,
  now: Date,
  errors: string[] = [],
  errorFields: QueryField[] = [],
): ConditionState {
  const { q = "", from = "", to = "", categories, page = "", pageSize: size = "" } = values;
  function error(message: string, ...fields: QueryField[]) {
    errors.push(message);
    errorFields.push(...fields);
  }
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
    (values.from !== undefined && !validDate(from)) ||
    (values.to !== undefined && !validDate(to))
  )
    error(
      "公開日はYYYY-MM-DDの実在日で指定してください",
      ...(values.from !== undefined && !validDate(from) ? ["from" as const] : []),
      ...(values.to !== undefined && !validDate(to) ? ["to" as const] : []),
    );
  if (
    values.page !== undefined &&
    (!/^[0-9]+$/.test(page) || Number(page) < 1 || Number(page) > MAX_LIST_PAGE)
  )
    error(`ページは1から${MAX_LIST_PAGE}で指定してください`, "page");
  if ((size && size !== String(LIST_PAGE_SIZE)) || (values.pageSize !== undefined && size === ""))
    error(`page_sizeは${LIST_PAGE_SIZE}だけを指定できます`, "page");
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
  };
}
