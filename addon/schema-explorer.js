/* global React */
import {sfConn, apiVersion} from "./inspector.js";
import {DataCache} from "./utils.js";

const SCHEMA_CACHE_KEY = "SCHEMA_OBJECTS_LIST";

class AllDataBoxSchemaExplorer extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      searchText: "",
      objects: [],
      filteredObjects: [],
      isLoading: false,
      error: null,
      selectedIndex: -1,
    };
  }

  componentDidMount() {
    this.loadSchemaObjects();
  }

  loadSchemaObjects() {
    this.setState({isLoading: true, error: null});

    this.getSchemaObjects(this.props.sfHost)
      .then((objects) => {
        this.setState({
          objects,
          filteredObjects: objects,
          isLoading: false,
        });
      })
      .catch((err) => {
        console.error("Error loading schema objects:", err);
        this.setState({
          isLoading: false,
          error: "Failed to load schema objects",
        });
      });
  }

  async getSchemaObjects(sfHost) {
    const cached = await DataCache.getCachedData(SCHEMA_CACHE_KEY, sfHost, true, true);
    if (cached) {
      const cachedData = cached.data ?? cached;
      const normalizedCachedData = Array.isArray(cachedData)
        ? cachedData
        : Array.isArray(cachedData?.data)
          ? cachedData.data
          : null;

      if (Array.isArray(normalizedCachedData)) {
        return normalizedCachedData;
      }

      await DataCache.clearCache(SCHEMA_CACHE_KEY, sfHost, true, true);
    }

    return this.fetchSchemaObjectsFromAPI(sfHost);
  }

  async fetchSchemaObjectsFromAPI(sfHost) {
    try {
      const objectsMap = new Map();

      const describe = await sfConn.rest("/services/data/v" + apiVersion + "/sobjects/");
      if (describe && describe.sobjects) {
        for (const sobject of describe.sobjects) {
          objectsMap.set(sobject.name, {
            apiName: sobject.name,
            label: sobject.label || sobject.name,
            type: "Standard",
          });
        }
      }

      try {
        const entityQuery = `SELECT QualifiedApiName, Label FROM EntityDefinition ORDER BY Label LIMIT 2000`;
        const entityResult = await sfConn.rest(
          "/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(entityQuery)
        );

        if (entityResult && entityResult.records) {
          for (const record of entityResult.records) {
            const apiName = record.QualifiedApiName;
            const label = record.Label || apiName;
            if (objectsMap.has(apiName)) {
              objectsMap.get(apiName).label = label;
            } else {
              objectsMap.set(apiName, {
                apiName,
                label,
                type: "Custom",
              });
            }
          }
        }
      } catch (toolingErr) {
        console.warn("EntityDefinition query failed, using basic info only:", toolingErr);
      }

      const objects = Array.from(objectsMap.values()).sort((a, b) =>
        a.label.localeCompare(b.label)
      );

      await DataCache.setCachedData(SCHEMA_CACHE_KEY, sfHost, objects, true, true, null, false);

      return objects;
    } catch (err) {
      console.error("Error fetching schema objects:", err);
      throw err;
    }
  }

  onSearchChange = (e) => {
    const searchText = e.target.value;
    this.setState({searchText, selectedIndex: -1}, () => {
      this.filterObjects(searchText);
    });
  };

  filterObjects(searchText) {
    const objects = Array.isArray(this.state.objects) ? this.state.objects : [];
    const lowerSearch = searchText.toLowerCase();

    if (!lowerSearch) {
      this.setState({filteredObjects: objects});
      return;
    }

    const filtered = objects.filter(
      (obj) =>
        obj.label.toLowerCase().includes(lowerSearch) ||
        obj.apiName.toLowerCase().includes(lowerSearch)
    );

    filtered.sort((a, b) => {
      const aLabel = a.label.toLowerCase();
      const bLabel = b.label.toLowerCase();
      const aApi = a.apiName.toLowerCase();
      const bApi = b.apiName.toLowerCase();

      // 1. Exact match
      const aExact = aLabel === lowerSearch || aApi === lowerSearch;
      const bExact = bLabel === lowerSearch || bApi === lowerSearch;
      if (aExact && !bExact) return -1;
      if (!aExact && bExact) return 1;

      // 2. Starts with search text
      const aStarts = aLabel.startsWith(lowerSearch) || aApi.startsWith(lowerSearch);
      const bStarts = bLabel.startsWith(lowerSearch) || bApi.startsWith(lowerSearch);
      if (aStarts && !bStarts) return -1;
      if (!aStarts && bStarts) return 1;

      // 3. Alphabetical fallback
      return aLabel.localeCompare(bLabel);
    });

    this.setState({filteredObjects: filtered});
  }

  onKeyDown = (e) => {
    e.stopPropagation();
    const {selectedIndex, filteredObjects} = this.state;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const newIndex = Math.min(selectedIndex + 1, filteredObjects.length - 1);
      this.setState({selectedIndex: newIndex});
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const newIndex = Math.max(selectedIndex - 1, -1);
      this.setState({selectedIndex: newIndex});
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      this.selectObject(filteredObjects[selectedIndex]);
    }
  };

  selectObject = (obj) => {
    if (!obj) return;

    const {sfHost} = this.props;
    const baseUrl = "https://" + sfHost;

    const url =
      baseUrl +
      "/lightning/setup/ObjectManager/" +
      encodeURIComponent(obj.apiName) +
      "/FieldsAndRelationships/view";

    chrome.tabs.create({url});

    this.setState((prevState) => ({
      searchText: "",
      selectedIndex: -1,
      filteredObjects: prevState.objects,
    }));
  };

  render() {
    const h = React.createElement;
    const {searchText, filteredObjects, isLoading, error, selectedIndex} = this.state;
    const safeFilteredObjects = Array.isArray(filteredObjects) ? filteredObjects : [];

    return h(
      "div",
      {className: "schema-explorer-container tab-container slds-p-horizontal_x-small"},
      h(
        "div",
        {className: "schema-explorer-search slds-m-vertical_small"},
        h("input", {
          type: "text",
          placeholder: "Search objects by name or label...",
          value: searchText,
          onChange: this.onSearchChange,
          onKeyDown: this.onKeyDown,
          className: "slds-input schema-explorer-input",
          autoFocus: true,
        })
      ),
      error
        ? h(
            "div",
            {className: "slds-notify slds-notify_alert slds-alert_error slds-m-vertical_small"},
            h("span", {}, error)
          )
        : null,
      isLoading
        ? h(
            "div",
            {className: "slds-m-vertical_medium slds-text-align_center"},
            h("span", {className: "slds-spinner_container slds-spinner_container--small"}, "Loading...")
          )
        : h(
            "div",
            {className: "schema-explorer-list"},
            safeFilteredObjects.length === 0
              ? h(
                  "div",
                  {className: "slds-text-align_center slds-m-vertical_medium slds-text-color_weak"},
                  searchText
                    ? "No objects found matching your search"
                    : "No objects available"
                )
              : safeFilteredObjects.map((obj, index) =>
                  h(
                    "div",
                    {
                      key: obj.apiName,
                      className:
                        "schema-explorer-item " +
                        (index === selectedIndex ? "schema-explorer-item--selected" : ""),
                      onClick: () => this.selectObject(obj),
                    },
                    h(
                      "div",
                      {className: "schema-explorer-item-label"},
                      obj.label
                    ),
                    h(
                      "div",
                      {className: "schema-explorer-item-api"},
                      obj.apiName
                    )
                  )
                )
          )
    );
  }
}

export default AllDataBoxSchemaExplorer;
