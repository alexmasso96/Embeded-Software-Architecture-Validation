// Minimal, dependency-free Markdown → HTML (shared by ChangeLog, Test Design
// preview, and the AI Chat thread). These are small, semi-trusted documents, but
// we still escape first so arbitrary text can't inject markup, then layer a few
// inline/block rules on top: headings, bold/italic, inline code, fenced code,
// bullet/numbered lists, horizontal rules, and paragraphs.

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function renderInline(s: string): string {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
}

export function renderMarkdown(md: string): string {
  const lines = (md ?? "").replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let inUl = false;
  let inOl = false;
  let inCode = false;
  const codeBuf: string[] = [];

  const closeLists = () => {
    if (inUl) {
      html.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      html.push("</ol>");
      inOl = false;
    }
  };
  const flushCode = () => {
    html.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
    codeBuf.length = 0;
  };

  for (const raw of lines) {
    if (/^\s*```/.test(raw)) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        closeLists();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(raw);
      continue;
    }

    const line = raw.trimEnd();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+\.\s+(.*)$/.exec(line);

    if (/^\s*---+\s*$/.test(line)) {
      closeLists();
      html.push("<hr />");
    } else if (heading) {
      closeLists();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
    } else if (bullet) {
      if (inOl) {
        html.push("</ol>");
        inOl = false;
      }
      if (!inUl) {
        html.push("<ul>");
        inUl = true;
      }
      html.push(`<li>${renderInline(bullet[1])}</li>`);
    } else if (numbered) {
      if (inUl) {
        html.push("</ul>");
        inUl = false;
      }
      if (!inOl) {
        html.push("<ol>");
        inOl = true;
      }
      html.push(`<li>${renderInline(numbered[1])}</li>`);
    } else if (line.trim() === "") {
      closeLists();
    } else {
      closeLists();
      html.push(`<p>${renderInline(line)}</p>`);
    }
  }
  if (inCode) flushCode();
  closeLists();
  return html.join("\n");
}
