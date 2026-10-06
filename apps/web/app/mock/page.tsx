import { notFound } from "next/navigation";
import { SearchIcon } from "lucide-react";

import { MockWorkbench } from "@/components/mock/workbench";
import { MockCategoryToggles } from "@/components/mock/category-toggles";
import { PressReleaseList } from "@/components/press-releases/list";
import { PressReleaseStatus, type ReleaseDisplayState } from "@/components/press-releases/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
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
        <Input id="release-keyword" type="search" placeholder="タイトルに含まれるキーワード" />
      </div>
      <Button type="button" className="release-search-button"><SearchIcon aria-hidden="true" />検索</Button>
    </div>
  );
}

function CategorySelect() {
  return (
    <div className="release-category-field release-category-select">
      <Label htmlFor="release-category">カテゴリ</Label>
      <NativeSelect id="release-category" defaultValue="">
        <NativeSelectOption value="">すべてのカテゴリ</NativeSelectOption>
        {mockCategories.map((category) => (
          <NativeSelectOption value={category.slug} key={category.slug}>{category.name}</NativeSelectOption>
        ))}
      </NativeSelect>
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

function Results({ state = "normal" }: { state?: "normal" | ReleaseDisplayState }) {
  const isEmpty = state === "empty" || state === "no-results";

  return (
    <section className="release-results" aria-label="報道発表の表示">
      <header className="release-results-heading">
        <h3>報道発表</h3>
        {state === "normal" && <p><strong>128</strong> 件中 1–{mockReleases.length}件<span>公開日の新しい順</span></p>}
        {isEmpty && <p><strong>0</strong> 件</p>}
      </header>
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
      header={
        <header className="release-header">
          <p className="release-brand">PressWatch<span>環境省の報道発表</span></p>
          <h2>報道発表一覧</h2>
          <p className="release-introduction">日々の発表から、必要な情報を見つける。</p>
        </header>
      }
      search={<SearchFields />}
      categories={{ toggles: <MockCategoryToggles categories={mockCategories} />, select: <CategorySelect /> }}
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
