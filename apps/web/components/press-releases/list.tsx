import { ArrowUpRightIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export type FixedCategoryLabel = {
  slug: string;
  name: string;
};

export type ReleaseSummary = {
  id: string;
  title: string;
  publishedOn: string;
  detailUrl: string;
  categories: readonly FixedCategoryLabel[];
};

export function PressReleaseList({ releases }: { releases: readonly ReleaseSummary[] }) {
  return (
    <ul className="release-list" aria-label="報道発表一覧">
      {releases.map((release) => (
        <li className="release-row" key={release.id}>
          <time className="release-date" dateTime={release.publishedOn}>
            {release.publishedOn.replaceAll("-", ".")}
          </time>
          <a className="release-title" href={release.detailUrl}>
            <span>{release.title}</span>
            <ArrowUpRightIcon className="release-link-icon" aria-hidden="true" />
          </a>
          <div className="release-categories" aria-label="固定カテゴリ">
            {release.categories.length > 0 ? (
              release.categories.map((category) => (
                <Badge variant="outline" className="release-category" key={category.slug}>
                  {category.name}
                </Badge>
              ))
            ) : (
              <span className="release-uncategorized">カテゴリなし</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
