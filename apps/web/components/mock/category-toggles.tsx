"use client";

import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { Button } from "@/components/ui/button";

type CategoryPillsProps = {
  categories: readonly FixedCategoryLabel[];
  selectedSlugs: readonly string[];
  onToggle: (slug: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
};

export function MockCategoryPills({ categories, selectedSlugs, onToggle, onSelectAll, onClear }: CategoryPillsProps) {
  return (
    <fieldset className="release-category-field" aria-labelledby="mock-category-label">
      <legend>
        <span id="mock-category-label">カテゴリ</span>
        <span className="release-category-actions" role="group" aria-label="カテゴリの一括操作">
          <Button type="button" variant="outline" className="release-category-action" aria-label="カテゴリを全選択" onClick={onSelectAll}>全選択</Button>
          <Button type="button" variant="outline" className="release-category-action" aria-label="カテゴリを全解除" onClick={onClear}>全解除</Button>
        </span>
      </legend>
      <div className="release-category-toggles">
        {categories.map((category) => (
          <Button
            key={category.slug} type="button" variant="outline" className="release-category-toggle"
            aria-pressed={selectedSlugs.includes(category.slug)} onClick={() => onToggle(category.slug)}
          >
            {category.name}
          </Button>
        ))}
      </div>
    </fieldset>
  );
}
