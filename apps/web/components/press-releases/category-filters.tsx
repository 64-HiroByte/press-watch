"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { DisplayTooltip } from "@/components/press-releases/display-tooltip";
import type { CategoryOption } from "@/lib/press-releases-api";
import { MAX_FIXED_CATEGORY_COUNT } from "@/lib/press-release-values";

const selectHelp = "分類済みの全カテゴリを対象";
const clearHelp = "未分類も含めて表示";

type Props = {
  options: CategoryOption[] | null;
  selected: string[];
  isBusy: boolean;
  canChange: boolean;
  onToggle: (slug: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
};

export function CategoryFilters({
  options,
  selected,
  isBusy,
  canChange,
  onToggle,
  onSelectAll,
  onClear,
}: Props) {
  const tooltipContainerRef = useRef<HTMLDivElement>(null);
  const atLimit = selected.length >= MAX_FIXED_CATEGORY_COUNT;
  const allExceedsLimit =
    new Set([...selected, ...(options?.map((option) => option.slug) ?? [])]).size >
    MAX_FIXED_CATEGORY_COUNT;
  const operationBlocked = !canChange || isBusy;
  const nativeDisabled = !canChange && !isBusy;
  const allSelected =
    !!options?.length && options.every((option) => selected.includes(option.slug));
  const canSelectAll = !allExceedsLimit && !allSelected;
  const hasSelection = selected.length > 0;
  // 一括操作はaria-disabledとガードで停止し、フォーカスとEscの標準動作を維持する。
  return (
    <div ref={tooltipContainerRef} className="release-sidebar-categories">
      <fieldset className="release-category-field" aria-labelledby="release-category-label">
        <legend>
          <span id="release-category-label">カテゴリ</span>
          <span className="release-category-actions">
            <DisplayTooltip label={selectHelp} container={tooltipContainerRef}>
              <Button
                type="button"
                variant="outline"
                className="release-category-action"
                aria-label="カテゴリを全選択"
                disabled={nativeDisabled}
                aria-disabled={operationBlocked || !canSelectAll}
                aria-describedby={
                  allExceedsLimit
                    ? "release-category-select-help release-category-all-limit"
                    : "release-category-select-help"
                }
                onClick={() => {
                  if (!operationBlocked && canSelectAll) onSelectAll();
                }}
              >
                全選択
              </Button>
            </DisplayTooltip>
            <DisplayTooltip label={clearHelp} container={tooltipContainerRef}>
              <Button
                type="button"
                variant="outline"
                className="release-category-action"
                aria-label="カテゴリを全解除"
                aria-describedby="release-category-clear-help"
                disabled={nativeDisabled}
                aria-disabled={operationBlocked || !hasSelection}
                onClick={() => {
                  if (!operationBlocked && hasSelection) onClear();
                }}
              >
                全解除
              </Button>
            </DisplayTooltip>
          </span>
        </legend>
        <p id="release-category-select-help" hidden>
          {selectHelp}
        </p>
        <p id="release-category-clear-help" hidden>
          {clearHelp}
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
        {isBusy && <output>カテゴリを読み込んでいます</output>}
        {!isBusy && options === null && <p role="alert">カテゴリ選択肢を取得できませんでした</p>}
        {!isBusy && options?.length === 0 && <p>カテゴリ選択肢が未登録です</p>}
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
                  disabled={nativeDisabled || cannotAdd}
                  aria-disabled={operationBlocked || cannotAdd}
                  aria-describedby={cannotAdd ? "release-category-limit" : undefined}
                  aria-pressed={pressed}
                  className="release-category-pill release-category-toggle"
                  onClick={() => {
                    if (!operationBlocked && !cannotAdd) onToggle(option.slug);
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
