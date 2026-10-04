import { notFound } from "next/navigation";

import { ThemeSelector } from "@/components/theme-selector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";

export default function UIFoundationPage() {
  if (process.env.NODE_ENV !== "development") {
    notFound();
  }

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <header className="space-y-4">
        <p className="text-sm font-medium text-muted-foreground">PressWatch</p>
        <h1 className="text-2xl font-bold">UI基盤の確認</h1>
        <p className="text-sm leading-relaxed text-muted-foreground">
          基本部品とテーマの表示・操作を確認する開発用の見本です。
          検索・絞り込み・ページ移動の処理はありません。
        </p>
        <ThemeSelector />
      </header>

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="buttons-title" className="space-y-4 rounded-xl border p-5">
          <h2 id="buttons-title" className="font-semibold">ボタン</h2>
          <div className="flex flex-wrap gap-3">
            <Button type="button">基本</Button>
            <Button type="button" variant="outline">枠線</Button>
            <Button type="button" variant="secondary">補助</Button>
            <Button type="button" disabled>無効</Button>
          </div>
        </section>

        <section aria-labelledby="inputs-title" className="space-y-4 rounded-xl border p-5">
          <h2 id="inputs-title" className="font-semibold">入力・ラベル</h2>
          <div className="space-y-2">
            <Label htmlFor="sample-input">入力見本</Label>
            <Input id="sample-input" placeholder="日本語の入力を確認" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="disabled-input">無効な入力見本</Label>
            <Input id="disabled-input" defaultValue="操作できません" disabled />
          </div>
        </section>

        <section aria-labelledby="badges-title" className="space-y-4 rounded-xl border p-5">
          <h2 id="badges-title" className="font-semibold">バッジ</h2>
          <div className="flex flex-wrap gap-3">
            <Badge>基本</Badge>
            <Badge variant="secondary">補助</Badge>
            <Badge variant="outline">長い日本語の表示見本</Badge>
          </div>
        </section>

        <section aria-labelledby="checkboxes-title" className="space-y-4 rounded-xl border p-5">
          <h2 id="checkboxes-title" className="font-semibold">チェックボックス</h2>
          <div className="flex items-center gap-3">
            <Checkbox id="sample-checkbox" />
            <Label htmlFor="sample-checkbox">選択の見本</Label>
          </div>
          <div className="flex items-center gap-3">
            <Checkbox id="checked-checkbox" defaultChecked />
            <Label htmlFor="checked-checkbox">選択済みの見本</Label>
          </div>
          <div className="flex items-center gap-3">
            <Checkbox id="disabled-checkbox" disabled />
            <Label htmlFor="disabled-checkbox">無効な選択の見本</Label>
          </div>
        </section>

        <section aria-labelledby="selects-title" className="space-y-4 rounded-xl border p-5">
          <h2 id="selects-title" className="font-semibold">ネイティブ選択</h2>
          <div className="space-y-2">
            <Label htmlFor="sample-select">選択肢の見本</Label>
            <NativeSelect id="sample-select" defaultValue="first">
              <NativeSelectOption value="first">最初の選択肢</NativeSelectOption>
              <NativeSelectOption value="second">次の選択肢</NativeSelectOption>
              <NativeSelectOption value="long">長い日本語の選択肢の見本</NativeSelectOption>
            </NativeSelect>
          </div>
          <div className="space-y-2">
            <Label htmlFor="disabled-select">無効な選択肢の見本</Label>
            <NativeSelect id="disabled-select" disabled>
              <NativeSelectOption>操作できません</NativeSelectOption>
            </NativeSelect>
          </div>
        </section>

        <section aria-labelledby="pagination-title" className="space-y-4 rounded-xl border p-5">
          <h2 id="pagination-title" className="font-semibold">ページ送り</h2>
          <p className="text-sm text-muted-foreground">表示だけの見本です。選択しても移動しません。</p>
          <Pagination>
            <PaginationContent>
              <PaginationItem><PaginationPrevious /></PaginationItem>
              <PaginationItem><PaginationLink aria-label="1ページ目" isActive>1</PaginationLink></PaginationItem>
              <PaginationItem><PaginationLink aria-label="2ページ目">2</PaginationLink></PaginationItem>
              <PaginationItem><PaginationEllipsis /></PaginationItem>
              <PaginationItem><PaginationNext /></PaginationItem>
            </PaginationContent>
          </Pagination>
        </section>
      </div>
    </main>
  );
}
