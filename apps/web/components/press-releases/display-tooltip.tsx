"use client";

import type { ReactElement } from "react";
import { Tooltip } from "@base-ui/react/tooltip";

export function DisplayTooltip({ label, children }: { label: string; children: ReactElement }) {
  return (
    <Tooltip.Provider delay={150}>
      <Tooltip.Root>
        <Tooltip.Trigger render={children} />
        <Tooltip.Portal>
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
