export function validateModule(
  source: string,
): Array<{ start: number; end: number; name: string }>;
export function rewriteModule(
  source: string,
  map: Record<string, string>,
): string;
