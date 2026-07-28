/* global React */
const h = React.createElement;

const TOOL_ICONS = {
  metadata_search: "\u{1F50D}",
  dependency_analysis: "\u{1F517}",
  code_analysis: "\u{1F4DD}",
  documentation: "\u{1F4C4}",
  data_export: "\u{1F4E4}",
  impact_analysis: "\u{1F4CA}",
  default: "\u2699",
};

function getToolIcon(tool) {
  return TOOL_ICONS[tool] || TOOL_ICONS[tool.split("_")[0]] || TOOL_ICONS.default;
}

function formatDuration(ms) {
  if (!ms) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function ToolExecutionItem({ execution }) {
  const { tool, status, progress, progressMessage, durationMs, outputSummary, error } = execution;
  const isDone = status === "completed" || status === "failed";
  const isRunning = status === "running";
  const isFailed = status === "failed";

  return h("div", {
    className: "ai-tool-exec-item",
    "data-status": status,
  },
    h("div", { className: "ai-tool-exec-header" },
      h("span", { className: "ai-tool-exec-icon" }, getToolIcon(tool)),
      h("span", { className: "ai-tool-exec-name" }, tool.replace(/_/g, " ")),
      isRunning && !progress
        ? h("span", { className: "ai-tool-exec-spinner" })
        : isRunning && progress
          ? h("span", { className: "ai-tool-exec-progress-pct" }, `${Math.round(progress * 100)}%`)
          : isDone
            ? h("span", { className: `ai-tool-exec-badge ${isFailed ? "ai-badge-danger" : "ai-badge-success"}` },
                isFailed ? "Failed" : "Done"
              )
            : null,
    ),
    isRunning && progress !== undefined
      ? h("div", { className: "ai-tool-exec-progress-track" },
          h("div", {
            className: "ai-tool-exec-progress-fill",
            style: { width: `${Math.round(progress * 100)}%` },
          })
        )
      : null,
    progressMessage
      ? h("div", { className: "ai-tool-exec-message" }, progressMessage)
      : null,
    durationMs
      ? h("div", { className: "ai-tool-exec-duration" }, formatDuration(durationMs))
      : null,
    outputSummary
      ? h("div", { className: "ai-tool-exec-output" }, outputSummary)
      : null,
    error
      ? h("div", { className: "ai-tool-exec-error" }, error)
      : null,
  );
}

export default function ToolExecutionPanel({ executions }) {
  if (!executions || executions.length === 0) return null;

  const runningCount = executions.filter((e) => e.status === "running").length;
  const completedCount = executions.filter((e) => e.status === "completed").length;
  const failedCount = executions.filter((e) => e.status === "failed").length;

  return h("div", { className: "ai-tool-exec-panel" },
    h("div", { className: "ai-tool-exec-summary" },
      h("span", null, "Tool Execution"),
      runningCount > 0
        ? h("span", { className: "ai-tool-exec-summary-status" }, `${runningCount} running...`)
        : h("span", { className: "ai-tool-exec-summary-status" },
            `${completedCount} completed${failedCount > 0 ? `, ${failedCount} failed` : ""}`
          ),
    ),
    h("div", { className: "ai-tool-exec-list" },
      executions.map((exec, i) =>
        h(ToolExecutionItem, { key: exec.executionId || i, execution: exec })
      )
    ),
  );
}
