"use client";

import { useEffect, useState } from "react";
import { MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

const options = [
  { value: "light", label: "ライト", icon: SunIcon },
  { value: "dark", label: "ダーク", icon: MoonIcon },
] as const;

export function MockThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const [animate, setAnimate] = useState(false);
  const { theme, resolvedTheme, setTheme } = useTheme();
  const selected = (theme === "system" ? resolvedTheme : theme) === "dark" ? "dark" : "light";

  useEffect(() => { setMounted(true); }, []);

  return (
    <div
      className="release-theme-options" role="group" aria-label="表示テーマ"
      data-selected={mounted ? selected : "light"} data-ready={mounted} data-animate={animate}
    >
      <span className="release-theme-indicator" aria-hidden="true" />
      {options.map(({ value, label, icon: Icon }) => (
        <Button
          key={value} type="button" variant="ghost" size="icon" disabled={!mounted}
          aria-label={label} title={label} aria-pressed={mounted && selected === value}
          onClick={() => { setAnimate(selected !== value); setTheme(value); }}
        ><Icon aria-hidden="true" /></Button>
      ))}
    </div>
  );
}
