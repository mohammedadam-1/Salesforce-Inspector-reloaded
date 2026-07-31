/* global React */
const h = React.createElement;

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return diffMin + "m ago";
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return diffHr + "h ago";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

class ConversationItem extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      editing: false,
      editValue: props.conv.title || "Untitled",
    };
    this.inputRef = null;
    this.setInputRef = (el) => { this.inputRef = el; };
    this.startEdit = this.startEdit.bind(this);
    this.commitEdit = this.commitEdit.bind(this);
    this.handleKeyDown = this.handleKeyDown.bind(this);
  }

  componentDidUpdate(prevProps, prevState) {
    if (!prevState.editing && this.state.editing && this.inputRef) {
      this.inputRef.focus();
      this.inputRef.select();
    }
  }

  startEdit(e) {
    e.stopPropagation();
    this.setState({
      editValue: this.props.conv.title || "Untitled",
      editing: true,
    });
  }

  commitEdit() {
    const trimmed = this.state.editValue.trim();
    if (trimmed && trimmed !== this.props.conv.title) {
      this.props.onRename(this.props.conv.id, trimmed);
    }
    this.setState({ editing: false });
  }

  handleKeyDown(e) {
    if (e.key === "Enter") { e.preventDefault(); this.commitEdit(); }
    if (e.key === "Escape") { this.setState({ editing: false }); }
  }

  render() {
    const { conv, isActive, onSelect, onDelete } = this.props;
    const { editing, editValue } = this.state;
    const msgCount = conv.messages?.length || 0;

    return h("div", {
      className: "ai-conv-item" + (isActive ? " ai-conv-active" : ""),
      onClick: () => onSelect(conv.id),
      role: "button",
      tabIndex: 0,
      onKeyDown: (e) => { if (e.key === "Enter") onSelect(conv.id); },
      "aria-label": conv.title || "Conversation",
    },
      h("div", { className: "ai-conv-item-content" },
        editing
          ? h("input", {
              ref: this.setInputRef,
              className: "ai-conv-edit-input",
              value: editValue,
              onChange: (e) => this.setState({ editValue: e.target.value }),
              onBlur: this.commitEdit,
              onKeyDown: this.handleKeyDown,
              onClick: (e) => e.stopPropagation(),
            })
          : h("div", { className: "ai-conv-title", title: conv.title },
              conv.title || "Untitled"
            ),
        h("div", { className: "ai-conv-meta" },
          h("span", null, msgCount + " messages"),
          h("span", null, formatDate(conv.updatedAt))
        )
      ),
      h("div", { className: "ai-conv-actions" },
        h("button", {
          className: "ai-conv-action-btn",
          onClick: this.startEdit,
          title: "Rename",
          "aria-label": "Rename conversation",
        },
          h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
            h("path", { d: "M8.5 1.5l2 2L4 10H2V8l6.5-6.5z" })
          )
        ),
        h("button", {
          className: "ai-conv-action-btn ai-conv-action-delete",
          onClick: (e) => { e.stopPropagation(); onDelete(conv.id); },
          title: "Delete",
          "aria-label": "Delete conversation",
        },
          h("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
            h("path", { d: "M2 3h8M4.5 3V2a1 1 0 011-1h1a1 1 0 011 1v1M3 3v7a1 1 0 001 1h4a1 1 0 001-1V3" })
          )
        ),
      )
    );
  }
}

export default function ConversationList({ conversations, activeId, onSelect, onNew, onDelete, onRename, onClose }) {
  return h("div", {
    className: "ai-dropdown-overlay",
    onClick: onClose,
    onKeyDown: (e) => { if (e.key === "Escape") onClose(); },
    role: "dialog",
    "aria-label": "Conversation history",
  },
    h("div", {
      className: "ai-conv-panel",
      onClick: (e) => e.stopPropagation(),
      role: "document",
    },
      h("div", { className: "ai-conv-header" },
        h("span", { className: "ai-conv-header-title" }, "Conversations"),
        h("button", {
          className: "ai-conv-new-btn",
          onClick: onNew,
          title: "New conversation",
          "aria-label": "Start new conversation",
        },
          h("svg", { width: "14", height: "14", viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round" },
            h("path", { d: "M7 1v12M1 7h12" })
          ),
          h("span", null, "New")
        )
      ),
      h("div", { className: "ai-conv-list" },
        conversations.length === 0
          ? h("div", { className: "ai-conv-empty" }, "No conversations yet")
          : conversations.map((conv) =>
              h(ConversationItem, {
                key: conv.id,
                conv,
                isActive: conv.id === activeId,
                onSelect,
                onDelete,
                onRename,
              })
            )
      ),
      h("button", {
        className: "ai-conv-close-btn",
        onClick: onClose,
        "aria-label": "Close conversation list",
      }, "Close")
    )
  );
}
