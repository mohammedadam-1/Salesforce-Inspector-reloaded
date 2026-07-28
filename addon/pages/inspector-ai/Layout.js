/* global React */
const h = React.createElement;

export default function WorkspaceLayout({
  header,
  headerActions,
  contextBar,
  sidebar,
  chat,
  timeline,
  inputArea,
}) {
  const [sidebarVisible, setSidebarVisible] = React.useState(true);

  return h("div", {className: "ai-workspace"},
    h("div", {className: "ai-workspace-header"},
      header || h("div", {className: "ai-workspace-header-title"}, "Inspector AI"),
      h("div", {className: "ai-workspace-header-actions"},
        h("button", {
          className: "ai-workspace-btn",
          onClick: () => setSidebarVisible(!sidebarVisible),
          title: sidebarVisible ? "Hide history" : "Show history",
        }, sidebarVisible ? "\u{1F4CB}" : "\u{1F4DD}"),
        headerActions
      )
    ),
    h("div", {className: "ai-workspace-body"},
      sidebarVisible && h("div", {className: "ai-workspace-sidebar"}, sidebar),
      h("div", {className: "ai-workspace-main"},
        contextBar && h("div", {className: "ai-workspace-context-bar"}, contextBar),
        h("div", {className: "ai-workspace-chat"},
          h("div", {className: "ai-workspace-chat-inner"}, chat)
        ),
        timeline && h("div", {className: "ai-workspace-timeline"}, timeline),
        h("div", {className: "ai-workspace-input-area"}, inputArea)
      )
    )
  );
}
