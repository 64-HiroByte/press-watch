"use client";

import { useState, type MouseEvent, type ReactNode } from "react";

import { MockCategoryPills } from "@/components/mock/category-toggles";
import { MockSidebarFilters } from "@/components/mock/sidebar-filters";
import { MockThemeToggle } from "@/components/mock/theme-toggle";
import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

type PreviewState = "normal" | "loading" | "error" | "empty" | "no-results";
type WorkbenchProps = {
  sidebarSearch: ReactNode;
  sidebarCategories: readonly FixedCategoryLabel[];
  results: Record<PreviewState, ReactNode>;
  robustness: ReactNode;
};

export function MockWorkbench({ sidebarSearch, sidebarCategories, results, robustness }: WorkbenchProps) {
  const [state, setState] = useState<PreviewState>("normal");
  const [sidebarSelection, setSidebarSelection] = useState<string[]>([]);
  const selectedCategories = sidebarCategories.filter((category) => sidebarSelection.includes(category.slug));

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
          サイドバーとピル型ボタンを採用しています。適用中カテゴリは選択に連動する表示見本で、一覧・件数・ページ位置は固定です。
        </p>
      </aside>

      <section
        className="mock-preview" data-design="sidebar" aria-label="サイドバーの画面見本"
        onClick={preventPreviewNavigation} onAuxClick={preventPreviewNavigation}
      >
        <MockSidebarFilters>
          {sidebarSearch}
          <div className="release-sidebar-categories">
            <MockCategoryPills categories={sidebarCategories} selectedSlugs={sidebarSelection} onToggle={toggleSidebarCategory} />
          </div>
        </MockSidebarFilters>
        <div className="release-main">
          <header className="release-header">
            <div className="release-header-top">
              <h2>報道発表一覧</h2>
              <MockThemeToggle />
            </div>
            <div className="release-applied-categories" role="group" aria-label="適用中カテゴリ">
              <span className="release-applied-label">適用中カテゴリ</span>
              <div className="release-applied-values" aria-live="polite" aria-atomic="true">
                {selectedCategories.length === 0 ? <span>すべてのカテゴリ</span> : selectedCategories.map((category) => (
                  <Badge key={category.slug} variant="outline" className="release-category">{category.name}</Badge>
                ))}
              </div>
            </div>
          </header>
          {results[state]}
          {robustness}
        </div>
      </section>
    </main>
  );
}
