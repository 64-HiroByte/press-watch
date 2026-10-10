import { InboxIcon, SearchIcon } from "lucide-react";
import { RetrievalFailureDecoration } from "@/components/press-releases/retrieval-failure-decoration";
import { PressReleaseStatus } from "@/components/press-releases/status";

export function ResultState({ state }: { state: "error" | "empty" | "no-results" }) {
  const DecorationIcon =
    state === "error" ? RetrievalFailureDecoration : state === "empty" ? InboxIcon : SearchIcon;
  return (
    <section
      className="release-results"
      data-state={state}
      data-decorated
      aria-label="報道発表の表示"
    >
      <DecorationIcon
        className="release-results-decoration"
        viewBox={state === "empty" ? "-1.5 -1.5 27 27" : "0 0 24 24"}
        strokeWidth={state === "empty" ? 1.125 : 1}
        aria-hidden="true"
        focusable="false"
      />
      <PressReleaseStatus state={state} />
    </section>
  );
}
