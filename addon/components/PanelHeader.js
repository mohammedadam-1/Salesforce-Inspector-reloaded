/* global React */
const h = React.createElement;

function titleFromStatus(status) {
  if (status === "connected") return "Backend connected";
  if (status === "reconnecting") return "Reconnecting to backend...";
  if (status === "configuring") return "Connecting...";
  if (status === "offline") return "Backend offline";
  return "Backend status unknown";
}

export default function PanelHeader({ orgName, orgStatus, connectionStatus, onToggleOrgSwitcher, onToggleConversations, conversationTitle }) {
  const statusClass = orgStatus === "connected"
    ? "ai-connected"
    : orgStatus === "pending"
      ? "ai-pending"
      : "ai-disconnected";

  return h("div", { className: "ai-header" },
    h("div", { className: "ai-header-title-group" },
      h("div", {
        className: `ai-backend-dot ai-backend-${connectionStatus || "unknown"}`,
        title: titleFromStatus(connectionStatus || "unknown"),
        "aria-label": titleFromStatus(connectionStatus || "unknown"),
      }),
      h("span", { className: "ai-header-title", title: conversationTitle || "Inspector AI" },
        conversationTitle || "Inspector AI"
      ),
    ),
    h("div", { className: "ai-header-actions" },
      h("button", {
        className: "ai-btn ai-btn-ghost ai-btn-icon",
        onClick: onToggleConversations,
        title: "Conversation history",
        "aria-label": "Conversation history",
      },
        h("svg", { width: "16", height: "16", viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
          h("path", { d: "M2 3h12M2 8h12M2 13h8" })
        )
      ),
      h("button", {
        className: "ai-org-trigger",
        onClick: onToggleOrgSwitcher,
        title: "Switch organization",
      },
        h("span", { className: `ai-org-dot ${statusClass}` }),
        h("span", null, orgName || "Not connected"),
        h("svg", {
          width: "10", height: "10", viewBox: "0 0 10 10",
          style: { marginLeft: "2px" },
        },
          h("path", {
            d: "M2 3l3 4 3-4",
            fill: "none",
            stroke: "currentColor",
            strokeWidth: "1.5",
            strokeLinecap: "round",
          })
        )
      ),
      h("button", {
        className: "ai-btn ai-btn-ghost ai-btn-icon",
        title: "Settings (coming soon)",
        "aria-label": "Settings (coming soon)",
        disabled: true,
      },
        h("svg", { width: "16", height: "16", viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
          h("circle", { cx: "8", cy: "8", r: "1.5" }),
          h("path", { d: "M8 1v2M8 13v2M1 8h2M13 8h2M2.5 2.5l1.5 1.5M12 12l1.5 1.5M2.5 13.5l1.5-1.5M12 4l1.5-1.5" })
        )
      ),
    )
  );
}
