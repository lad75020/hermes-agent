export const THEME_QUERY_PARAM = "theme";

export function readThemeQuery(search: string): string | null {
  const raw = new URLSearchParams(search).get(THEME_QUERY_PARAM);
  const value = raw?.trim();
  return value || null;
}

export function withThemeQuery(path: string, themeName: string): string {
  if (!themeName) return path;
  if (/^[a-z][a-z0-9+.-]*:/i.test(path)) return path;

  const hashIndex = path.indexOf("#");
  const beforeHash = hashIndex >= 0 ? path.slice(0, hashIndex) : path;
  const hash = hashIndex >= 0 ? path.slice(hashIndex) : "";

  const queryIndex = beforeHash.indexOf("?");
  const pathname = queryIndex >= 0 ? beforeHash.slice(0, queryIndex) : beforeHash;
  const search = queryIndex >= 0 ? beforeHash.slice(queryIndex + 1) : "";
  const params = new URLSearchParams(search);
  params.set(THEME_QUERY_PARAM, themeName);
  const query = params.toString();

  return `${pathname}${query ? `?${query}` : ""}${hash}`;
}
