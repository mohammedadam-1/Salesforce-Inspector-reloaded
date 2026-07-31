/* eslint-disable react/prop-types */
/* global React */
const h = React.createElement;

export default class ContextPanel extends React.Component {
  constructor(props) {
    super(props);
    this.state = {expanded: true};
    this.toggleExpanded = this.toggleExpanded.bind(this);
    this.onRefreshClick = this.onRefreshClick.bind(this);
  }

  toggleExpanded() {
    this.setState((prev) => ({expanded: !prev.expanded}));
  }

  onRefreshClick(e) {
    e.stopPropagation();
    if (this.props.onRefresh) this.props.onRefresh();
  }

  render() {
    const {context, isLoading} = this.props;
    const {expanded} = this.state;

    if (isLoading) {
      return h("div", {className: "ai-context-panel"},
        h("div", {className: "ai-context-panel-header"}, "Loading context...")
      );
    }

    if (!context) {
      return h("div", {className: "ai-context-panel"},
        h("div", {className: "ai-context-panel-header"}, "No Salesforce context available")
      );
    }

    const contextItems = [
      context.orgName && {label: "Org", value: context.orgName},
      context.username && {label: "User", value: context.username},
      context.apiVersion && {label: "API", value: "v" + context.apiVersion},
      context.objectType && {label: "Object", value: context.objectType},
      context.recordId && {label: "Record", value: context.recordId},
      context.sfHost && {label: "Host", value: context.sfHost},
    ].filter(Boolean);

    return h("div", {className: "ai-context-panel"},
      h("div", {
        className: "ai-context-panel-header",
        onClick: this.toggleExpanded,
      },
      h("span", null, expanded ? "\u25BC" : "\u25B6"),
      h("span", null, "Salesforce Context"),
      contextItems.length > 0 && h("span", {
        style: {fontSize: 11, color: "var(--ai-text-secondary, #666)"},
      }, "(" + contextItems.length + " items)"),
      h("button", {
        className: "ai-workspace-btn",
        style: {marginLeft: "auto", padding: "2px 6px", fontSize: 11},
        onClick: this.onRefreshClick,
      }, "Refresh")
      ),
      expanded && h("div", {className: "ai-context-panel-body"},
        contextItems.map((item, idx) => h("div", {key: idx, className: "ai-context-item"},
          h("span", {className: "ai-context-item-label"}, item.label),
          h("span", {className: "ai-context-item-value"}, item.value)
        ))
      )
    );
  }
}
