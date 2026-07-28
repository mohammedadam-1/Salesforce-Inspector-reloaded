/* global React */
const h = React.createElement;

export default function OrgSwitcher({ orgs, onClose, onSelect }) {
  const handleOverlay = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  return h("div", {
    style: {
      position: "fixed",
      top: 0, left: 0, right: 0, bottom: 0,
      zIndex: "var(--ai-z-overlay)",
    },
    onClick: handleOverlay,
  },
    h("div", { className: "ai-dropdown ai-open" },
      orgs.map((org) =>
        h("div", {
          key: org.id,
          className: `ai-dropdown-item ${org.status === "connected" ? "ai-active" : ""}`,
          onClick: () => { if (onSelect) onSelect(org); onClose(); },
        },
          h("span", {
            className: `ai-org-dot ${org.status === "connected" ? "ai-connected" : "ai-disconnected"}`,
          }),
          h("div", { style: { flex: 1 } },
            h("div", { style: { fontSize: "var(--ai-text-sm)", fontWeight: "var(--ai-weight-medium)" } }, org.name),
            h("div", { style: { fontSize: "var(--ai-text-xs)", color: "var(--ai-text-tertiary)" } }, org.username)
          )
        )
      ),
      h("div", { className: "ai-dropdown-divider" }),
      h("div", { className: "ai-dropdown-add" },
        h("span", null, "+"),
        h("span", null, "Connect Another Org")
      )
    )
  );
}
