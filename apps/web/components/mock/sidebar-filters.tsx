"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode, type RefObject } from "react";
import { XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

export type MockSearchConditions = {
  keyword: string;
  publishedFrom: string;
  publishedTo: string;
};

type SidebarFiltersProps = {
  children: ReactNode;
  onSearch: (conditions: MockSearchConditions) => void;
  renderMain: (controls: {
    drawerOpen: boolean;
    openDrawer: () => void;
    rememberTriggerFocus: () => void;
    triggerRef: RefObject<HTMLButtonElement | null>;
  }) => ReactNode;
};

export function MockSidebarFilters({ children, onSearch, renderMain }: SidebarFiltersProps) {
  const panelRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const restoreTriggerFocus = useRef(false);
  const lastFilterFocus = useRef<HTMLElement | null>(null);
  const pointerStartedOnBackdrop = useRef(false);
  const pagePosition = useRef({ left: 0, top: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const narrowScreen = window.matchMedia("(width < 768px)");
    let wasNarrow: boolean | undefined;

    function syncLayout() {
      if (!panel) return;
      // ソフトウェアキーボードなどによる狭い画面内のリサイズでは、開いたドロワーを維持する。
      if (narrowScreen.matches && wasNarrow) return;
      wasNarrow = narrowScreen.matches;
      // CSSでパネルが隠れると、幅変更の通知より先にbodyへフォーカスが戻ることがある。
      const focused = document.activeElement === document.body && lastFilterFocus.current
        ? lastFilterFocus.current : document.activeElement;
      const focusInPanel = panel.contains(focused);
      const position = panel.matches(":modal") ? pagePosition.current : { left: window.scrollX, top: window.scrollY };
      restoreTriggerFocus.current = false;
      setDrawerOpen(false);

      if (narrowScreen.matches) {
        if (panel.open) panel.close();
        if (focusInPanel) triggerRef.current?.focus({ preventScroll: true });
      } else {
        if (panel.matches(":modal")) panel.close();
        // 通常のサイドバー表示では、show()による自動フォーカス移動を避ける。
        panel.open = true;
        // 幅変更で隠れる閉じるボタン・見出しから、通常の検索欄へ戻す。
        if (focusInPanel && focused instanceof HTMLElement && focused.getClientRects().length > 0) {
          focused.focus({ preventScroll: true });
        } else if (focusInPanel || focused === triggerRef.current) {
          panel.querySelector<HTMLInputElement>('input[type="search"]')?.focus({ preventScroll: true });
        } else if (focused instanceof HTMLElement) {
          focused.focus({ preventScroll: true });
        }
      }
      window.scrollTo({ ...position, behavior: "instant" });
    }

    syncLayout();
    window.addEventListener("resize", syncLayout);
    return () => {
      window.removeEventListener("resize", syncLayout);
      restoreTriggerFocus.current = false;
      if (panel.open) panel.close();
    };
  }, []);

  function openDrawer() {
    const panel = panelRef.current;
    if (!panel || !window.matchMedia("(width < 768px)").matches) return;
    pagePosition.current = { left: window.scrollX, top: window.scrollY };
    if (panel.open) panel.close();
    restoreTriggerFocus.current = true;
    panel.showModal();
    panel.scrollTop = 0;
    headingRef.current?.focus({ preventScroll: true });
    // showModal()の初期フォーカスで、背面の一覧が先頭へ動くことを防ぐ。
    window.scrollTo({ ...pagePosition.current, behavior: "instant" });
    setDrawerOpen(true);
  }

  function handleClose() {
    // closeイベントは非同期なので、幅変更後の再表示を閉状態に戻さない。
    if (panelRef.current?.open) return;
    setDrawerOpen(false);
    if (restoreTriggerFocus.current) {
      triggerRef.current?.focus({ preventScroll: true });
      window.scrollTo({ ...pagePosition.current, behavior: "instant" });
    }
    restoreTriggerFocus.current = false;
  }

  function handlePanelClick(event: MouseEvent<HTMLDialogElement>) {
    const panel = panelRef.current;
    if (!panel) return;
    const search = event.target instanceof Element
      ? event.target.closest(".release-search-button")?.closest(".release-search") : null;
    if (search) {
      onSearch({
        keyword: search.querySelector<HTMLInputElement>("#release-keyword")?.value ?? "",
        publishedFrom: search.querySelector<HTMLInputElement>("#release-date-from")?.value ?? "",
        publishedTo: search.querySelector<HTMLInputElement>("#release-date-to")?.value ?? "",
      });
      if (panel.matches(":modal")) panel.close();
    } else if (panel.matches(":modal") && pointerStartedOnBackdrop.current && event.target === panel) {
      const bounds = panel.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) {
        panel.close();
      }
    }
    pointerStartedOnBackdrop.current = false;
  }

  function handlePanelKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    const panel = panelRef.current;
    if (event.key !== "Tab" || !panel?.matches(":modal")) return;
    const focusable = Array.from(panel.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], [tabindex]'))
      .filter((element) => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === headingRef.current)) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  function handleBackdropPointer(event: MouseEvent<HTMLDialogElement>) {
    const panel = panelRef.current;
    pointerStartedOnBackdrop.current = false;
    if (!panel?.matches(":modal") || event.target !== panel) return;
    const bounds = panel.getBoundingClientRect();
    pointerStartedOnBackdrop.current = event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
  }

  return (
    <>
      <div className="release-mobile-bar">
        <span>PressWatch</span>
      </div>
      <aside className="release-filters release-sidebar-filters" aria-label="検索とカテゴリ">
        <dialog
          ref={panelRef} id="mock-filter-panel" className="release-filter-panel" open aria-label="検索条件"
          onClose={handleClose} onClick={handlePanelClick} onPointerDown={handleBackdropPointer}
          onKeyDown={handlePanelKeyDown}
          onFocusCapture={(event) => { lastFilterFocus.current = event.target; }}
          onBlurCapture={(event) => {
            if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) lastFilterFocus.current = null;
          }}
        >
          <div className="release-drawer-heading">
            <h2 ref={headingRef} tabIndex={-1}>検索条件</h2>
            <Button type="button" variant="ghost" className="release-filter-close" aria-label="検索条件を閉じる" onClick={() => panelRef.current?.close()}>
              <XIcon aria-hidden="true" />
            </Button>
          </div>
          <p className="release-sidebar-brand">PressWatch<span>環境省の報道発表</span></p>
          {children}
        </dialog>
      </aside>
      {renderMain({ drawerOpen, openDrawer, triggerRef, rememberTriggerFocus: () => { lastFilterFocus.current = triggerRef.current; } })}
    </>
  );
}
