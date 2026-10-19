export type Period = "custom" | "week" | "month1" | "month3" | "month6" | "year";

export function tokyoToday(now: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

export function periodDates(period: Exclude<Period, "custom">, now: Date) {
  const to = tokyoToday(now);
  const date = new Date(`${to}T00:00:00Z`);
  const day = date.getUTCDate();
  if (period === "week") date.setUTCDate(day - 6);
  else {
    const months = { month1: 1, month3: 3, month6: 6, year: 12 }[period];
    date.setUTCDate(1);
    date.setUTCMonth(date.getUTCMonth() - months);
    const end = new Date(date);
    end.setUTCMonth(end.getUTCMonth() + 1, 0);
    date.setUTCDate(Math.min(day, end.getUTCDate()));
  }
  return { from: date.toISOString().slice(0, 10), to };
}
