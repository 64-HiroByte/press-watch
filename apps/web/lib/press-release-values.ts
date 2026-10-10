export const categorySlug = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;

export function validDate(value: string): boolean {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value) || value.startsWith("0000")) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function safeHttpURL(value: string): boolean {
  if (!/^https?:\/\//i.test(value) || /[^\x21-\x7e]|[<>"\\^`{|}]|%(?![0-9a-f]{2})/i.test(value))
    return false;
  try {
    const authority = value.match(/^https?:\/\/([^/?#]*)/i)?.[1];
    if (!authority || authority.includes("@") || authority.includes("%")) return false;
    const url = new URL(value);
    return (
      ["http:", "https:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password
    );
  } catch {
    return false;
  }
}
