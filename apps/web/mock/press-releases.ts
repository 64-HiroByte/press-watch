import type { FixedCategoryLabel, ReleaseSummary } from "@/components/press-releases/list";

// Mockだけの表示用データ。本実装では選択肢・所属カテゴリをAPIから受け取る。
export const mockCategories = [
  { slug: "air", name: "大気" },
  { slug: "soil", name: "土壌" },
  { slug: "tap_water", name: "水道" },
  { slug: "environmental_water", name: "環境水" },
  { slug: "effluent", name: "排水" },
  { slug: "odor", name: "臭気" },
  { slug: "noise", name: "騒音" },
  { slug: "vibration", name: "振動" },
  { slug: "common", name: "共通" },
  { slug: "other", name: "その他" },
] as const satisfies readonly FixedCategoryLabel[];

export const mockReleases = [
  {
    id: "sample-1",
    publishedOn: "2026-10-02",
    detailUrl: "#",
    title: "大気環境の測定結果と今後の取組について",
    categories: [mockCategories[0]],
  },
  {
    id: "sample-2",
    publishedOn: "2026-10-02",
    detailUrl: "#",
    title:
      "水道水の安全性確保と河川・湖沼の水環境保全に向けた調査結果及び地域の関係機関と連携して進める今後の対策に関する意見募集について",
    categories: [mockCategories[2], mockCategories[3], mockCategories[4]],
  },
  {
    id: "sample-3",
    publishedOn: "2026-10-01",
    detailUrl: "#",
    title: "土壌汚染対策に関する説明会の開催について",
    categories: [mockCategories[1]],
  },
  {
    id: "sample-4",
    publishedOn: "2026-09-30",
    detailUrl: "#",
    title: "地域の環境保全活動に関するシンポジウムの開催について",
    categories: [],
  },
  {
    id: "sample-5",
    publishedOn: "2026-09-29",
    detailUrl: "#",
    title: "騒音及び振動の状況に関する調査結果について",
    categories: [mockCategories[6], mockCategories[7]],
  },
  {
    id: "sample-6",
    publishedOn: "2026-09-28",
    detailUrl: "#",
    title: "事業場における臭気・排水対策の事例集の公表について",
    categories: [mockCategories[4], mockCategories[5]],
  },
  {
    id: "sample-7",
    publishedOn: "2026-09-25",
    detailUrl: "#",
    title: "環境行政の共通課題に関する公開会議の開催について",
    categories: [mockCategories[8]],
  },
  {
    id: "sample-8",
    publishedOn: "2026-09-24",
    detailUrl: "#",
    title: "その他の環境関連施策に関する資料の公表について",
    categories: [mockCategories[9]],
  },
] as const satisfies readonly ReleaseSummary[];

export const longCategorySample = [
  {
    id: "layout-only",
    publishedOn: "2026-10-02",
    detailUrl: "#",
    title: "長いカテゴリ名がある場合の一覧行の表示見本",
    categories: [
      {
        slug: "layout_test",
        name: "レイアウト検証専用：地域の環境保全及び持続可能な社会の実現に向けた関係機関との連携に関する非常に長いカテゴリ名の表示見本（名称が長くても省略せず、複数行で全文を読むことができ、隣接するカテゴリやタイトルと重ならないことを確認するための架空のサンプル）",
      },
      mockCategories[0],
    ],
  },
] as const satisfies readonly ReleaseSummary[];
