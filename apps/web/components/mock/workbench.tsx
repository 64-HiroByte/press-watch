"use client";

import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { ChevronDownIcon, PencilLineIcon } from "lucide-react";

import { MockCategoryPills } from "@/components/mock/category-toggles";
import { MockDisplayTooltip } from "@/components/mock/display-tooltip";
import { MockSidebarFilters, type MockSearchConditions } from "@/components/mock/sidebar-filters";
import { MockThemeToggle } from "@/components/mock/theme-toggle";
import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

type PreviewState = "normal" | "loading" | "error" | "empty" | "no-results";
type WorkbenchProps = {
  sidebarSearch: ReactNode;
  sidebarCategories: readonly FixedCategoryLabel[];
  resultSummaries: Record<PreviewState, ReactNode>;
  results: Record<PreviewState, ReactNode>;
  robustness: ReactNode;
};

export function MockWorkbench({ sidebarSearch, sidebarCategories, resultSummaries, results, robustness }: WorkbenchProps) {
  const [state, setState] = useState<PreviewState>("normal");
  const [sidebarSelection, setSidebarSelection] = useState<string[]>([]);
  const [appliedSearch, setAppliedSearch] = useState<MockSearchConditions>({ keyword: "", publishedFrom: "", publishedTo: "" });
  const [conditionsExpanded, setConditionsExpanded] = useState(false);
  const [textSize, setTextSize] = useState<"standard" | "large">("standard");
  const mainRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setConditionsExpanded(!window.matchMedia("(width < 768px)").matches);
  }, []);

  useEffect(() => {
    const main = mainRef.current;
    const header = headerRef.current;
    if (!main || !header) return;
    const updateHeaderHeight = () => {
      main.style.setProperty("--mock-header-height", `${header.offsetHeight}px`);
    };
    updateHeaderHeight();
    const observer = new ResizeObserver(updateHeaderHeight);
    observer.observe(header, { box: "border-box" });
    return () => {
      observer.disconnect();
      main.style.removeProperty("--mock-header-height");
    };
  }, []);
  const selectedCategories = sidebarCategories.filter((category) => sidebarSelection.includes(category.slug));
  const publicationRange = appliedSearch.publishedFrom || appliedSearch.publishedTo
    ? `${appliedSearch.publishedFrom.replaceAll("-", "/") || "開始日指定なし"} 〜 ${appliedSearch.publishedTo.replaceAll("-", "/") || "終了日指定なし"}`
    : "指定なし";
  const hasConditions = Boolean(appliedSearch.keyword || appliedSearch.publishedFrom || appliedSearch.publishedTo || selectedCategories.length);
  const conditionAction = hasConditions ? "条件を変更" : "検索条件を設定";
  const conditionRows = (
    <>
      <span className="release-applied-row">
        <span className="release-applied-label">キーワード</span>
        <span className="release-applied-value">{appliedSearch.keyword || "指定なし"}</span>
      </span>
      <span className="release-applied-row">
        <span className="release-applied-label">公開日</span>
        <span className="release-applied-value">{publicationRange}</span>
      </span>
      <span className="release-applied-row">
        <span className="release-applied-label">カテゴリ</span>
        <span className="release-applied-values">
          {selectedCategories.length === 0 ? <span>すべてのカテゴリ</span> : selectedCategories.map((category) => (
            <Badge key={category.slug} variant="outline" className="release-category">{category.name}</Badge>
          ))}
        </span>
      </span>
    </>
  );

  function toggleSidebarCategory(slug: string) {
    setSidebarSelection((current) => current.includes(slug)
      ? current.filter((value) => value !== slug)
      : [...current, slug]);
  }

  function preventPreviewNavigation(event: MouseEvent<HTMLElement>) {
    // 表示部品のリンクは維持し、Mockの確認画面内でだけ遷移を抑止する。
    if (event.target instanceof Element && event.target.closest("a")) {
      event.preventDefault();
    }
  }

  return (
    <main className="mock-workbench">
      <aside className="mock-controls" aria-labelledby="mock-controls-title">
        <div className="mock-controls-heading">
          <div>
            <h1 id="mock-controls-title">一覧Mockの表示確認</h1>
            <p>内容は架空のサンプルです。検索・選択・リンクによって結果は変わりません。</p>
          </div>
        </div>
        <div className="mock-control-fields">
          <div className="mock-control-field">
            <Label htmlFor="mock-state">表示状態</Label>
            <NativeSelect id="mock-state" value={state} onChange={(event) => setState(event.target.value as PreviewState)}>
              <NativeSelectOption value="normal">通常一覧</NativeSelectOption>
              <NativeSelectOption value="loading">ローディング</NativeSelectOption>
              <NativeSelectOption value="error">取得失敗</NativeSelectOption>
              <NativeSelectOption value="empty">データなし</NativeSelectOption>
              <NativeSelectOption value="no-results">検索結果なし</NativeSelectOption>
            </NativeSelect>
          </div>
        </div>
        <p className="mock-design-description">
          検索ボタンでキーワード・公開日、カテゴリ選択でカテゴリの条件表示だけが更新されます。一覧・件数・ページ位置は固定です。
        </p>
      </aside>

      <section
        className="mock-preview" data-design="sidebar" data-text-size={textSize} aria-label="サイドバーの画面見本"
        onClick={preventPreviewNavigation} onAuxClick={preventPreviewNavigation}
      >
        <MockSidebarFilters onSearch={setAppliedSearch} renderMain={({ drawerOpen, openDrawer, triggerRef, rememberTriggerFocus }) => (
          <div ref={mainRef} className="release-main" role="region" aria-label="報道発表一覧のスクロール領域" tabIndex={0}>
            <header ref={headerRef} className="release-header">
              <div className="release-header-body">
                <div className="release-header-top">
                  <h2>報道発表一覧</h2>
                  <div className="release-display-controls">
                    <div className="release-text-options" role="group" aria-label="文字サイズ">
                      <div className="release-text-buttons">
                        {(["standard", "large"] as const).map((size) => (
                          <MockDisplayTooltip key={size} label={textSize === size
                            ? `${size === "standard" ? "標準" : "大きめ"}サイズ（選択中）`
                            : `${size === "standard" ? "標準" : "大きめ"}サイズに切り替え`}>
                            <Button
                              type="button" variant="ghost" size="icon"
                              aria-label={size === "standard" ? "文字サイズ：標準" : "文字サイズ：大きめ"}
                              aria-pressed={textSize === size} onClick={() => setTextSize(size)}
                            ><span className="release-text-symbol" data-size={size} aria-hidden="true">あ</span></Button>
                          </MockDisplayTooltip>
                        ))}
                      </div>
                    </div>
                    <MockThemeToggle />
                  </div>
                </div>
                <div className="release-condition-controls">
                  <span id="mock-condition-status" className="release-condition-status" aria-live="polite" aria-atomic="true">
                    {hasConditions ? "検索条件あり" : "絞り込みなし"}
                  </span>
                  <Button
                    type="button" variant="ghost" className="release-conditions-disclosure"
                    aria-expanded={conditionsExpanded} aria-controls="mock-applied-values"
                    onClick={() => setConditionsExpanded((current) => !current)}
                  >
                    条件の詳細<ChevronDownIcon aria-hidden="true" />
                  </Button>
                  <Button
                    ref={triggerRef} type="button" variant="ghost" className="release-conditions-trigger"
                    aria-describedby="mock-condition-status"
                    aria-haspopup="dialog" aria-controls="mock-filter-panel" aria-expanded={drawerOpen}
                    onClick={openDrawer} onFocus={rememberTriggerFocus}
                  >
                    <PencilLineIcon aria-hidden="true" />{conditionAction}
                  </Button>
                </div>
                <div
                  id="mock-applied-values" className="release-applied-conditions" hidden={!conditionsExpanded}
                  role="group" aria-label="適用中の検索条件" aria-live="polite" aria-atomic="true"
                >
                  {conditionRows}
                </div>
                {resultSummaries[state]}
              </div>
            </header>
            <div className="release-content">
              {results[state]}
              {robustness}
            </div>
          </div>
        )}>
          {sidebarSearch}
          <div className="release-sidebar-categories">
            <MockCategoryPills
              categories={sidebarCategories} selectedSlugs={sidebarSelection}
              onSelectAll={() => setSidebarSelection(sidebarCategories.map((category) => category.slug))}
              onToggle={toggleSidebarCategory} onClear={() => setSidebarSelection([])}
            />
          </div>
        </MockSidebarFilters>
      </section>
    </main>
  );
}
