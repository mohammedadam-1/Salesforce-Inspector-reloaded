/* global React */
const h = React.createElement;

const EXAMPLES = [
  { prefix: "\"", text: "Where is Account.Name used?\"" },
  { prefix: "\"", text: "Show me all validation rules\"" },
  { prefix: "\"", text: "Explain this page\"" },
  { prefix: "\"", text: "What objects are in my org?\"" },
];

export default function EmptyState({ onExampleClick, isUnconfigured }) {
  const handleExample = typeof onExampleClick === "function" ? onExampleClick : () => {};
  if (isUnconfigured) {
    return h("div", { className: "ai-empty" },
      h("div", { className: "ai-empty-icon" },
        h("svg", { width: "40", height: "40", viewBox: "0 0 40 40", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
          h("path", { d: "M20 5v4M20 31v4M5 20h4M31 20h4M8.5 8.5l3 3M28.5 28.5l3 3M8.5 31.5l3-3M28.5 11.5l3-3" }),
          h("circle", { cx: "20", cy: "20", r: "6" })
        )
      ),
      h("div", { className: "ai-empty-title" }, "Backend Not Configured"),
      h("div", { className: "ai-empty-desc" },
        "Set up your backend URL and API key in Options to enable AI chat."
      ),
    );
  }

  return h("div", { className: "ai-empty" },
    h("div", { className: "ai-empty-icon" },
      h("svg", { width: "40", height: "40", viewBox: "0 0 40 40", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round" },
        h("circle", { cx: "20", cy: "20", r: "16" }),
        h("path", { d: "M20 14v8" }),
        h("path", { d: "M20 26h.01" })
      )
    ),
    h("div", { className: "ai-empty-title" }, "How can I help you?"),
    h("div", { className: "ai-empty-desc" },
      "Ask questions about your Salesforce metadata to get started."
    ),
    h("div", { className: "ai-empty-examples" },
      EXAMPLES.map((ex, i) =>
        h("button", {
          key: i,
          onClick: () => handleExample(ex.text),
        }, ex.prefix + ex.text)
      )
    )
  );
}
