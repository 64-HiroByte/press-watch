import { PressReleaseList } from "@/components/press-releases/list";
import { ResultState } from "@/components/press-releases/result-state";
import type { ApiResult, ListData } from "@/lib/press-releases-api";
import type { Conditions } from "@/lib/press-release-query";

export function ListSummary({ list }: { list: ApiResult<ListData> | null }) {
  if (!list?.ok) return null;
  const { items, pagination } = list.data;
  return (
    <div className="release-results-summary">
      <p>
        <strong>{pagination.total_items}</strong> 件
        {items.length > 0 &&
          `中 ${(pagination.page - 1) * 50 + 1}–${(pagination.page - 1) * 50 + items.length}件`}
      </p>
      <span>公開日の新しい順</span>
    </div>
  );
}

export function ListResults({
  list,
  conditions,
}: {
  list: ApiResult<ListData> | null;
  conditions: Conditions;
}) {
  if (!list) return null;
  if (!list.ok) return <ResultState state="error" />;
  const { items, pagination } = list.data;
  const filtered = !!(
    conditions.q ||
    conditions.from ||
    conditions.to ||
    conditions.categories.length
  );
  if (pagination.total_items === 0)
    return <ResultState state={filtered ? "no-results" : "empty"} />;
  return (
    <>
      <section className="release-results" aria-label="報道発表の表示">
        {pagination.page > pagination.total_pages ? (
          <output>指定したページは範囲外です</output>
        ) : items.length === 0 ? (
          <output>表示件数と一覧が一致しません。再取得してください</output>
        ) : (
          <PressReleaseList
            releases={items.map((item) => ({
              id: item.source_url,
              title: item.title,
              detailUrl: item.source_url,
              publishedOn: item.published_at,
              categories: item.fixed_categories,
            }))}
          />
        )}
        <footer className="release-pagination">
          <span className="release-page-description">
            {pagination.page} / {pagination.total_pages}ページ
          </span>
          <span>ページ送りは後続フェーズで実装します。</span>
        </footer>
      </section>
    </>
  );
}
