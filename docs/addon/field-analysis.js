/* global React ReactDOM */
import { sfConn, apiVersion } from "./inspector.js";
import { FieldDependencyAiService } from "./ai_service.js";

class FieldAnalysisApp extends React.Component {
  constructor(props) {
    super(props);

    // Parse URL params
    const params = new URLSearchParams(window.location.search);
    this.sfHost = params.get("host");
    this.fieldName = params.get("fieldName");
    this.objectName = params.get("objectName");

    this.state = {
      loadingStep: "Initializing...",
      error: null,
      dependencies: null,
      aiInsight: null
    };

    this.aiService = new FieldDependencyAiService();
  }

  async componentDidMount() {
    try {
      // Connect to SF
      sfConn.getSession(this.sfHost).then(() => {
        this.runAnalysis();
      }).catch(err => {
        this.setState({ error: "Failed to connect to Salesforce: " + err.message, loadingStep: null });
      });
    } catch (err) {
      this.setState({ error: err.message, loadingStep: null });
    }
  }

  async runAnalysis() {
    try {
      this.setState({ loadingStep: "Fetching Salesforce Dependencies..." });
      const dependencies = await this.buildDependencyGraph();

      this.setState({ loadingStep: "Generating AI Impact Analysis...", dependencies });

      const aiInsight = await this.aiService.analyzeField({
        field: this.fieldName,
        objectName: this.objectName,
        dependencies: dependencies
      });

      this.setState({ loadingStep: null, aiInsight });
    } catch (err) {
      console.error(err);
      this.setState({ error: err.message, loadingStep: null });
    }
  }

  async buildDependencyGraph() {
    // 1. Get CustomField ID if this is a custom field
    let fieldId = null;
    let dependencies = {
      ApexClass: [],
      Flow: [],
      ValidationRule: [],
      Layout: []
    };

    if (this.fieldName.endsWith("__c")) {
      const devName = this.fieldName.replace(/__c$/, "");
      const cfQuery = `SELECT Id FROM CustomField WHERE DeveloperName = '${devName}' AND TableEnumOrId = '${this.objectName}'`;
      const cfResult = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(cfQuery));

      if (cfResult && cfResult.records && cfResult.records.length > 0) {
        fieldId = cfResult.records[0].Id;
      }
    }

    if (fieldId) {
      const depQuery = `SELECT MetadataComponentName, MetadataComponentType FROM MetadataComponentDependency WHERE RefMetadataComponentId = '${fieldId}'`;
      try {
        const depResult = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(depQuery));
        if (depResult && depResult.records) {
          depResult.records.forEach(record => {
            const type = record.MetadataComponentType;
            const name = record.MetadataComponentName;
            if (!dependencies[type]) dependencies[type] = [];
            dependencies[type].push(name);
          });
        }
      } catch (e) {
        console.warn("Failed to query MetadataComponentDependency", e);
      }
    } else {
      // Fallback for standard fields or fields where Tooling API graph is incomplete
      // 1. Layouts
      const layoutQuery = `SELECT Name FROM Layout WHERE TableEnumOrId = '${this.objectName}'`;
      try {
        const layoutResult = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(layoutQuery));
        if (layoutResult && layoutResult.records) {
          dependencies.Layout = layoutResult.records.map(r => r.Name);
        }
      } catch (e) {
        console.warn("Layout query failed", e);
      }

      // 2. Validation Rules via ErrorConditionFormula
      const vrQuery = `SELECT ValidationName, ErrorConditionFormula FROM ValidationRule WHERE EntityDefinition.DeveloperName = '${this.objectName}'`;
      try {
        const vrResult = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(vrQuery));
        if (vrResult && vrResult.records) {
          const matchedVRs = vrResult.records
            .filter(r => r.ErrorConditionFormula && r.ErrorConditionFormula.includes(this.fieldName))
            .map(r => r.ValidationName);
          if (matchedVRs.length > 0) dependencies.ValidationRule = matchedVRs;
        }
      } catch (e) {
        console.warn("ValidationRule fallback failed", e);
      }

      // 3. Apex usage via SOSL text search (Finds classes/triggers referencing the field string)
      try {
        const sosl = `FIND {${this.fieldName}} IN ALL FIELDS RETURNING ApexClass(Name), ApexTrigger(Name)`;
        const soslResult = await sfConn.rest("/services/data/v" + apiVersion + "/search/?q=" + encodeURIComponent(sosl));
        if (soslResult && soslResult.searchRecords) {
          soslResult.searchRecords.forEach(r => {
            const type = r.attributes.type;
            if (!dependencies[type]) dependencies[type] = [];
            // To prevent false positives, we would ideally parse the symbol table, but text search is a solid fallback
            if (!dependencies[type].includes(r.Name)) {
              dependencies[type].push(r.Name);
            }
          });
        }
      } catch (e) {
        console.warn("SOSL fallback failed", e);
      }
    }

    return dependencies;
  }

  renderLoading() {
    return React.createElement(
      "div",
      { className: "fa-loading" },
      React.createElement("div", { className: "fa-loading-spinner" }),
      React.createElement("h2", { className: "slds-text-heading_medium" }, this.state.loadingStep)
    );
  }

  renderError() {
    return React.createElement(
      "div",
      { className: "fa-error-banner" },
      React.createElement("strong", null, "Error: "),
      this.state.error
    );
  }

  renderDependencies() {
    const { dependencies } = this.state;
    if (!dependencies) return null;

    const sections = Object.keys(dependencies).filter(k => dependencies[k].length > 0);

    if (sections.length === 0) {
      return React.createElement("p", { className: "slds-m-top_medium slds-text-color_weak" }, "No dependencies found.");
    }

    return React.createElement(
      "div",
      { className: "fa-dependency-list slds-m-top_medium" },
      sections.map(type =>
        React.createElement(
          "div",
          { key: type, className: "slds-m-bottom_medium" },
          React.createElement("h3", { className: "slds-text-heading_small slds-m-bottom_small slds-text-title_caps" }, type),
          dependencies[type].map(name =>
            React.createElement(
              "div",
              { key: name, className: "fa-dependency-item" },
              React.createElement("span", null, name)
            )
          )
        )
      )
    );
  }

  render() {
    const { loadingStep, error, aiInsight, dependencies } = this.state;

    return React.createElement(
      "div",
      null,
      React.createElement(
        "div",
        { className: "fa-header" },
        React.createElement("h1", { className: "slds-text-heading_large" }, `Field Analysis: ${this.fieldName}`),
        React.createElement("p", { className: "slds-text-color_weak slds-m-top_xxx-small" }, `Object: ${this.objectName}`)
      ),
      error ? this.renderError() : null,
      loadingStep ? this.renderLoading() : null,
      !loadingStep && !error ? React.createElement(
        "div",
        { className: "fa-grid" },
        React.createElement(
          "div",
          { className: "fa-card" },
          React.createElement("h2", { className: "slds-text-heading_medium slds-m-bottom_medium" }, "✨ AI Insight"),
          aiInsight ? React.createElement(
            "div",
            null,
            React.createElement(
              "div",
              { className: "fa-insight-section" },
              React.createElement("h3", { className: "slds-text-title_caps slds-m-bottom_x-small slds-text-color_weak" }, "Risk Level"),
              React.createElement("span", { className: `fa-badge ${(aiInsight.riskLevel || "").toLowerCase()}` }, (aiInsight.riskLevel || "UNKNOWN").toUpperCase())
            ),
            React.createElement(
              "div",
              { className: "fa-insight-section" },
              React.createElement("h3", { className: "slds-text-title_caps slds-m-bottom_x-small slds-text-color_weak" }, "Executive Summary"),
              React.createElement("p", null, aiInsight.executiveSummary)
            ),
            React.createElement(
              "div",
              { className: "fa-insight-section" },
              React.createElement("h3", { className: "slds-text-title_caps slds-m-bottom_x-small slds-text-color_weak" }, "Refactoring Risks"),
              React.createElement("ul", { className: "slds-list_dotted slds-m-left_medium" },
                (aiInsight.refactoringRisks || []).map((risk, i) => React.createElement("li", { key: i }, risk))
              )
            ),
            React.createElement(
              "div",
              { className: "fa-insight-section" },
              React.createElement("h3", { className: "slds-text-title_caps slds-m-bottom_x-small slds-text-color_weak" }, "Recommendations"),
              React.createElement("ul", { className: "slds-list_dotted slds-m-left_medium" },
                (aiInsight.recommendations || []).map((rec, i) => React.createElement("li", { key: i }, rec))
              )
            )
          ) : React.createElement("p", { className: "slds-text-color_weak" }, "No AI insights generated.")
        ),
        React.createElement(
          "div",
          { className: "fa-card" },
          React.createElement("h2", { className: "slds-text-heading_medium" }, "Dependency Explorer"),
          this.renderDependencies()
        )
      ) : null
    );
  }
}

ReactDOM.render(React.createElement(FieldAnalysisApp), document.getElementById("root"));
