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
      fieldResults: [],
      selectedIndex: -1,
      selectedFieldKey: null,
      selectedField: null,
      fieldDependencies: {dependsOn: [], referencedBy: []},
      isLoading: false,
      isLoadingFields: false,
      isLoadingDependencies: false,
      fieldSearchError: null,
      activeView: "objects",
    };

    this.fieldSearchTimer = null;
  }

  componentDidMount() {
    this.loadSchemaObjects();
  }

  componentWillUnmount() {
    if (this.fieldSearchTimer) {
      clearTimeout(this.fieldSearchTimer);
    }
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
    this.setState(
      {
        searchText,
        selectedIndex: -1,
        selectedFieldKey: null,
        selectedField: null,
        fieldDependencies: {dependsOn: [], referencedBy: []},
      },
      () => {
        this.filterObjects(searchText);
        this.loadFieldResults(searchText);
      }
    );
  };

  switchView = (view) => {
    this.setState({activeView: view});
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

      const aExact = aLabel === lowerSearch || aApi === lowerSearch;
      const bExact = bLabel === lowerSearch || bApi === lowerSearch;
      if (aExact && !bExact) return -1;
      if (!aExact && bExact) return 1;

      const aStarts = aLabel.startsWith(lowerSearch) || aApi.startsWith(lowerSearch);
      const bStarts = bLabel.startsWith(lowerSearch) || bApi.startsWith(lowerSearch);
      if (aStarts && !bStarts) return -1;
      if (!aStarts && bStarts) return 1;

      return aLabel.localeCompare(bLabel);
    });

    this.setState({filteredObjects: filtered});
  }

  getObjectMatches(searchText) {
    const objects = Array.isArray(this.state.objects) ? this.state.objects : [];
    const lowerSearch = String(searchText || "").toLowerCase();

    if (!lowerSearch) {
      return objects;
    }

    return objects.filter(
      (obj) =>
        obj.label.toLowerCase().includes(lowerSearch) ||
        obj.apiName.toLowerCase().includes(lowerSearch)
    );
  }

  loadFieldResults(searchText) {
    if (this.fieldSearchTimer) {
      clearTimeout(this.fieldSearchTimer);
    }

    this.fieldSearchTimer = setTimeout(async () => {
      const normalized = String(searchText || "").trim();
      if (normalized.length < 2) {
        this.setState({fieldResults: [], isLoadingFields: false, fieldSearchError: null});
        return;
      }

      this.setState({isLoadingFields: true, fieldSearchError: null});

      try {
        const results = await this.fetchFieldResultsFromAPI(normalized);
        const objectMatches = this.getObjectMatches(normalized);
        const shouldSwitchToFields = objectMatches.length === 0 && results.length > 0;

        if (results.length === 0) {
          console.debug(`Field search for '${normalized}' returned 0 results`);
        }

        this.setState((prevState) => ({
          fieldResults: results,
          isLoadingFields: false,
          activeView: shouldSwitchToFields ? "fields" : prevState.activeView,
        }));
      } catch (err) {
        console.error("Error fetching field search results:", err);
        this.setState({fieldResults: [], isLoadingFields: false, fieldSearchError: err.message || "Field search failed"});
      }
    }, 300);
  }

  async fetchFieldResultsFromAPI(searchText) {
    const escapedSearch = searchText.replace(/([\\%_'])/g, "\\$1");
    
    // We must query FieldDefinition to get standard fields.
    // However, FieldDefinition requires filtering by EntityDefinitionId.
    // So we chunk all known objects and query them concurrently.
    const allObjects = Array.isArray(this.state.objects) ? this.state.objects.map(o => o.apiName) : [];
    if (allObjects.length === 0) return [];

    // Filter out some notoriously problematic system objects that cause query errors
    const safeObjects = allObjects.filter(apiName => !apiName.endsWith('ChangeEvent') && !apiName.endsWith('Share') && !apiName.endsWith('History'));

    const chunks = [];
    for (let i = 0; i < safeObjects.length; i += 100) {
      chunks.push(safeObjects.slice(i, i + 100));
    }

    const promises = chunks.map(chunk => {
      // Disjunctions (OR) are not supported on FieldDefinition. We strictly search by Label as requested.
      const query = `SELECT DurableId, QualifiedApiName, Label, DataType, EntityDefinition.QualifiedApiName, EntityDefinition.MasterLabel FROM FieldDefinition WHERE Label LIKE '%${escapedSearch}%' AND EntityDefinition.QualifiedApiName IN ('${chunk.join("','")}') LIMIT 200`;
      return sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(query)).catch(e => {
        console.warn("Field chunk query failed", e);
        return { records: [] };
      });
    });

    const results = await Promise.all(promises);
    const groups = new Map();

    for (const result of results) {
      if (!result || !Array.isArray(result.records)) continue;

      for (const record of result.records) {
        const label = record.Label || record.QualifiedApiName || "";
        if (!label) continue;
        
        const apiName = record.QualifiedApiName;
        const objectName = record.EntityDefinition?.QualifiedApiName || "Unknown";
        const objectLabel = record.EntityDefinition?.MasterLabel || objectName;
        const durableId = record.DurableId || null;
        
        // Group by Label instead of API Name, as requested
        const groupKey = label.toLowerCase();

        if (!groups.has(groupKey)) {
          groups.set(groupKey, {
            key: groupKey,
            apiName: apiName, // store the first API name found as a reference
            label: label,
            dataType: record.DataType || "Field",
            objects: new Map(),
            records: [],
          });
        }

        const group = groups.get(groupKey);
        group.records.push({
          durableId,
          apiName,
          label,
          objectName,
          objectLabel,
          dataType: record.DataType,
        });
        
        if (!group.objects.has(objectName)) {
          group.objects.set(objectName, {apiName: objectName, label: objectLabel});
        }
      }
    }

    const groupsArray = Array.from(groups.values()).map((group) => ({
      ...group,
      objects: Array.from(group.objects.values()),
      objectCount: group.objects.size,
      apiNames: Array.from(new Set(group.records.map(r => r.apiName))),
      // Pass all records so we can resolve their IDs later
      records: group.records,
    }));

    groupsArray.sort((a, b) => a.label.localeCompare(b.label));
    return groupsArray;
  }

  async loadFieldDependencies(fieldGroup) {
    if (!fieldGroup || !Array.isArray(fieldGroup.records) || fieldGroup.records.length === 0) {
      this.setState({fieldDependencies: {dependsOn: [], referencedBy: []}, isLoadingDependencies: false});
      return;
    }

    this.setState({isLoadingDependencies: true, fieldDependencies: {dependsOn: [], referencedBy: []}});
    
    try {
      // Salesforce MetadataComponentDependency requires the 18-char ID for Custom Fields.
      // FieldDefinition only gives us the DurableId (ObjectName.FieldApiName). 
      // So we must first lookup the CustomField IDs before we can query dependencies.
      const customFieldRecords = fieldGroup.records.filter(r => r.apiName.endsWith('__c'));
      let validDependencyIds = [];

      if (customFieldRecords.length > 0) {
        // Build DevNames from apiNames (e.g. "Namespace__Field__c" -> "Field" or "Namespace__Field")
        const devNames = customFieldRecords.map(r => {
          let name = r.apiName.replace(/__c$/, '');
          return name.includes('__') ? name.split('__')[1] : name;
        });
        
        // Chunk custom field lookups to avoid URI limits
        for (let i = 0; i < devNames.length; i += 50) {
          const chunk = devNames.slice(i, i + 50);
          const devNameList = Array.from(new Set(chunk)).map(n => `'${n}'`).join(',');
          const cfQuery = `SELECT Id FROM CustomField WHERE DeveloperName IN (${devNameList})`;
          const cfResult = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(cfQuery)).catch(() => ({records: []}));
          
          if (cfResult && cfResult.records) {
            validDependencyIds.push(...cfResult.records.map(r => r.Id));
          }
        }
      }

      // Note: Standard fields do not have tracked dependencies in MetadataComponentDependency.
      if (validDependencyIds.length === 0) {
        this.setState({fieldDependencies: {dependsOn: [], referencedBy: []}, isLoadingDependencies: false});
        return;
      }

      // Eliminate duplicates
      validDependencyIds = Array.from(new Set(validDependencyIds));

      const dependsOnPromises = validDependencyIds.map(id => {
        const query = `SELECT MetadataComponentId, MetadataComponentName, MetadataComponentType, RefMetadataComponentId, RefMetadataComponentName, RefMetadataComponentType, RefMetadataComponentNamespace FROM MetadataComponentDependency WHERE MetadataComponentId = '${id}' ORDER BY MetadataComponentType, RefMetadataComponentType, MetadataComponentName LIMIT 1000`;
        return sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(query)).catch(e => {
          console.warn(`dependsOn query failed for ${id}`, e);
          return { records: [] };
        });
      });

      const referencedByPromises = validDependencyIds.map(id => {
        const query = `SELECT MetadataComponentId, MetadataComponentName, MetadataComponentType, RefMetadataComponentId, RefMetadataComponentName, RefMetadataComponentType, RefMetadataComponentNamespace FROM MetadataComponentDependency WHERE RefMetadataComponentId = '${id}' ORDER BY MetadataComponentType, RefMetadataComponentType, MetadataComponentName LIMIT 1000`;
        return sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(query)).catch(e => {
          console.warn(`referencedBy query failed for ${id}`, e);
          return { records: [] };
        });
      });

      const dependsOnResults = await Promise.all(dependsOnPromises);
      const referencedByResults = await Promise.all(referencedByPromises);

      const dependsOnMap = new Map();
      const referencedByMap = new Map();

      for (const result of dependsOnResults) {
        if (result && Array.isArray(result.records)) {
          for (const row of result.records) {
            const key = `${row.MetadataComponentId}|${row.RefMetadataComponentId}|${row.MetadataComponentType}|${row.RefMetadataComponentType}`;
            if (!dependsOnMap.has(key)) {
              dependsOnMap.set(key, {
                id: row.RefMetadataComponentId,
                name: row.RefMetadataComponentName,
                type: row.RefMetadataComponentType,
                namespace: row.RefMetadataComponentNamespace,
              });
            }
          }
        }
      }

      for (const result of referencedByResults) {
        if (result && Array.isArray(result.records)) {
          for (const row of result.records) {
            const key = `${row.MetadataComponentId}|${row.RefMetadataComponentId}|${row.MetadataComponentType}|${row.RefMetadataComponentType}`;
            if (!referencedByMap.has(key)) {
              referencedByMap.set(key, {
                id: row.MetadataComponentId,
                name: row.MetadataComponentName,
                type: row.MetadataComponentType,
                namespace: row.MetadataComponentNamespace,
              });
            }
          }
        }
      }

      this.setState({
        fieldDependencies: {
          dependsOn: Array.from(dependsOnMap.values()),
          referencedBy: Array.from(referencedByMap.values()),
        },
        isLoadingDependencies: false,
      });
    } catch (err) {
      console.error("Error fetching field dependencies:", err);
      this.setState({fieldDependencies: {dependsOn: [], referencedBy: []}, isLoadingDependencies: false});
    }
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

  selectField = (fieldGroup) => {
    if (!fieldGroup) {
      return;
    }

    this.setState(
      {
        selectedFieldKey: fieldGroup.key,
        selectedField: fieldGroup,
      },
      () => this.loadFieldDependencies(fieldGroup)
    );
  };

  openFieldInSetup = (fieldGroup) => {
    if (!fieldGroup || !Array.isArray(fieldGroup.records) || fieldGroup.records.length === 0) {
      return;
    }
    const record = fieldGroup.records[0];
    const objectName = record.objectName;
    if (!objectName) {
      return;
    }

    const {sfHost} = this.props;
    const baseUrl = "https://" + sfHost;
    const url =
      baseUrl +
      "/lightning/setup/ObjectManager/" +
      encodeURIComponent(objectName) +
      "/FieldsAndRelationships/view";

    chrome.tabs.create({url});
  };

  backToFields = () => {
    this.setState({
      selectedFieldKey: null,
      selectedField: null,
    });
  };

  renderObjectsView() {
    const {filteredObjects, selectedIndex, isLoading, fieldResults, searchText} = this.state;
    const safeFilteredObjects = Array.isArray(filteredObjects) ? filteredObjects : [];
    const showFieldHint = !isLoading && searchText && searchText.trim().length >= 2 && Array.isArray(fieldResults) && fieldResults.length > 0;

    if (isLoading) {
      return React.createElement(
        "div",
        {className: "slds-m-vertical_medium slds-text-align_center"},
        React.createElement("span", {className: "slds-spinner_container slds-spinner_container--small"}, "Loading objects...")
      );
    }

    if (safeFilteredObjects.length === 0) {
      return React.createElement(
        "div",
        {className: "schema-explorer-empty-state slds-text-align_center slds-m-vertical_medium slds-text-color_weak"},
        "No objects found matching your search"
      );
    }

    return React.createElement(
      "div",
      {className: "schema-explorer-objects-view"},
      React.createElement(
        "div",
        {className: "schema-explorer-list"},
        safeFilteredObjects.map((obj, index) =>
          React.createElement(
            "div",
            {
              key: obj.apiName,
              className:
                "schema-explorer-item " +
                (index === selectedIndex ? "schema-explorer-item--selected" : ""),
              onClick: () => this.selectObject(obj),
            },
            React.createElement("div", {className: "schema-explorer-item-label"}, obj.label),
            React.createElement("div", {className: "schema-explorer-item-api"}, obj.apiName),
            React.createElement("span", {className: "schema-explorer-item-type"}, obj.type)
          )
        )
      )
    );
  }

  renderFieldsView() {
    const {fieldResults, selectedFieldKey, selectedField, isLoadingFields, searchText, fieldSearchError} = this.state;
    const safeFieldResults = Array.isArray(fieldResults) ? fieldResults : [];

    if (selectedField) {
      return React.createElement(
        "div",
        {className: "schema-explorer-fields-view"},
        this.renderFieldDetails(selectedField)
      );
    }

    return React.createElement(
      "div",
      {className: "schema-explorer-fields-view"},
      fieldSearchError
        ? React.createElement(
            "div",
            {className: "schema-explorer-field-search-error slds-notify slds-notify_alert slds-alert_error slds-m-bottom_small"},
            React.createElement("span", {}, `Field search error: ${fieldSearchError}`)
          )
        : null,
      React.createElement(
        "div",
        {className: "schema-explorer-fields-list"},
        isLoadingFields
          ? React.createElement(
              "div",
              {className: "schema-explorer-empty-state slds-text-align_center slds-m-vertical_medium slds-text-color_weak"},
              "Searching fields..."
            )
          : safeFieldResults.length === 0
          ? React.createElement(
              "div",
              {className: "schema-explorer-empty-state slds-text-align_center slds-m-vertical_medium slds-text-color_weak"},
              searchText && searchText.trim().length >= 2
                ? "No fields found matching your search"
                : "Enter 2+ characters to search fields"
            )
          : safeFieldResults.map((fieldGroup, index) =>
              React.createElement(
                "div",
                {
                  key: fieldGroup.key,
                  className: "schema-explorer-field-item",
                  onClick: () => this.selectField(fieldGroup),
                },
                React.createElement("div", {className: "schema-explorer-field-name"}, fieldGroup.label),
                React.createElement(
                  "div",
                  {className: "schema-explorer-field-label"},
                  `${fieldGroup.apiNames.length === 1 ? fieldGroup.apiNames[0] : fieldGroup.apiNames.join(", ")} • ${fieldGroup.objectCount} ${fieldGroup.objectCount === 1 ? "object" : "objects"}`
                ),
                React.createElement("span", {className: "schema-explorer-field-type"}, fieldGroup.dataType || "CustomField")
              )
            )
      )
    );
  }

  renderFieldDetails(fieldGroup) {
    const {fieldDependencies, isLoadingDependencies} = this.state;
    return React.createElement(
      "div",
      {className: "schema-explorer-field-details"},
      React.createElement(
        "div",
        {className: "schema-explorer-details-header"},
        React.createElement(
          "div",
          {className: "schema-explorer-details-header-left"},
          React.createElement(
            "button",
            {
              type: "button",
              className: "schema-explorer-back-btn slds-button slds-button_icon slds-button_icon-border slds-m-right_small",
              onClick: this.backToFields,
              title: "Back to fields list",
            },
            "←"
          ),
          React.createElement(
            "div",
            null,
            React.createElement("h3", null, fieldGroup.label),
            React.createElement(
              "div",
              {className: "schema-explorer-detail-label", style: {textTransform: "none", letterSpacing: "normal"}},
              fieldGroup.apiNames.length === 1 ? fieldGroup.apiNames[0] : `API Names: ${fieldGroup.apiNames.join(", ")}`
            )
          )
        ),
        React.createElement(
          "button",
          {
            type: "button",
            className: "schema-explorer-details-close",
            onClick: () => this.openFieldInSetup(fieldGroup),
            title: "Open object field setup in Salesforce",
          },
          "Open Setup"
        )
      ),
      React.createElement(
        "div",
        {className: "schema-explorer-details-content"},
        React.createElement(
          "div",
          {className: "schema-explorer-detail-section"},
          React.createElement("div", {className: "schema-explorer-detail-label"}, "Field details"),
          React.createElement("div", {className: "schema-explorer-detail-value"}, `Field Label: ${fieldGroup.label}`),
          React.createElement("div", {className: "schema-explorer-detail-value"}, `API Name(s): ${fieldGroup.apiNames.join(", ")}`),
          React.createElement("div", {className: "schema-explorer-detail-value"}, `Type: ${fieldGroup.dataType || "Unknown"}`),
          React.createElement("div", {className: "schema-explorer-detail-value"}, `Objects: ${fieldGroup.objectCount}`)
        ),
        React.createElement(
          "div",
          {className: "schema-explorer-detail-section"},
          React.createElement("div", {className: "schema-explorer-detail-label"}, "Objects containing this field"),
          React.createElement(
            "div",
            {className: "schema-explorer-objects-list"},
            fieldGroup.objects.map((object) =>
              React.createElement(
                "div",
                {key: object.apiName, className: "schema-explorer-object-badge"},
                React.createElement("div", {className: "schema-explorer-object-name"}, object.apiName),
                React.createElement("div", {className: "schema-explorer-object-label"}, object.label)
              )
            )
          )
        ),
        React.createElement(
          "div",
          {className: "schema-explorer-detail-section"},
          React.createElement("div", {className: "schema-explorer-detail-label"}, "Dependencies"),
          isLoadingDependencies
            ? React.createElement("div", {className: "schema-explorer-empty-state slds-text-align_center"}, "Loading dependencies...")
            : React.createElement(
                React.Fragment,
                null,
                React.createElement(
                  "div",
                  {className: "schema-explorer-references-list"},
                  React.createElement("div", {className: "schema-explorer-detail-value"}, "Field depends on:"),
                  fieldDependencies.dependsOn.length === 0
                    ? React.createElement("div", {className: "schema-explorer-reference-item"}, "No upstream dependencies found")
                    : fieldDependencies.dependsOn.map((dep, index) =>
                        React.createElement(
                          "div",
                          {key: `${dep.type}-${dep.id}-${index}`, className: "schema-explorer-reference-item"},
                          `${dep.type}: ${dep.name}${dep.namespace ? ` (${dep.namespace})` : ""}`
                        )
                      )
                ),
                React.createElement(
                  "div",
                  {className: "schema-explorer-references-list"},
                  React.createElement("div", {className: "schema-explorer-detail-value"}, "Referenced by:"),
                  fieldDependencies.referencedBy.length === 0
                    ? React.createElement("div", {className: "schema-explorer-reference-item"}, "No downstream references found")
                    : fieldDependencies.referencedBy.map((dep, index) =>
                        React.createElement(
                          "div",
                          {key: `${dep.type}-${dep.id}-${index}`, className: "schema-explorer-reference-item"},
                          `${dep.type}: ${dep.name}${dep.namespace ? ` (${dep.namespace})` : ""}`
                        )
                      )
                )
              )
        )
      )
    );
  }

  render() {
    const h = React.createElement;
    const {searchText, error, activeView, filteredObjects, fieldResults} = this.state;
    const objectCount = Array.isArray(filteredObjects) ? filteredObjects.length : 0;
    const fieldCount = Array.isArray(fieldResults) ? fieldResults.length : 0;

    return h(
      "div",
      {className: "schema-explorer-container slds-p-horizontal_x-small"},
      h(
        "div",
        {className: "schema-explorer-search slds-m-vertical_small"},
        h("input", {
          type: "text",
          placeholder: "Search objects and fields...",
          value: searchText,
          onChange: this.onSearchChange,
          onKeyDown: this.onKeyDown,
          className: "slds-input schema-explorer-input",
          autoFocus: true,
        })
      ),
      h(
        "div",
        {className: "schema-explorer-segmented-control"},
        h(
          "div",
          {
            className: `schema-explorer-segment ${activeView === "objects" ? "schema-explorer-segment--active" : ""}`,
            onClick: () => this.switchView("objects"),
          },
          `Objects (${objectCount})`
        ),
        h(
          "div",
          {
            className: `schema-explorer-segment ${activeView === "fields" ? "schema-explorer-segment--active" : ""}`,
            onClick: () => this.switchView("fields"),
          },
          `Fields (${fieldCount})`
        )
      ),
      error
        ? h(
            "div",
            {className: "slds-notify slds-notify_alert slds-alert_error slds-m-vertical_small"},
            h("span", {}, error)
          )
        : null,
      h(
        "div",
        {className: "schema-explorer-content"},
        activeView === "objects" ? this.renderObjectsView() : this.renderFieldsView()
      )
    );
  }
}

export default AllDataBoxSchemaExplorer;
