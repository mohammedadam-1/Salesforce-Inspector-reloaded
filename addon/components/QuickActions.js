/* global React */
const h = React.createElement;

function IconExplain() {
  return h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
    h("circle", { cx: "6", cy: "6", r: "4.5" }),
    h("path", { d: "M6 4.5v2.5" }),
    h("path", { d: "M6 9h.01" })
  );
}

function IconDeps() {
  return h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
    h("path", { d: "M2 6h8" }),
    h("path", { d: "M6 2v8" }),
    h("circle", { cx: "6", cy: "6", r: "1.5", fill: "currentColor" })
  );
}

function IconDocs() {
  return h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
    h("path", { d: "M3 1.5h6a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1z" }),
    h("path", { d: "M4 4.5h4" }),
    h("path", { d: "M4 6.5h4" }),
    h("path", { d: "M4 8.5h2" })
  );
}

function IconImpact() {
  return h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
    h("path", { d: "M6 1.5L1 10.5h10L6 1.5z" }),
    h("path", { d: "M6 5v2.5" }),
    h("path", { d: "M6 9.5h.01" })
  );
}

function IconSchema() {
  return h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
    h("circle", { cx: "6", cy: "3", r: "1.5" }),
    h("circle", { cx: "3", cy: "9", r: "1.5" }),
    h("circle", { cx: "9", cy: "9", r: "1.5" }),
    h("path", { d: "M6 4.5v3" }),
    h("path", { d: "M4.5 7.5l-1.5 1" }),
    h("path", { d: "M7.5 7.5l1.5 1" })
  );
}

const ACTION_ICONS = {
  "Explain this page": IconExplain,
  "Find dependencies": IconDeps,
  "Generate documentation": IconDocs,
  "Impact analysis": IconImpact,
  "Schema overview": IconSchema,
};

export default function QuickActions({ actions, onAction, visible }) {
  if (!visible || !actions || actions.length === 0) return null;

  return h("div", { className: "ai-quick-actions", role: "group", "aria-label": "Quick actions" },
    actions.map((action) => {
      const IconComponent = ACTION_ICONS[action];
      return h("button", {
        key: action,
        className: "ai-quick-action ai-primary-action",
        onClick: () => onAction(action),
        title: action,
        "aria-label": action,
      },
        IconComponent ? h(IconComponent) : null,
        h("span", null, action)
      );
    })
  );
}
