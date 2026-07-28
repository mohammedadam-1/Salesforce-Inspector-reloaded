/* eslint-disable react/prop-types */
/* global React */
const h = React.createElement;

const actionIcons = {
  query: "\u{1F50D}",
  analyze: "\u{1F4CA}",
  navigate: "\u{1F517}",
  execute: "\u25B6",
  explain: "\u{1F4DD}",
  fix: "\u{1F527}",
  default: "\u{1F4AC}",
};

export default function NextActionsPanel({actions = [], onAction}) {
  if (!actions || actions.length === 0) return null;

  return h("div", {className: "ai-next-actions"},
    h("div", {className: "ai-next-actions-title"}, "Suggested Next Steps"),
    h("div", {className: "ai-next-actions-list"},
      actions.map((action, idx) =>
        h("button", {
          key: action.id || idx,
          className: "ai-next-action-btn",
          onClick: () => { if (onAction) onAction(action); },
          title: action.description || "",
        },
        h("span", null, actionIcons[action.type] || actionIcons.default),
        h("span", null, action.label || action.title || action.name)
        )
      )
    )
  );
}
