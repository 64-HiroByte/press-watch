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
import { SidebarFilters, SidebarForm } from "@/components/press-releases/sidebar-filters";
import { ListThemeToggle } from "@/components/press-releases/theme-toggle";
import { PressReleaseStatus } from "@/components/press-releases/status";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CategoryOption } from "@/lib/press-releases-api";
import {
  parseQuery,
  queryString,
  type Conditions,
  type QueryState,
  type SearchValues,
} from "@/lib/press-release-query";

type Props = {
  query: QueryState;
  options: CategoryOption[] | null;
  dateError: boolean;
  outOfRange: boolean;
  summary: ReactNode;
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
  const media = window.matchMedia("(width < 768px)");
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

export function ListWorkbench({ query, options, dateError, outOfRange, summary, children }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [navigationURL, setNavigationURL] = useState<string | null>(null);
  const [draft, setDraft] = useState(() => draftValues(query));
  const [localErrors, setLocalErrors] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const [textSize, setTextSize] = useState<"standard" | "large">("standard");
  const narrow = useSyncExternalStore(
    subscribeWidth,
    () => window.matchMedia("(width < 768px)").matches,
    () => false,
  );
  const conditionsExpanded = expanded ?? !narrow;
  const mainRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const lock = useRef(false);
  const normalizing = !query.errors.length && query.original !== query.canonical;
  const busy =
    pending || normalizing || (navigationURL !== null && navigationURL !== query.original);
  const canChange = !busy && options !== null && options.length > 0;
  const repair = query.errors.length > 0 || dateError;

  useEffect(() => {
    if (!busy) lock.current = false;
  }, [busy]);

  useEffect(() => {
    if (normalizing)
      startTransition(() =>
        router.replace(query.canonical ? `/?${query.canonical}` : "/", { scroll: false }),
      );
  }, [normalizing, query.canonical, router]);

  useEffect(() => {
    function restore() {
      const restored = parseQuery(currentValues());
      setDraft(draftValues(restored));
      setLocalErrors([]);
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

  function navigate(conditions?: Conditions) {
    if (busy || lock.current || (conditions && !canChange)) return;
    lock.current = true;
    const target = conditions ? queryString(conditions) : query.original;
    setNavigationURL(target);
    startTransition(() => {
      if (target === query.original) router.refresh();
      else router.push(target ? `/?${target}` : "/", { scroll: false });
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canChange || !repair) return false;
    const corrected = parseQuery({
      q: draft.q,
      published_from: draft.from || undefined,
      published_to: draft.to || undefined,
      fixed_category: query.errors.length
        ? draft.categories.split("\n")
        : query.conditions.categories,
      page: draft.page || undefined,
    });
    if (corrected.errors.length) {
      setLocalErrors(corrected.errors);
      return false;
    }
    setLocalErrors([]);
    setDraft(draftValues(corrected));
    navigate({ ...corrected.conditions, page: 1 });
    return true;
  }

  const updateDraft = (key: keyof typeof draft, value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const filtered = !!(
    query.conditions.q ||
    query.conditions.from ||
    query.conditions.to ||
    query.conditions.categories.length
  );

  return (
    <main className="release-workbench">
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
                      onClick={openDrawer}
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
                                      navigate({
                                        ...query.conditions,
                                        categories: query.conditions.categories.filter(
                                          (value) => value !== slug,
                                        ),
                                        page: 1,
                                      })
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
                  {!busy && summary}
                </div>
              </header>
              <div className="release-content">
                {busy ? (
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
                    {outOfRange && (
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!canChange || repair}
                        onClick={() => navigate({ ...query.conditions, page: 1 })}
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
                    disabled={busy}
                    onClick={() => navigate()}
                  >
                    再取得
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!canChange || (!filtered && !repair)}
                    onClick={() => {
                      setDraft({ q: "", from: "", to: "", categories: "", page: "1" });
                      setLocalErrors([]);
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
          <SidebarForm className="release-search" onApply={submit} noValidate>
            <div className="release-search-field">
              <Label htmlFor="release-keyword">キーワード</Label>
              <Input
                id="release-keyword"
                type="search"
                value={draft.q}
                onChange={(event) => updateDraft("q", event.target.value)}
                placeholder="タイトル内のキーワード"
              />
            </div>
            <fieldset className="release-date-range">
              <legend>公開日</legend>
              <div className="release-date-inputs">
                {(["from", "to"] as const).map((key) => (
                  <div key={key} className="release-date-field">
                    <Label htmlFor={`release-date-${key}`}>
                      {key === "from" ? "開始日" : "終了日"}
                    </Label>
                    <Input
                      id={`release-date-${key}`}
                      type={query.errors.length ? "text" : "date"}
                      value={draft[key]}
                      onChange={(event) => updateDraft(key, event.target.value)}
                      aria-invalid={dateError || undefined}
                      aria-describedby={dateError ? "release-date-error" : undefined}
                    />
                  </div>
                ))}
              </div>
            </fieldset>
            {dateError && (
              <p id="release-date-error" role="alert">
                公開日の開始日・終了日を確認して修正してください。
              </p>
            )}
            {query.errors.length > 0 && (
              <>
                <Label htmlFor="release-repair-categories">カテゴリslug（1行に1個）</Label>
                <textarea
                  id="release-repair-categories"
                  value={draft.categories}
                  onChange={(event) => updateDraft("categories", event.target.value)}
                />
                <Label htmlFor="release-repair-page">ページ</Label>
                <Input
                  id="release-repair-page"
                  type="text"
                  inputMode="numeric"
                  value={draft.page}
                  onChange={(event) => updateDraft("page", event.target.value)}
                />
              </>
            )}
            {localErrors.length > 0 && (
              <div role="alert">
                {localErrors.map((error) => (
                  <p key={error}>{error}</p>
                ))}
              </div>
            )}
            {repair && (
              <Button type="submit" disabled={!canChange}>
                条件を修正して適用
              </Button>
            )}
            <Button type="button" className="release-search-button" disabled>
              検索
            </Button>
            <Button type="button" variant="outline" className="release-search-reset" disabled>
              リセット
            </Button>
            <p className="release-feature-notice">
              検索・リセット・カテゴリ選択は後続フェーズで実装します。
            </p>
          </SidebarForm>
          <div className="release-sidebar-categories">
            <fieldset className="release-category-field">
              <legend>カテゴリ</legend>
              {busy ? (
                <output>カテゴリを読み込んでいます</output>
              ) : options === null ? (
                <p role="alert">カテゴリ選択肢を取得できませんでした</p>
              ) : options.length === 0 ? (
                <p>カテゴリ選択肢が未登録です</p>
              ) : (
                <div className="release-category-toggles">
                  {options.map((option) => (
                    <Button
                      type="button"
                      key={option.slug}
                      variant="outline"
                      disabled
                      aria-pressed={query.conditions.categories.includes(option.slug)}
                      className="release-category-pill release-category-toggle"
                    >
                      {option.name}
                    </Button>
                  ))}
                </div>
              )}
            </fieldset>
          </div>
        </SidebarFilters>
      </section>
    </main>
  );
}
