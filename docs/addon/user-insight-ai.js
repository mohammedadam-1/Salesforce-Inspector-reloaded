/* eslint-disable react/prop-types, react/no-deprecated */
/* global React ReactDOM initButton */
import {sfConn} from "./inspector.js";
import {PageHeader} from "./components/PageHeader.js";
import {UserInfoModel, createSpinForMethod, applyProductionStyling} from "./utils.js";
import {SalesforceUserInsightService} from "./salesforce_service.js";
import {UserInsightAiService} from "./ai_service.js";

let h = React.createElement;

class Model {
  constructor(sfHost, args) {
    this.reactCallback = null;
    this.sfHost = sfHost;
    this.sfLink = "https://" + sfHost;
    this.orgName = sfHost.split(".")[0]?.toUpperCase() || "";
    this.spinnerCount = 0;
    this.searchInput = args.get("userId") || args.get("userQuery") || "";
    this.searchResults = [];
    this.selectedUser = null;
    this.sections = null;
    this.summary = null;
    this.highlights = [];
    this.queryPlan = [];
    this.queryPlanSource = "ai";
    this.errorMessage = "";
    this.warningMessage = "";
    this.aiSettings = {};
    this.salesforceService = new SalesforceUserInsightService(sfHost);
    this.aiService = new UserInsightAiService();
    this.aiSettings = this.aiService.getConfiguration();
    this.spinFor = createSpinForMethod(this);
    applyProductionStyling(sfHost);
    this.userInfoModel = new UserInfoModel(this.spinFor.bind(this));
  }

  didUpdate(cb) {
    if (this.reactCallback) {
      this.reactCallback(cb);
    }
  }

  async runWithSpinner(action) {
    this.spinnerCount++;
    this.didUpdate();
    try {
      return await action();
    } finally {
      this.spinnerCount--;
      this.didUpdate();
    }
  }

  setError(error) {
    this.errorMessage = error?.message || String(error || "");
    this.didUpdate();
  }

  clearResults() {
    this.sections = null;
    this.summary = null;
    this.highlights = [];
    this.queryPlan = [];
    this.warningMessage = "";
  }

  async searchUsers() {
    const input = this.searchInput.trim();
    this.errorMessage = "";
    this.clearResults();
    if (!input) {
      this.searchResults = [];
      this.selectedUser = null;
      this.errorMessage = "Enter a Salesforce User Id, email, username, alias, or name.";
      this.didUpdate();
      return;
    }
    await this.runWithSpinner(async () => {
      const users = await this.salesforceService.searchUsers(input);
      this.searchResults = users;
      this.selectedUser = users.length === 1 ? users[0] : null;
      if (users.length === 0) {
        this.errorMessage = "No matching Salesforce user was found.";
      }
    }).catch(error => this.setError(error));
  }

  async selectUser(user) {
    this.selectedUser = user;
    this.searchInput = user.Email || user.Username || user.Id;
    this.searchResults = [user];
    this.errorMessage = "";
    this.clearResults();
    this.didUpdate();
  }

  async loadUserById(userId) {
    await this.runWithSpinner(async () => {
      const user = await this.salesforceService.getUserDetails(userId);
      if (!user) {
        this.errorMessage = "No matching Salesforce user was found.";
        return;
      }
      await this.selectUser(user);
    }).catch(error => this.setError(error));
  }

  async generateInsight() {
    if (!this.selectedUser) {
      await this.searchUsers();
      if (!this.selectedUser) {
        return;
      }
    }
    this.errorMessage = "";
    this.warningMessage = "";
    this.clearResults();
    await this.runWithSpinner(async () => {
      const objectInventory = await this.salesforceService.getObjectInventory();
      let queryPlanResponse;
      try {
        queryPlanResponse = await this.aiService.generateQueryPlan({
          user: this.selectedUser,
          objectInventory
        });
        this.queryPlanSource = "ai";
      } catch (error) {
        this.warningMessage = `${error.message} Using a limited built-in query plan instead.`;
        this.queryPlanSource = "fallback";
        queryPlanResponse = {queries: []};
      }
      let queryPlan = this.salesforceService.sanitizeQueryPlan(queryPlanResponse, {
        objectInventory,
        userId: this.selectedUser.Id,
        maxQueries: this.aiSettings.maxQueries
      });
      if (queryPlan.length === 0) {
        queryPlan = this.salesforceService.buildDefaultQueryPlan({
          objectInventory,
          userId: this.selectedUser.Id,
          maxQueries: this.aiSettings.maxQueries
        });
        this.queryPlanSource = "fallback";
      }
      this.queryPlan = queryPlan;
      this.sections = await this.salesforceService.executeQueryPlan(queryPlan);
      const sectionsForAi = this.salesforceService.summarizeSectionsForAi(this.sections);
      try {
        const summary = await this.aiService.summarize({
          user: this.selectedUser,
          sections: sectionsForAi
        });
        this.summary = summary.summary;
        this.highlights = summary.highlights || [];
      } catch (error) {
        this.summary = this.createDeterministicSummary(this.sections);
        this.highlights = [];
        this.warningMessage = this.warningMessage || `${error.message} Showing a non-AI summary of returned data.`;
      }
    }).catch(error => this.setError(error));
  }

  createDeterministicSummary(sections) {
    const user = this.selectedUser;
    if (!user || !sections) {
      return `User data retrieved for ${user?.Name || "user"}.`;
    }

    // Collect record counts by object type
    const recordsByType = {};
    Object.entries(sections || {}).forEach(([sectionKey, groups]) => {
      groups.forEach(group => {
        const objectName = group.objectLabel || group.objectApiName || "Record";
        if (!recordsByType[objectName]) {
          recordsByType[objectName] = 0;
        }
        recordsByType[objectName] += group.totalSize || 0;
      });
    });

    // Format the summary narrative
    const userRole = user.UserRole?.Name ? `in role ${user.UserRole.Name}` : "without a role";
    const profileName = user.Profile?.Name || "Unknown Profile";
    const activeStatus = user.IsActive ? "active" : "inactive";
    const lastLogin = user.LastLoginDate ? new Date(user.LastLoginDate).toLocaleDateString() : "never";

    const recordList = Object.entries(recordsByType)
      .filter(([, count]) => count > 0)
      .map(([name, count]) => `${count} ${name}${count !== 1 ? "s" : ""}`)
      .join(", ");

    const summary = recordList
      ? `${user.Name}, a ${profileName}, is ${activeStatus} and last logged in on ${lastLogin}. This user has references across ${recordList}.`
      : `${user.Name}, a ${profileName}, is ${activeStatus}. No owned or created records found.`;

    // Generate highlights from the data
    this.highlights = Object.entries(recordsByType)
      .filter(([, count]) => count > 0)
      .map(([name, count]) => `${count} ${name}${count !== 1 ? "s" : ""} owned/created`);

    return summary;
  }

  getOptionsLink() {
    const args = new URLSearchParams();
    args.set("host", this.sfHost);
    args.set("selectedTab", "ai");
    return "options.html?" + args;
  }
}

class App extends React.Component {
  constructor(props) {
    super(props);
    this.model = props.model;
    this.onSearchInput = this.onSearchInput.bind(this);
    this.onSearchSubmit = this.onSearchSubmit.bind(this);
    this.onGenerate = this.onGenerate.bind(this);
  }

  componentDidMount() {
    if (this.model.searchInput) {
      if (/^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$/.test(this.model.searchInput)) {
        this.model.loadUserById(this.model.searchInput);
      } else {
        this.model.searchUsers();
      }
    }
  }

  onSearchInput(e) {
    this.model.searchInput = e.target.value;
    this.model.didUpdate();
  }

  onSearchSubmit(e) {
    e.preventDefault();
    this.model.searchUsers();
  }

  onGenerate() {
    this.model.generateInsight();
  }

  renderUserCard(user) {
    return h("div", {className: "slds-card user-insight-card slds-m-top_medium"},
      h("div", {className: "slds-card__body slds-card__body_inner"},
        h("div", {className: "slds-text-title_caps slds-m-bottom_x-small"}, "Selected user"),
        h("h2", {className: "slds-text-heading_medium"}, user.Name),
        h("p", {className: "slds-text-color_weak"}, user.Email || user.Username),
        h("dl", {className: "slds-list_horizontal slds-wrap slds-m-top_small"},
          this.renderDetail("Id", user.Id),
          this.renderDetail("Profile", user.Profile?.Name || "Unknown"),
          this.renderDetail("Role", user.UserRole?.Name || "No role"),
          this.renderDetail("Active", user.IsActive ? "Yes" : "No"),
          this.renderDetail("Last login", user.LastLoginDate || "Not available")
        ),
        h("button", {
          className: "slds-button slds-button_brand slds-m-top_small",
          onClick: this.onGenerate,
          disabled: this.model.spinnerCount > 0
        }, "Generate User Insight")
      )
    );
  }

  renderDetail(label, value) {
    return [
      h("dt", {key: `${label}-label`, className: "slds-item_label slds-text-color_weak slds-truncate"}, label),
      h("dd", {key: `${label}-value`, className: "slds-item_detail slds-truncate", title: value}, value)
    ];
  }

  renderSearchResults() {
    const model = this.model;
    if (model.searchResults.length <= 1) {
      return null;
    }
    return h("div", {className: "slds-card user-insight-card slds-m-top_medium"},
      h("div", {className: "slds-card__header slds-grid"},
        h("header", {className: "slds-media slds-media_center slds-has-flexi-truncate"},
          h("div", {className: "slds-media__body"},
            h("h2", {className: "slds-card__header-title"}, "Choose a user")
          )
        )
      ),
      h("div", {className: "slds-card__body slds-card__body_inner"},
        model.searchResults.map(user =>
          h("div", {key: user.Id, className: "user-insight-user-row"},
            h("div", {className: "slds-grid slds-grid_vertical-align-center"},
              h("div", {className: "slds-col"},
                h("strong", {}, user.Name),
                h("div", {className: "slds-text-color_weak"}, user.Email || user.Username),
                h("div", {className: "slds-text-body_small"}, user.Profile?.Name || "Unknown profile")
              ),
              h("button", {
                className: "slds-button slds-button_neutral",
                onClick: () => model.selectUser(user)
              }, "Select")
            )
          )
        )
      )
    );
  }

  renderSummary() {
    const model = this.model;
    if (!model.summary && !model.sections) {
      return null;
    }
    return h("div", {className: "slds-card user-insight-card slds-m-bottom_medium"},
      h("div", {className: "slds-card__body slds-card__body_inner"},
        h("div", {className: "slds-grid slds-grid_vertical-align-center"},
          h("div", {className: "slds-col"},
            h("h2", {className: "slds-text-heading_medium"}, "Summary")
          ),
          h("span", {className: "slds-badge"}, model.queryPlanSource === "ai" ? "AI query plan" : "Safe fallback query plan")
        ),
        model.summary ? h("p", {className: "slds-m-top_small"}, model.summary) : null,
        model.highlights.length > 0
          ? h("ul", {className: "slds-list_dotted slds-m-top_small"},
            model.highlights.map((highlight, index) => h("li", {key: index}, highlight))
          )
          : null
      )
    );
  }

  renderSection(sectionKey, title) {
    const groups = this.model.sections?.[sectionKey] || [];
    if (!this.model.sections) {
      return null;
    }
    return h("div", {className: "slds-card user-insight-card slds-m-bottom_medium"},
      h("div", {className: "slds-card__header slds-grid"},
        h("header", {className: "slds-media slds-media_center slds-has-flexi-truncate"},
          h("div", {className: "slds-media__body"},
            h("h2", {className: "slds-card__header-title"}, title)
          )
        )
      ),
      h("div", {className: "slds-card__body slds-card__body_inner"},
        groups.length === 0
          ? h("p", {className: "slds-text-color_weak"}, "No query was generated for this section.")
          : groups.map(group => this.renderQueryGroup(group))
      )
    );
  }

  renderQueryGroup(group) {
    return h("article", {key: group.key, className: "slds-m-bottom_medium"},
      h("div", {className: "slds-grid slds-grid_vertical-align-center"},
        h("div", {className: "slds-col"},
          h("h3", {className: "slds-text-title_bold"}, group.title),
          h("div", {className: "slds-text-body_small slds-text-color_weak"},
            `${group.totalSize || 0} matching ${group.objectLabel || group.objectApiName} record(s)`
          )
        )
      ),
      group.error
        ? h("div", {className: "slds-notify slds-notify_alert slds-alert_warning slds-m-top_x-small", role: "alert"}, group.error)
        : group.records.length === 0
          ? h("p", {className: "slds-text-color_weak slds-m-top_x-small"}, "No records returned.")
          : h("div", {className: "slds-m-top_x-small"},
            group.records.map(record =>
              h("div", {key: record.Id, className: "user-insight-record"},
                h("a", {href: record.link, target: "_blank", rel: "noopener noreferrer"}, record.label),
                record.meta ? h("div", {className: "slds-text-body_small slds-text-color_weak"}, record.meta) : null
              )
            )
          )
    );
  }

  render() {
    const model = this.model;
    document.title = "User Insight AI";
    return h("div", {},
      h(PageHeader, {
        pageTitle: "User Insight AI",
        orgName: model.orgName,
        sfLink: model.sfLink,
        sfHost: model.sfHost,
        spinnerCount: model.spinnerCount,
        ...model.userInfoModel.getProps(),
        utilityItems: [
          h("div", {key: "ai-options", className: "slds-builder-header__utilities-item slds-p-horizontal_x-small sfir-border-none"},
            h("a", {href: model.getOptionsLink(), className: "slds-button slds-button_neutral"}, "AI Options")
          )
        ]
      }),
      h("main", {className: "slds-m-top_xx-large sfir-page-container slds-p-around_medium"},
        h("div", {className: "user-insight-layout"},
          h("aside", {},
            h("div", {className: "slds-card user-insight-card"},
              h("div", {className: "slds-card__body slds-card__body_inner"},
                h("h1", {className: "slds-text-heading_medium slds-m-bottom_small"}, "Find user references"),
                h("p", {className: "slds-text-color_weak slds-m-bottom_small"},
                  "Search by Salesforce User Id, email, username, alias, or name. Results use Salesforce REST API with your current session."
                ),
                h("form", {className: "user-insight-search", onSubmit: this.onSearchSubmit},
                  h("input", {
                    className: "slds-input",
                    type: "search",
                    value: model.searchInput,
                    onChange: this.onSearchInput,
                    placeholder: "005..., user@example.com, Jane Admin"
                  }),
                  h("button", {className: "slds-button slds-button_brand", type: "submit", disabled: model.spinnerCount > 0}, "Search")
                ),
                !model.aiSettings.apiKey
                  ? h("div", {className: "slds-notify slds-notify_alert slds-alert_warning slds-m-top_small", role: "alert"},
                    "Groq API key is not configured. Add it in AI Options before generating AI summaries."
                  )
                  : null
              )
            ),
            model.errorMessage
              ? h("div", {className: "slds-notify slds-notify_alert slds-alert_error slds-m-top_medium", role: "alert"}, model.errorMessage)
              : null,
            model.warningMessage
              ? h("div", {className: "slds-notify slds-notify_alert slds-alert_warning slds-m-top_medium", role: "alert"}, model.warningMessage)
              : null,
            this.renderSearchResults(),
            model.selectedUser ? this.renderUserCard(model.selectedUser) : null
          ),
          h("section", {},
            this.renderSummary(),
            model.sections
              ? [
                this.renderSection("owned", "Owned Records"),
                this.renderSection("created", "Created Records"),
                this.renderSection("activity", "Activity")
              ]
              : h("div", {className: "user-insight-empty"},
                h("div", {},
                  h("h2", {className: "slds-text-heading_medium"}, "No insight generated yet"),
                  h("p", {}, "Search for a user, select the match, then generate insight.")
                )
              )
          )
        )
      )
    );
  }
}

{
  const args = new URLSearchParams(location.search.slice(1));
  const sfHost = args.get("host");
  initButton(sfHost, true);
  sfConn.getSession(sfHost).then(() => {
    const root = document.getElementById("root");
    const model = new Model(sfHost, args);
    model.reactCallback = cb => {
      ReactDOM.render(h(App, {model}), root, cb);
    };
    ReactDOM.render(h(App, {model}), root);
  });
}
