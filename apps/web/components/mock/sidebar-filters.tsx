"use client";

import type { ComponentProps, MouseEvent } from "react";
import { SidebarFilters } from "@/components/press-releases/sidebar-filters";

export type MockSearchConditions = { keyword: string; publishedFrom: string; publishedTo: string };

export function MockSidebarFilters({
  onSearch,
  ...props
}: Omit<ComponentProps<typeof SidebarFilters>, "onAction"> & {
  onSearch: (conditions: MockSearchConditions) => void;
}) {
  function handleAction(event: MouseEvent<HTMLDialogElement>, panel: HTMLDialogElement) {
    if (!(event.target instanceof Element)) return false;
    const reset = event.target.closest(".release-search-reset")?.closest(".release-search");
    const search = event.target.closest(".release-search-button")?.closest(".release-search");
    if (reset) {
      for (const input of reset.querySelectorAll<HTMLInputElement>("input")) input.value = "";
      onSearch({ keyword: "", publishedFrom: "", publishedTo: "" });
      return true;
    }
    if (!search) return false;
    onSearch({
      keyword: search.querySelector<HTMLInputElement>("#release-keyword")?.value ?? "",
      publishedFrom: search.querySelector<HTMLInputElement>("#release-date-from")?.value ?? "",
      publishedTo: search.querySelector<HTMLInputElement>("#release-date-to")?.value ?? "",
    });
    if (panel.matches(":modal")) panel.close();
    return true;
  }
  return <SidebarFilters {...props} onAction={handleAction} />;
}
