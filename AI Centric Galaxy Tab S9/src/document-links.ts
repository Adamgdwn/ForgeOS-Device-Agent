/** Resolve a document's relative citation inside the virtual workspace root. */
export function documentLink(
  documentPath: string,
  href: string,
): string | null {
  const origin = "https://workspace.invalid";
  try {
    const base = `${origin}/${documentPath.split("/").map(encodeURIComponent).join("/")}`;
    const resolved = new URL(href, base);
    if (resolved.origin !== origin) return null;
    return decodeURIComponent(resolved.pathname.slice(1));
  } catch {
    return null;
  }
}
