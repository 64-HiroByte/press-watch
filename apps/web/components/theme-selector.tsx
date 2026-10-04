"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

export function ThemeSelector() {
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="flex items-center gap-3">
      <Label htmlFor="theme">テーマ</Label>
      <NativeSelect
        id="theme"
        disabled={!mounted}
        value={mounted ? theme : "system"}
        onChange={(event) => setTheme(event.target.value)}
      >
        <NativeSelectOption value="system">システム設定</NativeSelectOption>
        <NativeSelectOption value="light">ライト</NativeSelectOption>
        <NativeSelectOption value="dark">ダーク</NativeSelectOption>
      </NativeSelect>
    </div>
  );
}
