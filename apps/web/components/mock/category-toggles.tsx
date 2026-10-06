"use client";

import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { Button } from "@/components/ui/button";

type CategoryPillsProps = {
  categories: readonly FixedCategoryLabel[];
  selectedSlugs: readonly string[];
  onToggle: (slug: string) => void;
};

export function MockCategoryPills({ categories, selectedSlugs, onToggle }: CategoryPillsProps) {
  return (
    <fieldset className="release-category-field">
      <legend>カテゴリ</legend>
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
