import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkStringify from "remark-stringify";
import remarkGfm from "remark-gfm";
import type { Root, RootContent } from "mdast";
import { documentLink } from "./document-links.ts";

const markdown = unified().use(remarkParse).use(remarkGfm).use(remarkStringify);

/** Chat citations are relative to the workspace; reports may be nested. */
export function answerForReport(text: string): string {
  const tree = markdown.parse(text);
  function visit(node: Root | RootContent) {
    if (node.type === "link" || node.type === "definition") {
      if (
        !node.url.startsWith("#") &&
        !/^[a-z][a-z\d+.-]*:|^\/\//i.test(node.url)
      ) {
        const path = documentLink("", node.url);
        if (path !== null)
          node.url = "/" + path.split("/").map(encodeURIComponent).join("/");
      }
    }
    if ("children" in node) node.children.forEach(visit);
  }
  visit(tree);
  return markdown.stringify(tree);
}
