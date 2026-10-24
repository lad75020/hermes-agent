import { parse } from "../vendor/acorn.mjs";
export const allowedImports = new Set([
  "@hermes/plugin-sdk",
  "react",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
]);
/** Parse, never execute. A single pre-bundled ESM entry; only SDK/React imports. */
export function validateModule(source) {
  const ast = parse(source, { ecmaVersion: "latest", sourceType: "module" }),
    imports = [];
  function walk(node) {
    if (!node || typeof node !== "object") return;
    if (node.type === "ImportExpression" || node.type === "MetaProperty")
      throw Error(
        "Dynamic import/import.meta forbidden: supply a single bundled module",
      );
    if (
      [
        "ImportDeclaration",
        "ExportNamedDeclaration",
        "ExportAllDeclaration",
      ].includes(node.type) &&
      node.source
    ) {
      if (!allowedImports.has(node.source.value))
        throw Error("Module import not approved: " + node.source.value);
      imports.push({
        start: node.source.start,
        end: node.source.end,
        name: node.source.value,
      });
    }
    for (const [key, value] of Object.entries(node)) {
      if (key === "start" || key === "end") continue;
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value === "object") walk(value);
    }
  }
  walk(ast);
  return imports;
}
export function rewriteModule(source, map) {
  const imports = validateModule(source);
  for (const item of imports.sort((a, b) => b.start - a.start)) {
    if (!map[item.name]) throw Error("SDK import unavailable");
    source =
      source.slice(0, item.start) +
      JSON.stringify(map[item.name]) +
      source.slice(item.end);
  }
  return source;
}
