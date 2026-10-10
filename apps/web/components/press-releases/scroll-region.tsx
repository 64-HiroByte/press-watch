import type { ComponentProps } from "react";

export function ScrollRegion(props: ComponentProps<"div">) {
  return (
    <div
      {...props}
      className="release-main"
      role="region"
      aria-label="報道発表一覧のスクロール領域"
      tabIndex={0}
    />
  );
}
