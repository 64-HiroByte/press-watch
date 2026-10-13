"use client";

import { Button } from "@/components/ui/button";
import type { CategoryOption } from "@/lib/press-releases-api";
import { MAX_FIXED_CATEGORY_COUNT } from "@/lib/press-release-values";

type Props = {
  options: CategoryOption[] | null;
  selected: string[];
  busy: boolean;
  canChange: boolean;
  onToggle: (slug: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
};

export function CategoryFilters({
  options,
  selected,
  busy,
  canChange,
  onToggle,
  onSelectAll,
  onClear,
}: Props) {
  const atLimit = selected.length >= MAX_FIXED_CATEGORY_COUNT;
  const allExceedsLimit =
    new Set([...selected, ...(options?.map((option) => option.slug) ?? [])]).size >
    MAX_FIXED_CATEGORY_COUNT;
  // 取得中はaria-disabledと操作ガードで停止し、操作元のDOMとフォーカスを維持する。
  return (
    <div className="release-sidebar-categories">
      <fieldset className="release-category-field" aria-labelledby="release-category-label">
        <legend>
          <span id="release-category-label">カテゴリ</span>
          <span className="release-category-actions">
            <Button
              type="button"
              variant="outline"
              className="release-category-action"
              aria-label="カテゴリを全選択"
              disabled={(!canChange && !busy) || allExceedsLimit}
              aria-disabled={!canChange || busy || allExceedsLimit}
              aria-describedby={
                allExceedsLimit
                  ? "release-category-select-help release-category-all-limit"
                  : "release-category-select-help"
              }
              onClick={() => {
                if (canChange && !busy && !allExceedsLimit) onSelectAll();
              }}
            >
              全選択
            </Button>
            <Button
              type="button"
              variant="outline"
              className="release-category-action"
              aria-label="カテゴリを全解除"
              aria-describedby="release-category-clear-help"
              disabled={!canChange && !busy}
              aria-disabled={!canChange || busy}
              onClick={() => {
                if (canChange && !busy) onClear();
              }}
            >
              全解除
            </Button>
          </span>
        </legend>
        <p id="release-category-select-help" className="release-category-help">
          分類済みの全カテゴリを対象
        </p>
        <p id="release-category-clear-help" className="release-category-help">
          未分類も含めて表示
        </p>
        {atLimit && (
          <p id="release-category-limit" className="release-category-help">
            カテゴリは{MAX_FIXED_CATEGORY_COUNT}個まで選択できます。解除してから追加してください。
          </p>
        )}
        {allExceedsLimit && (
          <p id="release-category-all-limit" className="release-category-help">
            全選択は{MAX_FIXED_CATEGORY_COUNT}個を超えるため利用できません。個別に選択してください。
          </p>
        )}
        {busy && <output>カテゴリを読み込んでいます</output>}
        {!busy && options === null && <p role="alert">カテゴリ選択肢を取得できませんでした</p>}
        {!busy && options?.length === 0 && <p>カテゴリ選択肢が未登録です</p>}
        {options && options.length > 0 && (
          <div className="release-category-toggles">
            {options.map((option) => {
              const pressed = selected.includes(option.slug);
              const cannotAdd = atLimit && !pressed;
              return (
                <Button
                  type="button"
                  key={option.slug}
                  variant="outline"
                  disabled={(!canChange && !busy) || cannotAdd}
                  aria-disabled={!canChange || busy || cannotAdd}
                  aria-describedby={cannotAdd ? "release-category-limit" : undefined}
                  aria-pressed={pressed}
                  className="release-category-pill release-category-toggle"
                  onClick={() => {
                    if (canChange && !busy && !cannotAdd) onToggle(option.slug);
                  }}
                >
                  {option.name}
                </Button>
              );
            })}
          </div>
        )}
      </fieldset>
    </div>
  );
}
