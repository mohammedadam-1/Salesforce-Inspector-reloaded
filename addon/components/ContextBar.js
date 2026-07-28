/* global React */
const h = React.createElement;

export default function ContextBar({ context, expanded, onToggle }) {
  const hasContext = context && (context.sobject || context.pageType || context.recordId);

  if (!hasContext) {
    return h("div", {
      className: `ai-contextbar ${expanded ? "ai-expanded" : "ai-collapsed"}`,
    });
  }

  return h("div", {
    className: `ai-contextbar ${expanded ? "ai-expanded" : "ai-collapsed"}`,
    onClick: onToggle,
    onKeyDown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); } },
    role: "button",
    tabIndex: 0,
    "aria-expanded": expanded,
    title: expanded ? "Collapse context" : "Show current page context",
  },
    h("div", { className: "ai-contextbar-indicator" }),
    h("div", { className: "ai-contextbar-content" },
      context.sobject && h("div", { className: "ai-contextbar-row" },
        h("span", { className: "ai-contextbar-label" }, "Object:"),
        h("span", { className: "ai-contextbar-value" }, context.sobject)
      ),
      context.pageType && h("div", { className: "ai-contextbar-row" },
        h("span", { className: "ai-contextbar-label" }, "Page:"),
        h("span", { className: "ai-contextbar-value" }, context.pageType)
      ),
      context.recordName && h("div", { className: "ai-contextbar-row" },
        h("span", { className: "ai-contextbar-label" }, "Record:"),
        h("span", { className: "ai-contextbar-value" }, context.recordName)
      )
    ),
    h("button", {
      className: "ai-contextbar-clear",
      onClick: (e) => { e.stopPropagation(); onToggle(); },
      title: "Clear context",
      "aria-label": "Clear context",
    },
      h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
        h("path", { d: "M3 3l6 6M9 3l-6 6" })
      )
    )
  );
}
