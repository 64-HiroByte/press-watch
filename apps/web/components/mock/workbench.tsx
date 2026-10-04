"use client";

import { useState, type MouseEvent, type ReactNode } from "react";

import { ThemeSelector } from "@/components/theme-selector";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

type PreviewState = "normal" | "loading" | "error" | "empty" | "no-results";
type CategoryLayout = "checkboxes" | "select";

const designs = [
  { id: "standard", label: "A · 標準", description: "日付を左に揃えた、一覧性と読みやすさのバランス。" },
  { id: "spacious", label: "B · 余白", description: "余白と見出しに強弱をつけた、ゆったり読む配置。" },
  { id: "compact", label: "C · コンパクト", description: "カテゴリを右にまとめた、一画面の情報量を重視する配置。" },
] as const;

type WorkbenchProps = {
  header: ReactNode;
  search: ReactNode;
  categories: Record<CategoryLayout, ReactNode>;
  results: Record<PreviewState, ReactNode>;
  robustness: ReactNode;
};

export function MockWorkbench({ header, search, categories, results, robustness }: WorkbenchProps) {
  const [design, setDesign] = useState<(typeof designs)[number]>(designs[0]);
  const [state, setState] = useState<PreviewState>("normal");
  const [categoryLayout, setCategoryLayout] = useState<CategoryLayout>("checkboxes");

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
            <NativeSelect id="mock-category-layout" value={categoryLayout} onChange={(event) => setCategoryLayout(event.target.value as CategoryLayout)}>
              <NativeSelectOption value="checkboxes">チェックボックス案</NativeSelectOption>
              <NativeSelectOption value="select">コンパクトな選択欄案</NativeSelectOption>
            </NativeSelect>
          </div>
        </div>
        <p className="mock-design-description" aria-live="polite">{design.description}</p>
      </aside>

      <section
        className="mock-preview" data-design={design.id} aria-label={`${design.label}の画面見本`}
        onClick={preventPreviewNavigation} onAuxClick={preventPreviewNavigation}
      >
        {header}
        <section className="release-filters" aria-label="検索とカテゴリ">
          {search}
          {categories[categoryLayout]}
        </section>
        {results[state]}
        {robustness}
      </section>
    </main>
  );
}
