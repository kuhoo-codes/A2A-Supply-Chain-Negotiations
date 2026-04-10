export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}


export function formatLabel(value: string): string {
  return value
    .split("-")
    .join(" ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
