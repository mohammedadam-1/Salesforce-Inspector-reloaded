/* global React ReactDOM initButton */
import { sfConn } from "./inspector.js";
import AllDataBoxSchemaExplorer from "./schema-explorer.js";

const h = React.createElement;

class App extends React.PureComponent {
  render() {
    const { sfHost, initialSearchText } = this.props;

    return h(
      "div",
      {
        className: "sfir-page-container slds-p-around_medium",
      },
      h(AllDataBoxSchemaExplorer, {
        sfHost,
        initialSearchText,
      })
    );
  }
}

function showError(message) {
  hideBootLoading();
  const root = document.getElementById("root");
  root.textContent = message;
}

function hideBootLoading() {
  const bootLoading = document.getElementById("bootLoading");
  if (bootLoading) {
    bootLoading.style.display = "none";
  }
}

function showLoading(message = "Loading Schema Explorer...") {
  hideBootLoading();
  ReactDOM.render(
    h(
      "div",
      {
        className: "sfir-page-container slds-p-around_medium",
      },
      h(
        "div",
        {
          className: "slds-is-relative",
          style: {
            minHeight: "220px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: "12px",
          },
        },
        h(
          "div",
          {
            className: "slds-spinner slds-spinner_medium slds-spinner_brand",
            role: "status",
          },
          h("span", { className: "slds-assistive-text" }, "Loading"),
          h("div", { className: "slds-spinner__dot-a" }),
          h("div", { className: "slds-spinner__dot-b" })
        ),
        h("div", { className: "slds-text-color_weak" }, message)
      )
    ),
    document.getElementById("root")
  );
}

{
  const args = new URLSearchParams(location.search.slice(1));
  const sfHost = args.get("host");
  const initialSearchText = String(args.get("q") || "").trim();

  if (!sfHost) {
    showError("Missing Salesforce host parameter.");
  } else {
    showLoading();
    initButton(sfHost, true);
    sfConn.getSession(sfHost)
      .then(() => {
        ReactDOM.render(
          h(App, {
            sfHost,
            initialSearchText,
          }),
          document.getElementById("root")
        );
        hideBootLoading();
      })
      .catch((error) => {
        console.error("Failed to initialize Schema Explorer page:", error);
        showError("Unable to initialize Schema Explorer.");
      });
  }
}
