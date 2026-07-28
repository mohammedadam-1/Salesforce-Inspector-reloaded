/* eslint-disable react/prop-types */
/* global React */
const h = React.createElement;

const CITATION_TYPE_COLORS = {
  soql: "#4caf50",
  apex: "#2196f3",
  metadata: "#ff9800",
  documentation: "#9c27b0",
  debug: "#f44336",
  permission: "#00bcd4",
  flow: "#e91e63",
  default: "#607d8b",
};

export default function CitationChips({citations = [], onNavigate}) {
  if (!citations || citations.length === 0) return null;

  return h("div", {className: "ai-citation-chips"},
    h("span", {className: "ai-citation-label"}, "Sources"),
    citations.map((citation, idx) => {
      const color = CITATION_TYPE_COLORS[citation.type] || CITATION_TYPE_COLORS.default;
      return h("button", {
        key: citation.id || idx,
        className: "ai-citation-chip",
        onClick: () => { if (onNavigate && citation.url) onNavigate(citation.url, citation); },
        title: citation.description || citation.title || "",
      },
      h("span", {
        className: "ai-citation-type-badge",
        style: {backgroundColor: color},
      }, (citation.type || "ref").charAt(0).toUpperCase()),
      h("span", {className: "ai-citation-title"}, citation.title || citation.name || `Source ${idx + 1}`),
      citation.url ? h("span", {className: "ai-citation-link-icon"}, "\u2197") : null
      );
    })
  );
}
