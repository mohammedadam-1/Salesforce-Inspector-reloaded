/* global React */
const h = React.createElement;

export default function ErrorState({ message, details, onRetry }) {
  return h("div", { className: "ai-error" },
    h("div", { className: "ai-error-icon" },
      h("svg", { width: "40", height: "40", viewBox: "0 0 40 40", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
        h("circle", { cx: "20", cy: "20", r: "16" }),
        h("path", { d: "M20 14v6" }),
        h("path", { d: "M20 24h.01" })
      )
    ),
    h("div", { className: "ai-error-title" }, "Something went wrong"),
    h("div", { className: "ai-error-desc" }, message || "An unexpected error occurred."),
    details && h("div", { className: "ai-error-details" }, details),
    h("div", { className: "ai-error-actions" },
      onRetry && h("button", {
        className: "ai-btn ai-btn-primary",
        onClick: onRetry,
      }, "Retry"),
    )
  );
}
