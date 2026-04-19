export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function api(path: string) {
  return `${apiBaseUrl}${path}`;
}
