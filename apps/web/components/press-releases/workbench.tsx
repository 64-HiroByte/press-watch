"use client";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  useTransition,
  type FormEvent,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { ChevronDownIcon, PencilLineIcon } from "lucide-react";
import { ScrollRegion } from "@/components/press-releases/scroll-region";
import { DisplayTooltip } from "@/components/press-releases/display-tooltip";
import { SidebarFilters } from "@/components/press-releases/sidebar-filters";
import { ListThemeToggle } from "@/components/press-releases/theme-toggle";
import { PressReleaseStatus } from "@/components/press-releases/status";
import { ListPagination } from "@/components/press-releases/pagination";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SearchForm } from "@/components/press-releases/search-form";
import { CategoryFilters } from "@/components/press-releases/category-filters";
import { periodDates, type Period } from "@/lib/press-release-dates";
import type { CategoryOption, ListData } from "@/lib/press-releases-api";
import { MAX_FIXED_CATEGORY_COUNT } from "@/lib/press-release-values";
import { NARROW_SCREEN_QUERY } from "@/lib/press-release-layout";
import {
  parseQuery,
  queryString,
  type Conditions,
  type QueryState,
  type QueryField,
  type SearchValues,
} from "@/lib/press-release-query";

type Props = {
  query: QueryState;
  options: CategoryOption[] | null;
  dateError: boolean;
  outOfRange: boolean;
  summary: ReactNode;
  pagination: ListData["pagination"] | null;
  children: ReactNode;
};

function currentValues(): SearchValues {
  const params = new URLSearchParams(window.location.search);
  return Object.fromEntries(
    [...new Set(params.keys())].map((key) => {
      const values = params.getAll(key);
      return [key, values.length === 1 ? values[0] : values];
    }),
  );
}

function draftValues(query: QueryState) {
  return query.errors.length
    ? query.raw
    : {
        q: query.conditions.q,
        from: query.conditions.from,
        to: query.conditions.to,
        categories: query.conditions.categories.join("\n"),
        page: String(query.conditions.page),
      };
}

function subscribeWidth(callback: () => void) {
  const media = window.matchMedia(NARROW_SCREEN_QUERY);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

export function ListWorkbench({
  query,
  options,
  dateError,
  outOfRange,
  summary,
  pagination,
  children,
}: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [navigationURL, setNavigationURL] = useState<string | null>(null);
  const [draft, setDraft] = useState(() => draftValues(query));
  const [localErrors, setLocalErrors] = useState<string[]>([]);
  const [localErrorFields, setLocalErrorFields] = useState<QueryField[]>([]);
  const [period, setPeriod] = useState<{ value: Period; from: string; to: string } | null>(null);
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const [textSize, setTextSize] = useState<"standard" | "large">("standard");
  const narrow = useSyncExternalStore(
    subscribeWidth,
    () => window.matchMedia(NARROW_SCREEN_QUERY).matches,
    () => false,
  );
  const conditionsExpanded = expanded ?? !narrow;
  const mainRef = useRef<HTMLDivElement>(null);
  const searchFormRef = useRef<HTMLFormElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const lock = useRef(false);
  const pageFocusURL = useRef<string | null>(null);
  const normalizing = !query.errors.length && query.original !== query.canonical;
  const isBusy =
    pending || normalizing || (navigationURL !== null && navigationURL !== query.original);
  const canChange = !isBusy && options !== null && options.length > 0;
  const repair = query.errors.length > 0 || dateError;
  const canChangeCategories = canChange && !repair;

  useEffect(() => {
    if (!isBusy) lock.current = false;
  }, [isBusy]);

  useEffect(() => {
    if (isBusy || pageFocusURL.current !== query.original) return;
    pageFocusURL.current = null;
    titleRef.current?.focus({ preventScroll: true });
    if (window.matchMedia(NARROW_SCREEN_QUERY).matches) {
      titleRef.current?.scrollIntoView({ block: "start", behavior: "instant" });
    } else {
      headerRef.current
        ?.querySelector(".release-header-body")
        ?.scrollTo({ top: 0, behavior: "instant" });
      mainRef.current?.scrollTo({ top: 0, behavior: "instant" });
    }
  }, [isBusy, query.original]);

  useEffect(() => {
    if (normalizing)
      startTransition(() => {
        setNavigationURL(query.canonical);
        router.replace(query.canonical ? `/?${query.canonical}` : "/", { scroll: false });
      });
  }, [normalizing, query.canonical, router]);

  useEffect(() => {
    function restore() {
      pageFocusURL.current = null;
      const restored = parseQuery(currentValues());
      clearIncompleteDates();
      setDraft(draftValues(restored));
      setLocalErrors([]);
      setLocalErrorFields([]);
      setPeriod(null);
      setNavigationURL(restored.original);
    }
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    const main = mainRef.current;
    const header = headerRef.current;
    if (!main || !header) return;
    const update = () =>
      main.style.setProperty("--release-header-height", `${header.offsetHeight}px`);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(header, { box: "border-box" });
    return () => {
      observer.disconnect();
      main.style.removeProperty("--release-header-height");
    };
  }, []);

  function navigate(conditions?: Conditions, moveToResults = false) {
    if (isBusy || lock.current || (conditions && !canChange)) return;
    const target = conditions ? queryString(conditions) : query.original;
    if (moveToResults && target === query.original) return;
    lock.current = true;
    pageFocusURL.current = moveToResults ? target : null;
    setNavigationURL(target);
    startTransition(() => {
      if (target === query.original) router.refresh();
      else router.push(target ? `/?${target}` : "/", { scroll: false });
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canChange || lock.current) return false;
    const incomplete = (["from", "to"] as const).filter(
      (field) =>
        event.currentTarget.querySelector<HTMLInputElement>(`#release-date-${field}`)?.validity
          .badInput,
    );
    function reject(errors: string[], fields: QueryField[]) {
      setLocalErrors(errors);
      setLocalErrorFields(fields);
      const ids = {
        q: "release-keyword",
        from: "release-date-from",
        to: "release-date-to",
        categories: "release-repair-categories",
        page: "release-repair-page",
      };
      if (fields[0]) event.currentTarget.querySelector<HTMLElement>(`#${ids[fields[0]]}`)?.focus();
      return false;
    }
    if (incomplete.length)
      return reject(["公開日はYYYY-MM-DDの実在日で指定してください"], incomplete);
    const corrected = parseQuery({
      q: draft.q,
      published_from: draft.from || undefined,
      published_to: draft.to || undefined,
      fixed_category: query.errors.length
        ? draft.categories.split("\n")
        : query.conditions.categories,
      page: query.errors.length ? draft.page || undefined : "1",
    });
    if (corrected.errors.length) {
      return reject(corrected.errors, corrected.errorFields);
    }
    setLocalErrors([]);
    setLocalErrorFields([]);
    setDraft(draftValues(corrected));
    if (
      period &&
      (corrected.conditions.from !== period.from || corrected.conditions.to !== period.to)
    )
      setPeriod(null);
    navigate({ ...corrected.conditions, page: 1 });
    return true;
  }

  function clearIncompleteDates() {
    // 未完成の日付はvalueが既に空なので、状態更新だけでは表示が消えない。
    searchFormRef.current
      ?.querySelectorAll<HTMLInputElement>('input[type="date"]')
      .forEach((input) => {
        if (input.validity.badInput) input.value = "";
      });
  }

  const updateDraft = (key: keyof typeof draft, value: string) => {
    pageFocusURL.current = null;
    if (period && (key === "from" || key === "to") && value !== period[key]) setPeriod(null);
    setDraft((current) => ({ ...current, [key]: value }));
  };
  function selectPeriod(value: Period) {
    pageFocusURL.current = null;
    if (value === "custom") setPeriod(null);
    else {
      const dates = periodDates(value, new Date());
      setPeriod({ value, ...dates });
      setDraft((current) => ({ ...current, ...dates }));
    }
  }
  function resetSearch() {
    if (!canChange || lock.current || query.errors.length) return;
    clearIncompleteDates();
    const conditions = { ...query.conditions, q: "", from: "", to: "", page: 1 };
    pageFocusURL.current = null;
    setDraft({ ...draft, q: "", from: "", to: "", page: "1" });
    setLocalErrors([]);
    setLocalErrorFields([]);
    setPeriod(null);
    if (queryString(conditions) !== query.original) navigate(conditions);
  }
  function changeCategories(values: string[]) {
    if (!canChangeCategories || lock.current) return;
    const categories = [...new Set(values)].sort();
    if (categories.length > MAX_FIXED_CATEGORY_COUNT) return;
    if (
      categories.length === query.conditions.categories.length &&
      categories.every((slug, index) => slug === query.conditions.categories[index])
    )
      return;
    navigate({ ...query.conditions, categories, page: 1 });
  }
  const filtered = !!(
    query.conditions.q ||
    query.conditions.from ||
    query.conditions.to ||
    query.conditions.categories.length
  );

  return (
    <main
      className="release-workbench"
      onFocusCapture={() => {
        pageFocusURL.current = null;
      }}
    >
      <section
        className="release-preview"
        data-design="sidebar"
        data-text-size={textSize}
        aria-label="報道発表の一覧画面"
      >
        <SidebarFilters
          fallbackFocusRef={titleRef}
          renderMain={({ drawerOpen, openDrawer, triggerRef, rememberTriggerFocus }) => (
            <ScrollRegion ref={mainRef}>
              <header ref={headerRef} className="release-header">
                <div className="release-header-body">
                  <div className="release-header-top">
                    <h1 ref={titleRef} tabIndex={-1}>
                      報道発表一覧
                    </h1>
                    <div className="release-display-controls">
                      <fieldset className="release-text-options">
                        <legend className="sr-only">文字サイズ</legend>
                        <div className="release-text-buttons">
                          {(["standard", "large"] as const).map((size) => (
                            <DisplayTooltip
                              key={size}
                              label={size === "standard" ? "標準の文字サイズ" : "大きい文字サイズ"}
                            >
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label={
                                  size === "standard" ? "標準の文字サイズ" : "大きい文字サイズ"
                                }
                                aria-pressed={textSize === size}
                                onClick={() => setTextSize(size)}
                              >
                                <span
                                  className="release-text-symbol"
                                  data-size={size}
                                  aria-hidden="true"
                                >
                                  あ
                                </span>
                              </Button>
                            </DisplayTooltip>
                          ))}
                        </div>
                      </fieldset>
                      <ListThemeToggle />
                    </div>
                  </div>
                  <div className="release-condition-controls">
                    <Button
                      type="button"
                      variant="ghost"
                      className="release-conditions-disclosure"
                      aria-expanded={conditionsExpanded}
                      aria-controls="release-applied-values"
                      onClick={() => setExpanded(!conditionsExpanded)}
                    >
                      条件の詳細
                      <ChevronDownIcon aria-hidden="true" />
                    </Button>
                    <Button
                      ref={triggerRef}
                      type="button"
                      variant="ghost"
                      className="release-conditions-trigger"
                      aria-haspopup="dialog"
                      aria-controls="release-filter-panel"
                      aria-expanded={drawerOpen}
                      onClick={() => {
                        pageFocusURL.current = null;
                        openDrawer();
                      }}
                      onFocus={rememberTriggerFocus}
                    >
                      <PencilLineIcon aria-hidden="true" />
                      {filtered ? "条件を変更" : "検索条件を設定"}
                    </Button>
                  </div>
                  <dl
                    id="release-applied-values"
                    className="release-applied-conditions"
                    hidden={!conditionsExpanded}
                  >
                    <div className="release-applied-row">
                      <dt className="release-applied-label">キーワード</dt>
                      <dd className="release-applied-value">{query.conditions.q || "指定なし"}</dd>
                    </div>
                    <div className="release-applied-row">
                      <dt className="release-applied-label">公開日</dt>
                      <dd className="release-applied-value">
                        {query.conditions.from || query.conditions.to
                          ? `${query.conditions.from || "開始日指定なし"} 〜 ${query.conditions.to || "終了日指定なし"}`
                          : "指定なし"}
                      </dd>
                    </div>
                    <div className="release-applied-row">
                      <dt className="release-applied-label">カテゴリ</dt>
                      <dd className="release-applied-values">
                        {query.conditions.categories.length
                          ? query.conditions.categories.map((slug) => (
                              <span key={slug}>
                                <Badge variant="outline" className="release-category">
                                  {options?.find((option) => option.slug === slug)?.name ??
                                    (options ? `未定義カテゴリ：${slug}` : slug)}
                                </Badge>
                                {options && !options.some((option) => option.slug === slug) && (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    disabled={!canChange || repair}
                                    aria-label={`${slug}を解除`}
                                    onClick={() =>
                                      changeCategories(
                                        query.conditions.categories.filter(
                                          (value) => value !== slug,
                                        ),
                                      )
                                    }
                                  >
                                    解除
                                  </Button>
                                )}
                              </span>
                            ))
                          : "すべてのカテゴリ"}
                      </dd>
                    </div>
                  </dl>
                  {!isBusy && summary}
                </div>
              </header>
              <div className="release-content">
                {isBusy ? (
                  <PressReleaseStatus state="loading" />
                ) : (
                  <>
                    {query.errors.length > 0 && (
                      <div role="alert">
                        <p>URLの検索条件を修正してください</p>
                        {query.errors.map((error) => (
                          <p key={error}>{error}</p>
                        ))}
                      </div>
                    )}
                    {children}
                    <ListPagination
                      pagination={pagination}
                      conditions={query.conditions}
                      disabled={!canChange || repair}
                      onPageChange={(page) => navigate({ ...query.conditions, page }, true)}
                    />
                    {outOfRange && (
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!canChange || repair}
                        onClick={() => navigate({ ...query.conditions, page: 1 }, true)}
                      >
                        1ページ目へ戻る
                      </Button>
                    )}
                  </>
                )}
                <div className="release-recovery-actions">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={isBusy}
                    onClick={() => navigate()}
                  >
                    再取得
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!canChange || (!filtered && !repair)}
                    onClick={() => {
                      clearIncompleteDates();
                      setDraft({ q: "", from: "", to: "", categories: "", page: "1" });
                      setLocalErrors([]);
                      setLocalErrorFields([]);
                      setPeriod(null);
                      navigate({ q: "", from: "", to: "", categories: [], page: 1 });
                    }}
                  >
                    すべての条件を解除
                  </Button>
                </div>
              </div>
            </ScrollRegion>
          )}
        >
          <SearchForm
            formRef={searchFormRef}
            draft={draft}
            updateDraft={updateDraft}
            period={period?.value ?? "custom"}
            onPeriodChange={selectPeriod}
            canChange={canChange}
            invalidURL={query.errors.length > 0}
            repair={repair}
            dateError={!isBusy && dateError}
            errors={localErrors.length ? localErrors : query.errors}
            errorFields={localErrors.length ? localErrorFields : query.errorFields}
            onApply={submit}
            onReset={resetSearch}
          />
          <CategoryFilters
            options={options}
            selected={query.conditions.categories}
            isBusy={isBusy}
            canChange={canChangeCategories}
            onToggle={(slug) =>
              changeCategories(
                query.conditions.categories.includes(slug)
                  ? query.conditions.categories.filter((value) => value !== slug)
                  : [...query.conditions.categories, slug],
              )
            }
            onSelectAll={() =>
              changeCategories([
                ...query.conditions.categories,
                ...(options?.map((option) => option.slug) ?? []),
              ])
            }
            onClear={() => changeCategories([])}
          />
        </SidebarFilters>
      </section>
    </main>
  );
}
