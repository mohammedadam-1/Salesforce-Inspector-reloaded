/* global React */
const h = React.createElement;

function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function tokenizeInline(text) {
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end !== -1) {
        tokens.push({ type: "code", text: text.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end !== -1) {
        tokens.push({ type: "bold", text: text.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (text[i] === "*" && text[i + 1] !== "*") {
      const end = text.indexOf("*", i + 1);
      if (end !== -1) {
        tokens.push({ type: "italic", text: text.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (text[i] === "[" && text.includes("](")) {
      const closeBracket = text.indexOf("](", i);
      const closeParen = text.indexOf(")", closeBracket + 2);
      if (closeBracket !== -1 && closeParen !== -1) {
        const linkText = text.slice(i + 1, closeBracket);
        const linkUrl = text.slice(closeBracket + 2, closeParen);
        tokens.push({ type: "link", text: linkText, url: linkUrl });
        i = closeParen + 1;
        continue;
      }
    }
    if (tokens.length && tokens[tokens.length - 1].type === "text") {
      tokens[tokens.length - 1].text += text[i];
    } else {
      tokens.push({ type: "text", text: text[i] });
    }
    i++;
  }
  return tokens;
}

function renderInline(text) {
  const tokens = tokenizeInline(text);
  return tokens.map((t, i) => {
    switch (t.type) {
      case "code":
        return h("code", { key: i, className: "ai-md-code" }, t.text);
      case "bold":
        return h("strong", { key: i }, t.text);
      case "italic":
        return h("em", { key: i }, t.text);
      case "link":
        return h("a", { key: i, className: "ai-md-link", href: t.url, target: "_blank", rel: "noopener" }, t.text);
      default:
        return h("span", { key: i }, t.text);
    }
  });
}

function parseTable(lines, startIdx) {
  const headerLine = lines[startIdx];
  const sepLine = lines[startIdx + 1];
  const headers = headerLine.split("|").map(s => s.trim()).filter(Boolean);
  const alignments = sepLine ? sepLine.split("|").map(s => s.trim()).filter(Boolean) : [];
  const rows = [];
  let idx = startIdx + 2;
  while (idx < lines.length) {
    const line = lines[idx].trim();
    if (!line.startsWith("|") || line.startsWith("|---")) break;
    const cells = line.split("|").map(s => s.trim()).filter(Boolean);
    if (cells.length === 0) break;
    rows.push(cells);
    idx++;
  }
  return { headers, rows, endIdx: idx };
}

function getLang(lines, langHint) {
  return langHint || "";
}

function highlightLine(line, lang) {
  const el = document.createElement("span");
  el.textContent = line;
  return el.textContent;
}

export default function MarkdownRenderer({ content }) {
  if (!content) return null;
  const elements = [];
  const lines = content.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("### ")) {
      elements.push(h("h3", { key: i, className: "ai-md-h3" }, ...renderInline(line.slice(4))));
      i++;
      continue;
    }
    if (line.startsWith("## ")) {
      elements.push(h("h2", { key: i, className: "ai-md-h2" }, ...renderInline(line.slice(3))));
      i++;
      continue;
    }
    if (line.startsWith("# ")) {
      elements.push(h("h1", { key: i, className: "ai-md-h1" }, ...renderInline(line.slice(2))));
      i++;
      continue;
    }

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      const codeText = codeLines.join("\n");
      elements.push(h("div", { key: "code-" + i, className: "ai-md-code-block" },
        lang ? h("div", { className: "ai-md-code-lang" }, lang) : null,
        h("pre", null,
          h("code", { className: lang ? "language-" + lang : "" },
            ...codeLines.map((cl, j) => h("span", { key: j }, escapeHtml(cl) + "\n"))
          )
        )
      ));
      continue;
    }

    if (line.startsWith("|") && i + 1 < lines.length && lines[i + 1].includes("---")) {
      const table = parseTable(lines, i);
      const headerRow = h("thead", { key: "thead" },
        h("tr", null,
          table.headers.map((hdr, ci) => h("th", { key: ci }, hdr))
        )
      );
      const bodyRows = table.rows.map((row, ri) =>
        h("tr", { key: ri },
          row.map((cell, ci) => h("td", { key: ci }, ...renderInline(cell)))
        )
      );
      elements.push(h("div", { key: "table-" + i, className: "ai-md-table-wrapper" },
        h("table", { className: "ai-md-table" },
          headerRow,
          h("tbody", null, bodyRows)
        )
      ));
      i = table.endIdx;
      continue;
    }

    if (line.match(/^\d+\.\s/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^\d+\.\s/)) {
        const itemContent = lines[i].replace(/^\d+\.\s+/, "");
        items.push(h("li", { key: i }, ...renderInline(itemContent)));
        i++;
      }
      elements.push(h("ol", { key: "ol-" + i }, items));
      continue;
    }

    if (line.startsWith("- ") || line.startsWith("* ")) {
      const items = [];
      while (i < lines.length && (lines[i].startsWith("- ") || lines[i].startsWith("* "))) {
        const itemContent = lines[i].slice(2);
        items.push(h("li", { key: i }, ...renderInline(itemContent)));
        i++;
      }
      elements.push(h("ul", { key: "ul-" + i }, items));
      continue;
    }

    if (line.trim() === "") {
      elements.push(h("div", { key: "spacer-" + i, className: "ai-md-spacer" }));
      i++;
      continue;
    }

    elements.push(h("p", { key: "p-" + i }, ...renderInline(line)));
    i++;
  }

  return h("div", { className: "ai-md-root" }, elements);
}
