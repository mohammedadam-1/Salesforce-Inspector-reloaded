/* global React */
const h = React.createElement;

class ChatInput extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = { value: "" };
    this.textRef = React.createRef();
    this.onChange = this.onChange.bind(this);
    this.onKeyDown = this.onKeyDown.bind(this);
    this.onSend = this.onSend.bind(this);
  }

  onChange(e) {
    this.setState({ value: e.target.value });
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 80) + "px";
  }

  onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      this.onSend();
    }
  }

  onSend() {
    if (this.state.value.trim() && !this.props.disabled) {
      this.props.onSend(this.state.value);
      this.setState({ value: "" });
      if (this.textRef.current) {
        this.textRef.current.style.height = "auto";
      }
    }
  }

  focus() {
    if (this.textRef.current) {
      this.textRef.current.focus();
    }
  }

  render() {
    const { disabled, placeholder } = this.props;
    const { value } = this.state;
    const hasText = value.trim().length > 0;

    return h("div", { className: "ai-chat-input-area" },
      h("div", { className: "ai-chat-input-wrapper" },
        h("textarea", {
          ref: this.textRef,
          className: "ai-chat-input",
          placeholder: placeholder || "Ask anything...",
          value,
          onChange: this.onChange,
          onKeyDown: this.onKeyDown,
          disabled,
          rows: 1,
          "aria-label": "Chat input",
        }),
        h("button", {
          className: `ai-chat-send ${hasText ? "ai-visible" : ""}`,
          onClick: this.onSend,
          disabled: !hasText || disabled,
          "aria-label": "Send message",
        },
          h("svg", { width: "16", height: "16", viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" },
            h("path", { d: "M2 8l12-5-5 12-3-4z" }),
            h("path", { d: "M9 7l-3 4" })
          )
        )
      )
    );
  }
}

export default ChatInput;
