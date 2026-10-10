import { ListResults, ListSummary } from "@/components/press-releases/results";
import { ListWorkbench } from "@/components/press-releases/workbench";
import { parseQuery, type SearchValues } from "@/lib/press-release-query";
import { getList } from "@/lib/press-releases-api";
import "@/components/press-releases/styles.css";

export const dynamic = "force-dynamic";

export default async function Home({ searchParams }: { searchParams: Promise<SearchValues> }) {
  const query = parseQuery(await searchParams);
  const normalizing = !query.errors.length && query.original !== query.canonical;
  const { list, categories } = normalizing
    ? { list: null, categories: null }
    : await getList(query.canonical, query.errors.length > 0);
  return (
    <ListWorkbench
      query={query}
      options={categories?.ok ? categories.data.items : null}
      dateError={list !== null && !list.ok && list.dateError}
      outOfRange={
        !!list?.ok &&
        list.data.pagination.total_items > 0 &&
        list.data.pagination.page > list.data.pagination.total_pages
      }
      summary={<ListSummary list={list} />}
    >
      <ListResults list={list} conditions={query.conditions} />
    </ListWorkbench>
  );
}
