import { notFound } from "next/navigation";
import { InboxIcon, SearchIcon } from "lucide-react";

import { MockRetrievalFailureDecoration } from "@/components/mock/retrieval-failure-decoration";
import { MockWorkbench } from "@/components/mock/workbench";
import { PressReleaseList } from "@/components/press-releases/list";
import { PressReleaseStatus, type ReleaseDisplayState } from "@/components/press-releases/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Pagination, PaginationContent, PaginationEllipsis, PaginationItem,
  PaginationLink, PaginationNext, PaginationPrevious,
} from "@/components/ui/pagination";
import { longCategorySample, mockCategories, mockReleases } from "@/mock/press-releases";

import "./mock.css";

function SearchFields() {
  return (
    <div className="release-search" role="search" aria-label="報道発表の検索">
      <div className="release-search-field">
        <Label htmlFor="release-keyword">キーワード</Label>
        <Input id="release-keyword" type="search" placeholder="タイトル内のキーワード" />
      </div>
      <fieldset className="release-date-range">
        <legend>公開日</legend>
        <div className="release-date-inputs">
          <div className="release-date-field">
            <Label htmlFor="release-date-from">開始日</Label>
            <Input id="release-date-from" type="date" />
          </div>
          <div className="release-date-field">
            <Label htmlFor="release-date-to">終了日</Label>
            <Input id="release-date-to" type="date" />
          </div>
        </div>
      </fieldset>
      <Button type="button" className="release-search-button"><SearchIcon aria-hidden="true" />検索</Button>
      <Button type="button" variant="outline" className="release-search-reset">リセット</Button>
    </div>
  );
}

function SamplePagination() {
  return (
    <footer className="release-pagination">
      <span className="release-page-description">1 / 16ページ</span>
      <Pagination>
        <PaginationContent>
          <PaginationItem><PaginationPrevious href="#" aria-disabled="true" tabIndex={-1} /></PaginationItem>
          <PaginationItem><PaginationLink href="#" aria-label="1ページ目" isActive>1</PaginationLink></PaginationItem>
          <PaginationItem><PaginationLink href="#" aria-label="2ページ目">2</PaginationLink></PaginationItem>
          <PaginationItem><PaginationLink href="#" aria-label="3ページ目">3</PaginationLink></PaginationItem>
          <PaginationItem><PaginationEllipsis /></PaginationItem>
          <PaginationItem><PaginationLink href="#" aria-label="16ページ目">16</PaginationLink></PaginationItem>
          <PaginationItem><PaginationNext href="#" /></PaginationItem>
        </PaginationContent>
      </Pagination>
    </footer>
  );
}

function ResultSummary({ state = "normal" }: { state?: "normal" | ReleaseDisplayState }) {
  if (state === "loading" || state === "error") {
    return null;
  }

  return (
    <div className="release-results-summary">
      {state === "normal" ? (
        <>
          <p><strong>128</strong> 件中 1–{mockReleases.length}件</p>
          <span>公開日の新しい順</span>
        </>
      ) : <p><strong>0</strong> 件</p>}
    </div>
  );
}

function Results({ state = "normal" }: { state?: "normal" | ReleaseDisplayState }) {
  const DecorationIcon = state === "error" ? MockRetrievalFailureDecoration
    : state === "empty" ? InboxIcon
    : state === "no-results" ? SearchIcon : null;

  return (
    <section className="release-results" data-state={state} data-decorated={DecorationIcon ? true : undefined} aria-label="報道発表の表示">
      {DecorationIcon && <DecorationIcon
        className="release-results-decoration"
        viewBox={state === "empty" ? "-1.5 -1.5 27 27" : "0 0 24 24"}
        strokeWidth={state === "empty" ? 1.125 : 1}
        aria-hidden="true"
        focusable="false"
      />}
      {state === "normal" ? <PressReleaseList releases={mockReleases} /> : <PressReleaseStatus state={state} />}
      {state === "normal" && <SamplePagination />}
    </section>
  );
}

export default function MockPage() {
  if (process.env.NODE_ENV !== "development") {
    notFound();
  }

  return (
    <MockWorkbench
      sidebarSearch={<SearchFields />}
      sidebarCategories={mockCategories}
      resultSummaries={{
        normal: <ResultSummary />, loading: <ResultSummary state="loading" />, error: <ResultSummary state="error" />,
        empty: <ResultSummary state="empty" />, "no-results": <ResultSummary state="no-results" />,
      }}
      results={{
        normal: <Results />, loading: <Results state="loading" />, error: <Results state="error" />,
        empty: <Results state="empty" />, "no-results": <Results state="no-results" />,
      }}
      robustness={
        <details className="mock-robustness">
          <summary>長いカテゴリ名のレイアウト確認</summary>
          <p>実カテゴリに含まれない検証用の名前です。通常一覧と同じ幅・部品で確認します。</p>
          <PressReleaseList releases={longCategorySample} />
        </details>
      }
    />
  );
}
