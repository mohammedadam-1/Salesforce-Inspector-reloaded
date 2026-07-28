/* eslint-disable react/prop-types */
/* global React */
const h = React.createElement;

function getLevel(score) {
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

function getIcon(level) {
  switch (level) {
    case "high": return "\u2713";
    case "medium": return "\u26A0";
    case "low": return "\u2717";
    default: return "?";
  }
}

function getLabel(level) {
  switch (level) {
    case "high": return "High Confidence";
    case "medium": return "Medium Confidence";
    case "low": return "Low Confidence";
    default: return "Unknown";
  }
}

export default function ConfidenceBadge({confidence, label}) {
  if (confidence == null) return null;

  const level = getLevel(confidence);
  const tooltip = label || `AI confidence: ${Math.round(confidence * 100)}% - ${getLabel(level)}`;

  return h("span", {className: `ai-confidence-badge ${level}`, title: tooltip},
    h("span", {className: "ai-confidence-icon"}, getIcon(level)),
    h("span", null, `${Math.round(confidence * 100)}%`),
    h("span", {className: "ai-confidence-tooltip"}, tooltip)
  );
}
