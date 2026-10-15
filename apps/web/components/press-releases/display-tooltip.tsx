"use client";

import type { ComponentProps, ReactElement } from "react";
import { Tooltip } from "@base-ui/react/tooltip";

export function DisplayTooltip({
  label,
  children,
  container,
}: {
  label: string;
  children: ReactElement;
  container?: ComponentProps<typeof Tooltip.Portal>["container"];
}) {
  return (
    <Tooltip.Provider delay={150}>
      <Tooltip.Root>
        <Tooltip.Trigger render={children} />
        <Tooltip.Portal container={container}>
          <Tooltip.Positioner
            side="bottom"
            sideOffset={8}
            className="release-display-tooltip-positioner"
          >
            <Tooltip.Popup className="release-display-tooltip">{label}</Tooltip.Popup>
          </Tooltip.Positioner>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
