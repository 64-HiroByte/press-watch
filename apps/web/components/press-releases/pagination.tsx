import type { MouseEvent } from "react";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { queryString, type Conditions } from "@/lib/press-release-query";
import type { ListData } from "@/lib/press-releases-api";
import { MAX_LIST_PAGE } from "@/lib/press-release-values";

function pageNumbers(page: number, last: number): (number | string)[] {
  if (last <= 5) return Array.from({ length: last }, (_, index) => index + 1);
  const center = Math.min(Math.max(page, 2), last - 1);
  const numbers = [...new Set([1, center - 1, center, center + 1, last])].sort((a, b) => a - b);
  const entries: (number | string)[] = [];
  for (const [index, number] of numbers.entries()) {
    const previous = numbers[index - 1];
    if (previous !== undefined) {
      if (number - previous === 2) entries.push(previous + 1);
      else if (number - previous > 2) entries.push(`gap-${previous}`);
    }
    entries.push(number);
  }
  return entries;
}

export function ListPagination({
  pagination,
  conditions,
  disabled,
  onPageChange,
}: {
  pagination: ListData["pagination"] | null;
  conditions: Conditions;
  disabled: boolean;
  onPageChange: (page: number) => void;
}) {
  if (!pagination || pagination.total_items === 0) return null;
  const { page, total_pages: total } = pagination;
  const last = Math.min(total, MAX_LIST_PAGE);
  function destination(number: number) {
    const unavailable = disabled || number < 1 || number > last;
    const query = queryString({ ...conditions, page: number });
    return {
      href: unavailable ? undefined : query ? `/?${query}` : "/",
      "aria-disabled": unavailable ? (true as const) : undefined,
      tabIndex: unavailable ? -1 : undefined,
      onClick(event: MouseEvent<HTMLAnchorElement>) {
        if (unavailable) {
          event.preventDefault();
          return;
        }
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
          return;
        event.preventDefault();
        if (number !== page) onPageChange(number);
      },
    };
  }
  return (
    <footer className="release-pagination">
      <span className="release-page-description">
        {page} / {total}ページ
      </span>
      {page <= total && (
        <Pagination>
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious {...destination(page - 1)} />
            </PaginationItem>
            {pageNumbers(page, last).map((number) => (
              <PaginationItem key={number}>
                {typeof number === "number" ? (
                  <PaginationLink
                    {...destination(number)}
                    aria-label={`${number}ページ目`}
                    isActive={number === page}
                  >
                    {number}
                  </PaginationLink>
                ) : (
                  <PaginationEllipsis />
                )}
              </PaginationItem>
            ))}
            <PaginationItem>
              <PaginationNext {...destination(page + 1)} />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
      {total > MAX_LIST_PAGE && (
        <span className="release-page-description">
          移動できるのは{MAX_LIST_PAGE}ページ目までです
        </span>
      )}
    </footer>
  );
}
