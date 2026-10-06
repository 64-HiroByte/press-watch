"use client";

import { useState, type MouseEvent, type ReactNode } from "react";

import { ThemeSelector } from "@/components/theme-selector";
import { MockCategoryPills } from "@/components/mock/category-toggles";
import { MockSidebarFilters } from "@/components/mock/sidebar-filters";
import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

type PreviewState = "normal" | "loading" | "error" | "empty" | "no-results";
type CategoryLayout = "toggles" | "select";

const designs = [
  { id: "standard", label: "A · 標準", description: "日付を左に揃えた、一覧性と読みやすさのバランス。" },
  { id: "spacious", label: "B · 余白", description: "余白と見出しに強弱をつけた、ゆったり読む配置。" },
  { id: "compact", label: "C · コンパクト", description: "カテゴリを右にまとめた、一画面の情報量を重視する配置。" },
  { id: "sidebar", label: "D · サイドバー", description: "左に検索条件、右に報道発表を配置し、ヘッダーに適用中カテゴリを表示。" },
] as const;

type WorkbenchProps = {
  header: ReactNode;
  search: ReactNode;
  sidebarSearch: ReactNode;
  categories: Record<CategoryLayout, ReactNode>;
  sidebarCategories: readonly FixedCategoryLabel[];
  results: Record<PreviewState, ReactNode>;
  robustness: ReactNode;
};

export function MockWorkbench({ header, search, sidebarSearch, categories, sidebarCategories, results, robustness }: WorkbenchProps) {
  const [design, setDesign] = useState<(typeof designs)[number]>(designs[3]);
  const [state, setState] = useState<PreviewState>("normal");
  const [categoryLayout, setCategoryLayout] = useState<CategoryLayout>("toggles");
  const [sidebarSelection, setSidebarSelection] = useState<string[]>([]);
  const isSidebar = design.id === "sidebar";
  const selectedCategories = sidebarCategories.filter((category) => sidebarSelection.includes(category.slug));

  function toggleSidebarCategory(slug: string) {
    setSidebarSelection((current) => current.includes(slug)
      ? current.filter((value) => value !== slug)
      : [...current, slug]);
  }

  function preventPreviewNavigation(event: MouseEvent<HTMLElement>) {
    // 表示部品のリンクは維持し、Mockの比較画面内でだけ遷移を抑止する。
    if (event.target instanceof Element && event.target.closest("a")) {
      event.preventDefault();
    }
  }

  return (
    <main className="mock-workbench">
      <aside className="mock-controls" aria-labelledby="mock-controls-title">
        <div className="mock-controls-heading">
          <div>
            <h1 id="mock-controls-title">一覧Mockのデザイン比較</h1>
            <p>内容は架空のサンプルです。検索・選択・リンクによって結果は変わりません。</p>
          </div>
          <ThemeSelector />
        </div>
        <div className="mock-control-fields">
          <div className="mock-design-field">
            <span id="mock-design-label" className="mock-control-label">デザイン</span>
            <div className="mock-design-options" role="group" aria-labelledby="mock-design-label">
              {designs.map((option) => (
                <Button
                  key={option.id} type="button" variant={design.id === option.id ? "default" : "outline"}
                  aria-pressed={design.id === option.id} onClick={() => setDesign(option)}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </div>
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
          <div className="mock-control-field">
            <Label htmlFor="mock-category-layout">カテゴリ欄</Label>
            <NativeSelect
              id="mock-category-layout" value={categoryLayout} disabled={isSidebar}
              aria-describedby={isSidebar ? "mock-sidebar-note" : undefined}
              onChange={(event) => setCategoryLayout(event.target.value as CategoryLayout)}
            >
              <NativeSelectOption value="toggles">ピルボタン案</NativeSelectOption>
              <NativeSelectOption value="select">コンパクトな選択欄案</NativeSelectOption>
            </NativeSelect>
          </div>
        </div>
        <p className="mock-design-description" aria-live="polite">{design.description}</p>
        {isSidebar && (
          <p id="mock-sidebar-note" className="mock-design-description">
            D案は採用済みのピル型ボタンを使います。適用中カテゴリは選択に連動する表示見本で、一覧・件数・ページ位置は固定です。
          </p>
        )}
      </aside>

      <section
        className="mock-preview" data-design={design.id} aria-label={`${design.label}の画面見本`}
        onClick={preventPreviewNavigation} onAuxClick={preventPreviewNavigation}
      >
        <div hidden={isSidebar}>{header}</div>
        <aside hidden={isSidebar} className="release-filters" aria-label="検索とカテゴリ">
          {!isSidebar && search}
          {categories[categoryLayout]}
        </aside>
        {isSidebar && (
          <MockSidebarFilters>
            {sidebarSearch}
            <div className="release-sidebar-categories">
              <MockCategoryPills categories={sidebarCategories} selectedSlugs={sidebarSelection} onToggle={toggleSidebarCategory} />
            </div>
          </MockSidebarFilters>
        )}
        <div className="release-main">
          {isSidebar && (
            <header className="release-header">
              <h2>報道発表一覧</h2>
              <div className="release-applied-categories" role="group" aria-label="適用中カテゴリ">
                <span className="release-applied-label">適用中カテゴリ</span>
                <div className="release-applied-values" aria-live="polite" aria-atomic="true">
                  {selectedCategories.length === 0 ? <span>すべてのカテゴリ</span> : selectedCategories.map((category) => (
                    <Badge key={category.slug} variant="outline" className="release-category">{category.name}</Badge>
                  ))}
                </div>
              </div>
            </header>
          )}
          {results[state]}
          {robustness}
        </div>
      </section>
    </main>
  );
}
