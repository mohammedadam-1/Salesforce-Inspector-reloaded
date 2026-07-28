/* global React */
const h = React.createElement;
import MarkdownRenderer from "./MarkdownRenderer.js";
import ToolExecutionPanel from "./ToolExecutionPanel.js";

function formatTime(date) {
  if (!date) return "";
  const d = date instanceof Date ? date : new Date(date);
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return diffMin + "m ago";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); } catch (e) { /* ignore */ }
  document.body.removeChild(ta);
}

function ReasoningSection({ text }) {
  const [open, setOpen] = React.useState(false);
  if (!text) return null;
  return h("div", { className: "ai-reasoning-section" },
    h("button", {
      className: "ai-reasoning-toggle",
      onClick: () => setOpen(!open),
      "aria-expanded": open,
    },
      h("span", { className: "ai-reasoning-toggle-icon" }, open ? "\u25BC" : "\u25B6"),
      h("span", null, "Reasoning"),
    ),
    open && h("div", { className: "ai-reasoning-content" }, text),
  );
}

function CitationChips({ citations }) {
  if (!citations || citations.length === 0) return null;
  return h("div", { className: "ai-citation-chips" },
    h("span", { className: "ai-citation-label" }, "Sources:"),
    citations.map((c, i) =>
      h("button", {
        key: c.id || i,
        className: "ai-citation-chip",
        title: c.title,
        onClick: () => {
          if (c.url) window.open(c.url, "_blank", "noopener");
        },
      },
        h("span", { className: "ai-citation-type" }, c.type.substring(0, 2)),
        h("span", { className: "ai-citation-title" }, c.title),
        c.url && h("span", { className: "ai-citation-link-icon" }, "\u2197"),
      )
    ),
  );
}

export default function ChatMessage({ role, content, time, error, isStreaming, onRetry, toolExecutions, citations, reasoning }) {
  const isUser = role === "user";
  const avatarClass = isUser ? "ai-user" : "ai-assistant";
  const avatarLabel = isUser ? "U" : "\u2726";
  const hasError = !!error;
  const showActions = !isUser && !hasError;

  return h("div", { className: "ai-fade-in", style: { marginBottom: "var(--ai-space-2)" } },
    h("div", { className: "ai-message-header" },
      h("div", { className: `ai-message-avatar ${avatarClass}` }, avatarLabel),
      h("span", { className: "ai-message-role" }, isUser ? "You" : "Assistant"),
      h("span", { className: "ai-message-time" }, formatTime(time))
    ),
    !isUser && h(ToolExecutionPanel, { executions: toolExecutions }),
    hasError
      ? h("div", { className: "ai-message-bubble ai-message-error" },
          h("div", { className: "ai-error-icon" }, "\u26A0"),
          h("div", { className: "ai-error-text" }, error),
          onRetry ? h("button", {
            className: "ai-message-retry-btn",
            onClick: onRetry,
            "aria-label": "Retry",
          },
            h("svg", { width: "14", height: "14", viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
              h("path", { d: "M1 7a6 6 0 1 1 2.5 4.9" }),
              h("path", { d: "M1 10.5V7h3.5" })
            ),
            h("span", null, "Retry")
          ) : null
        )
      : h("div", { className: "ai-message-bubble" },
          !isUser && h(ReasoningSection, { text: reasoning }),
          h(MarkdownRenderer, { content }),
          !isUser && h(CitationChips, { citations }),
          isStreaming ? h("span", { className: "ai-streaming-cursor" }) : null
        ),
    showActions
      ? h("div", { className: "ai-message-actions" },
          h("button", {
            className: "ai-message-action-btn",
            title: "Copy response",
            "aria-label": "Copy response to clipboard",
            onClick: () => copyToClipboard(content),
          },
            h("svg", { width: "14", height: "14", viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
              h("rect", { x: "2", y: "2", width: "9", height: "9", rx: "1.5" }),
              h("path", { d: "M5 5V3.5A1.5 1.5 0 0 1 6.5 2h4A1.5 1.5 0 0 1 12 3.5v4A1.5 1.5 0 0 1 10.5 9H9" })
            )
          )
        )
      : null
  );
}
