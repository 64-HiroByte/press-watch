"use client";

import { useRef, type FormEvent, type RefObject } from "react";
import { SidebarForm } from "@/components/press-releases/sidebar-filters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import type { Period } from "@/lib/press-release-dates";
import type { QueryState, QueryField } from "@/lib/press-release-query";

type Props = {
  formRef: RefObject<HTMLFormElement | null>;
  draft: QueryState["raw"];
  updateDraft: (key: QueryField, value: string) => void;
  period: Period;
  onPeriodChange: (value: Period) => void;
  canChange: boolean;
  invalidURL: boolean;
  repair: boolean;
  dateError: boolean;
  errors: string[];
  errorFields: QueryField[];
  onApply: (event: FormEvent<HTMLFormElement>) => boolean;
  onReset: () => void;
};

export function SearchForm({
  formRef,
  draft,
  updateDraft,
  period,
  onPeriodChange,
  canChange,
  invalidURL,
  repair,
  dateError,
  errors,
  errorFields,
  onApply,
  onReset,
}: Props) {
  const composing = useRef(false);
  function errorProps(field: QueryField) {
    const local = errorFields.includes(field);
    const apiDate = dateError && (field === "from" || field === "to");
    return {
      "aria-invalid": local || apiDate || undefined,
      "aria-describedby":
        [local ? "release-input-errors" : "", apiDate ? "release-date-error" : ""]
          .filter(Boolean)
          .join(" ") || undefined,
    };
  }
  return (
    <SidebarForm
      ref={formRef}
      className="release-search"
      onApply={(event) => {
        if (composing.current) {
          event.preventDefault();
          return false;
        }
        return onApply(event);
      }}
      onCompositionStart={() => {
        composing.current = true;
      }}
      onCompositionEnd={() => {
        composing.current = false;
      }}
      onKeyDownCapture={(event) => {
        if (
          event.key === "Enter" &&
          (composing.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)
        )
          event.preventDefault();
      }}
      noValidate
    >
      <div className="release-search-field">
        <Label htmlFor="release-keyword">キーワード</Label>
        <Input
          id="release-keyword"
          type="search"
          value={draft.q}
          {...errorProps("q")}
          onChange={(event) => updateDraft("q", event.target.value)}
          placeholder="タイトル内のキーワード"
        />
      </div>
      <fieldset className="release-date-range">
        <legend>公開日</legend>
        <Label htmlFor="release-period">期間</Label>
        <NativeSelect
          id="release-period"
          value={period}
          onChange={(event) => onPeriodChange(event.target.value as Period)}
        >
          <NativeSelectOption value="custom">任意の期間</NativeSelectOption>
          <NativeSelectOption value="week">直近1週間</NativeSelectOption>
          <NativeSelectOption value="month1">直近1ヶ月</NativeSelectOption>
          <NativeSelectOption value="month3">直近3ヶ月</NativeSelectOption>
          <NativeSelectOption value="month6">直近6ヶ月</NativeSelectOption>
          <NativeSelectOption value="year">直近1年</NativeSelectOption>
        </NativeSelect>
        <div className="release-date-inputs">
          {(["from", "to"] as const).map((key) => (
            <div key={key} className="release-date-field">
              <Label htmlFor={`release-date-${key}`}>{key === "from" ? "開始日" : "終了日"}</Label>
              <Input
                id={`release-date-${key}`}
                type={invalidURL ? "text" : "date"}
                value={draft[key]}
                onChange={(event) => updateDraft(key, event.target.value)}
                {...errorProps(key)}
              />
            </div>
          ))}
        </div>
      </fieldset>
      {dateError && (
        <p id="release-date-error" role="alert">
          公開日の開始日・終了日を確認して修正してください。
        </p>
      )}
      {invalidURL && (
        <>
          <Label htmlFor="release-repair-categories">カテゴリslug（1行に1個）</Label>
          <textarea
            id="release-repair-categories"
            {...errorProps("categories")}
            value={draft.categories}
            onChange={(event) => updateDraft("categories", event.target.value)}
          />
          <Label htmlFor="release-repair-page">ページ</Label>
          <Input
            id="release-repair-page"
            {...errorProps("page")}
            type="text"
            inputMode="numeric"
            value={draft.page}
            onChange={(event) => updateDraft("page", event.target.value)}
          />
        </>
      )}
      {errors.length > 0 && (
        <div id="release-input-errors" role="alert">
          {errors.map((error) => (
            <p key={error}>{error}</p>
          ))}
        </div>
      )}
      {repair && (
        <Button type="submit" disabled={!canChange}>
          条件を修正して適用
        </Button>
      )}
      <Button
        type={invalidURL ? "button" : "submit"}
        className="release-search-button"
        disabled={!canChange || invalidURL}
      >
        検索
      </Button>
      <Button
        type="button"
        variant="outline"
        className="release-search-reset"
        disabled={!canChange || invalidURL}
        onClick={onReset}
      >
        リセット
      </Button>
      <p className="release-feature-notice">カテゴリ選択は後続フェーズで実装します。</p>
    </SidebarForm>
  );
}
