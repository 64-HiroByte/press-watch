"use client";

import { useState } from "react";

import type { FixedCategoryLabel } from "@/components/press-releases/list";
import { Button } from "@/components/ui/button";

export function MockCategoryToggles({ categories }: { categories: readonly FixedCategoryLabel[] }) {
  const [selected, setSelected] = useState<string[]>([]);

  function toggleCategory(slug: string) {
    setSelected((current) => current.includes(slug)
      ? current.filter((value) => value !== slug)
      : [...current, slug]);
  }

  return (
    <fieldset className="release-category-field">
      <legend>カテゴリ</legend>
      <div className="release-category-toggles">
        {categories.map((category) => (
          <Button
            key={category.slug} type="button" variant="outline" className="release-category-toggle"
            aria-pressed={selected.includes(category.slug)} onClick={() => toggleCategory(category.slug)}
          >
            {category.name}
          </Button>
        ))}
      </div>
    </fieldset>
  );
}
