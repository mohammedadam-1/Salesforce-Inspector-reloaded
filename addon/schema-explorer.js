/* global React */
/* eslint-disable react/prop-types */
import { sfConn, apiVersion } from "./inspector.js";
import { DataCache } from "./utils.js";

const SCHEMA_CACHE_KEY = "SCHEMA_OBJECTS_LIST_V7";

class AllDataBoxSchemaExplorer extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      searchText: "",
      objects: [],
      filteredObjects: [],
      fieldResults: [],
      selectedIndex: -1,
      selectedField: null,
      fieldDependencies: { dependsOn: [], referencedBy: [] },
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
    this.setState({ isLoading: true, error: null });

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
          if (!sobject.custom && !sobject.layoutable && !sobject.customSetting) {
            continue; // Filter out system objects (not in Object Manager)
          }

          let type = "Standard Object";
          if (sobject.custom) {
            if (sobject.customSetting) type = "Custom Setting";
            else if (sobject.name.endsWith("__mdt")) type = "Custom Metadata Type";
            else if (sobject.name.endsWith("__e")) type = "Platform Event";
            else if (sobject.name.endsWith("__b")) type = "Big Object";
            else if (sobject.name.endsWith("__x")) type = "External Object";
            else type = "Custom Object";
          }

          objectsMap.set(sobject.name, {
            apiName: sobject.name,
            label: sobject.label || sobject.name,
            type: type,
            durableId: sobject.name,
            isCustomSetting: sobject.customSetting || false,
          });
        }
      }

      try {
        const allApiNames = Array.from(objectsMap.keys());
        const chunks = [];
        for (let i = 0; i < allApiNames.length; i += 100) {
          chunks.push(allApiNames.slice(i, i + 100));
        }

        const entityQueries = chunks.map(chunk => {
          const query = `SELECT QualifiedApiName, Label, DurableId, IsCustomSetting, IsCustomizable FROM EntityDefinition WHERE QualifiedApiName IN ('${chunk.join("','")}')`;
          return sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(query)).catch(err => {
            console.warn("EntityDefinition chunk query failed", err);
            return null;
          });
        });

        const results = await Promise.all(entityQueries);
        const processedApiNames = new Set();

        for (const result of results) {
          if (result && result.records) {
            for (const record of result.records) {
              const apiName = record.QualifiedApiName;
              processedApiNames.add(apiName);
              
              if (objectsMap.has(apiName)) {
                objectsMap.get(apiName).label = record.Label || apiName;
                objectsMap.get(apiName).durableId = record.DurableId || apiName;
                objectsMap.get(apiName).isCustomSetting = Boolean(record.IsCustomSetting);
                objectsMap.get(apiName).isCustomizable = Boolean(record.IsCustomizable);
              }
            }
          }
        }

        // Final filtering: Remove standard objects that are NOT customizable (like BusinessHours, WorkTypeGroup)
        for (const apiName of allApiNames) {
          const obj = objectsMap.get(apiName);
          if (obj && !obj.custom && !obj.isCustomSetting) {
            // If it was processed by Tooling API and is NOT customizable, delete it.
            // If it wasn't processed at all by EntityDefinition, it also means it's an internal system object.
            if (!processedApiNames.has(apiName) || obj.isCustomizable === false) {
              objectsMap.delete(apiName);
            }
          }
        }
      } catch (toolingErr) {
        console.warn("EntityDefinition queries failed, using basic info only:", toolingErr);
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
        selectedField: null,
        fieldDependencies: { dependsOn: [], referencedBy: [] },
      },
      () => {
        this.filterObjects(searchText);
        this.loadFieldResults(searchText);
      }
    );
  };

  switchView = (view) => {
    this.setState({ activeView: view });
  };

  filterObjects(searchText) {
    const objects = Array.isArray(this.state.objects) ? this.state.objects : [];
    const lowerSearch = searchText.toLowerCase();

    if (!lowerSearch) {
      this.setState({ filteredObjects: objects });
      return;
    }

    const filtered = objects.filter(
      (obj) =>
        obj.label.toLowerCase().includes(lowerSearch)
        || obj.apiName.toLowerCase().includes(lowerSearch)
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

    this.setState({ filteredObjects: filtered });
  }

  getObjectMatches(searchText) {
    const objects = Array.isArray(this.state.objects) ? this.state.objects : [];
    const lowerSearch = String(searchText || "").toLowerCase();

    if (!lowerSearch) {
      return objects;
    }

    return objects.filter(
      (obj) =>
        obj.label.toLowerCase().includes(lowerSearch)
        || obj.apiName.toLowerCase().includes(lowerSearch)
    );
  }

  loadFieldResults(searchText) {
    if (this.fieldSearchTimer) {
      clearTimeout(this.fieldSearchTimer);
    }

    this.fieldSearchTimer = setTimeout(async () => {
      const normalized = String(searchText || "").trim();
      if (normalized.length < 2) {
        this.setState({ fieldResults: [], isLoadingFields: false, fieldSearchError: null });
        return;
      }

      this.setState({ isLoadingFields: true, fieldSearchError: null });

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
        this.setState({ fieldResults: [], isLoadingFields: false, fieldSearchError: err.message || "Field search failed" });
      }
    }, 300);
  }

  escapeSoqlLike(value) {
    return String(value || "").replace(/([\\%_'])/g, "\\$1");
  }

  escapeSoqlString(value) {
    return String(value || "").replace(/([\\'])/g, "\\$1");
  }

  async queryFieldDefinitions(query, source) {
    try {
      const result = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(query));
      return { source, records: Array.isArray(result?.records) ? result.records : [] };
    } catch (e) {
      console.warn("Field chunk query failed", e);
      return { source, records: [] };
    }
  }

  addFieldRecordToGroups(groups, record) {
    const label = record.Label || record.QualifiedApiName || "";
    if (!label) return null;

    const apiName = record.QualifiedApiName;
    const objectName = record.EntityDefinition?.QualifiedApiName || "Unknown";
    const objectLabel = record.EntityDefinition?.MasterLabel || objectName;
    const durableId = record.DurableId || null;
    const entityDurableId = record.EntityDefinition?.DurableId || objectName;
    const isCustomSetting = Boolean(record.EntityDefinition?.IsCustomSetting);

    // Group by Label instead of API Name, as requested.
    const groupKey = label.toLowerCase();

    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        key: groupKey,
        apiName, // store the first API name found as a reference
        label,
        dataType: record.DataType || "Field",
        objects: new Map(),
        records: [],
      });
    }

    const group = groups.get(groupKey);
    const groupRecord = {
      durableId,
      entityDurableId,
      apiName,
      label,
      objectName,
      objectLabel,
      dataType: record.DataType,
      isCustomSetting,
    };

    const recordKey = `${objectName}.${apiName}.${durableId || ""}`;
    const recordExists = group.records.some(existing =>
      `${existing.objectName}.${existing.apiName}.${existing.durableId || ""}` === recordKey
    );
    if (!recordExists) {
      group.records.push(groupRecord);
    }

    if (!group.objects.has(objectName)) {
      group.objects.set(objectName, { apiName: objectName, label: objectLabel, record: groupRecord });
    }

    return label;
  }

  buildFieldGroups(groups) {
    const groupsArray = Array.from(groups.values()).map((group) => ({
      ...group,
      objects: Array.from(group.objects.values()),
      objectCount: group.objects.size,
      apiNames: Array.from(new Set(group.records.map(r => r.apiName).filter(Boolean))),
      // Pass all records so we can resolve their IDs later
      records: group.records,
    }));

    groupsArray.sort((a, b) => a.label.localeCompare(b.label));
    return groupsArray;
  }

  fetchFieldsByExactLabels(labels, objectChunks, fieldSelect) {
    const promises = labels.flatMap(label =>
      objectChunks.map(chunk => {
        const objectFilter = `EntityDefinition.QualifiedApiName IN ('${chunk.join("','")}')`;
        const labelFilter = `Label = '${this.escapeSoqlString(label)}'`;
        const query = `${fieldSelect} WHERE ${labelFilter} AND ${objectFilter} LIMIT 2000`;
        return this.queryFieldDefinitions(query, "labelExpansion");
      })
    );

    return Promise.all(promises);
  }

  async fetchFieldResultsFromAPI(searchText) {
    const escapedSearch = this.escapeSoqlLike(searchText);

    // We must query FieldDefinition to get standard fields.
    // However, FieldDefinition requires filtering by EntityDefinitionId.
    // So we chunk all known objects and query them concurrently.
    const allObjects = Array.isArray(this.state.objects) ? this.state.objects.map(o => o.apiName) : [];
    if (allObjects.length === 0) return [];

    // Filter out some notoriously problematic system objects that cause query errors
    const safeObjects = allObjects.filter(apiName => !apiName.endsWith("ChangeEvent") && !apiName.endsWith("Share") && !apiName.endsWith("History"));

    const chunks = [];
    for (let i = 0; i < safeObjects.length; i += 100) {
      chunks.push(safeObjects.slice(i, i + 100));
    }

    const fieldSelect
      = "SELECT DurableId, QualifiedApiName, Label, DataType, "
      + "EntityDefinition.QualifiedApiName, EntityDefinition.MasterLabel, "
      + "EntityDefinition.DurableId, EntityDefinition.IsCustomSetting FROM FieldDefinition";

    const searchQueries = chunks.flatMap(chunk => {
      const objectFilter = `EntityDefinition.QualifiedApiName IN ('${chunk.join("','")}')`;
      const labelQuery = `${fieldSelect} WHERE Label LIKE '%${escapedSearch}%' AND ${objectFilter} LIMIT 200`;
      const apiNameQuery = `${fieldSelect} WHERE QualifiedApiName LIKE '%${escapedSearch}%' AND ${objectFilter} LIMIT 200`;

      return [
        { query: labelQuery, source: "label" },
        { query: apiNameQuery, source: "apiName" },
      ];
    });

    const results = await Promise.all(
      searchQueries.map(({ query, source }) => this.queryFieldDefinitions(query, source))
    );
    const groups = new Map();
    const apiMatchLabels = new Set();

    for (const result of results) {
      if (!result || !Array.isArray(result.records)) continue;

      for (const record of result.records) {
        const label = this.addFieldRecordToGroups(groups, record);
        if (result.source === "apiName" && label) {
          apiMatchLabels.add(label);
        }
      }
    }

    const lowerSearch = String(searchText || "").toLowerCase();
    const labelsToExpand = Array.from(apiMatchLabels)
      .filter(label => !label.toLowerCase().includes(lowerSearch));

    if (labelsToExpand.length > 0 && labelsToExpand.length <= 20) {
      const labelExpansionResults = await this.fetchFieldsByExactLabels(labelsToExpand, chunks, fieldSelect);
      for (const result of labelExpansionResults) {
        if (!result || !Array.isArray(result.records)) continue;

        for (const record of result.records) {
          this.addFieldRecordToGroups(groups, record);
        }
      }
    }

    return this.buildFieldGroups(groups);
  }

  async loadFieldDependencies(fieldGroup) {
    if (!fieldGroup || !Array.isArray(fieldGroup.records) || fieldGroup.records.length === 0) {
      this.setState({ fieldDependencies: { dependsOn: [], referencedBy: [] }, isLoadingDependencies: false });
      return;
    }

    this.setState({ isLoadingDependencies: true, fieldDependencies: { dependsOn: [], referencedBy: [] } });

    try {
      // Salesforce MetadataComponentDependency requires the 18-char ID for Custom Fields.
      // FieldDefinition only gives us the DurableId (ObjectName.FieldApiName).
      // So we must first lookup the CustomField IDs before we can query dependencies.
      const customFieldRecords = fieldGroup.records.filter(r => String(r.apiName || "").endsWith("__c"));
      let validDependencyIds = [];

      if (customFieldRecords.length > 0) {
        // Build DevNames from apiNames (e.g. "Namespace__Field__c" -> "Field" or "Namespace__Field")
        const devNames = customFieldRecords.map(r => {
          let name = r.apiName.replace(/__c$/, "");
          return name.includes("__") ? name.split("__")[1] : name;
        });

        // Chunk custom field lookups to avoid URI limits
        for (let i = 0; i < devNames.length; i += 50) {
          const chunk = devNames.slice(i, i + 50);
          const devNameList = Array.from(new Set(chunk)).map(n => `'${n}'`).join(",");
          const cfQuery = `SELECT Id FROM CustomField WHERE DeveloperName IN (${devNameList})`;
          const cfResult = await sfConn.rest("/services/data/v" + apiVersion + "/tooling/query?q=" + encodeURIComponent(cfQuery)).catch(() => ({ records: [] }));

          if (cfResult && cfResult.records) {
            validDependencyIds.push(...cfResult.records.map(r => r.Id));
          }
        }
      }

      // Note: Standard fields do not have tracked dependencies in MetadataComponentDependency.
      if (validDependencyIds.length === 0) {
        this.setState({ fieldDependencies: { dependsOn: [], referencedBy: [] }, isLoadingDependencies: false });
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
      this.setState({ fieldDependencies: { dependsOn: [], referencedBy: [] }, isLoadingDependencies: false });
    }
  }

  onKeyDown = (e) => {
    e.stopPropagation();
    const { selectedIndex, filteredObjects } = this.state;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const newIndex = Math.min(selectedIndex + 1, filteredObjects.length - 1);
      this.setState({ selectedIndex: newIndex });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const newIndex = Math.max(selectedIndex - 1, -1);
      this.setState({ selectedIndex: newIndex });
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      this.selectObject(filteredObjects[selectedIndex]);
    }
  };

  selectObject = (obj) => {
    if (!obj) return;

    const url = this.getObjectFieldsSetupUrl(obj);

    chrome.tabs.create({ url });

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

    const objects = Array.isArray(fieldGroup.objects)
      ? [...fieldGroup.objects].sort((a, b) =>
        (a.label || a.apiName).localeCompare(b.label || b.apiName)
      )
      : [];

    this.setState({
      selectedField: {
        ...fieldGroup,
        objects,
      },
      fieldDependencies: { dependsOn: [], referencedBy: [] },
    });
  };

  openFieldInSetup = (fieldGroup) => {
    if (!fieldGroup || !Array.isArray(fieldGroup.records) || fieldGroup.records.length === 0) {
      return;
    }
    this.openFieldRecordInSetup(fieldGroup.records[0]);
  };

  openFieldRecordInSetup = (record) => {
    const url = this.getFieldSetupUrl(record);
    if (!url) {
      return;
    }

    chrome.tabs.create({ url });
  };

  getMetadataSetupUrl(durableId, type) {
    const { sfHost } = this.props;
    const encodedAddress = encodeURIComponent(`/${durableId}?setupid=${type}`);
    return `https://${sfHost}/lightning/setup/${type}/page?address=${encodedAddress}`;
  }

  getObjectFieldsSetupUrl(obj) {
    const { sfHost } = this.props;
    const objectName = obj.apiName;
    const entityDurableId = obj.durableId || objectName;

    if (objectName.endsWith("__mdt")) {
      return this.getMetadataSetupUrl(entityDurableId, "CustomMetadata");
    }

    if (obj.isCustomSetting) {
      return this.getMetadataSetupUrl(entityDurableId, "CustomSettings");
    }

    const objectManagerId = objectName.endsWith("__c") || objectName.endsWith("__kav")
      ? entityDurableId
      : objectName;

    return `https://${sfHost}/lightning/setup/ObjectManager/${encodeURIComponent(objectManagerId)}/FieldsAndRelationships/view`;
  }

  getFieldSetupUrl(record) {
    if (!record || !record.objectName) {
      return null;
    }

    const { sfHost } = this.props;
    const durableParts = String(record.durableId || "").split(".").filter(Boolean);
    const entityDurableId = record.entityDurableId || durableParts[0] || record.objectName;
    const fieldDurableId = durableParts.length > 1 ? durableParts[durableParts.length - 1] : record.apiName;

    if (!fieldDurableId) {
      return `https://${sfHost}/lightning/setup/ObjectManager/${encodeURIComponent(entityDurableId)}/FieldsAndRelationships/view`;
    }

    if (record.objectName.endsWith("__mdt")) {
      return this.getMetadataSetupUrl(fieldDurableId, "CustomMetadata");
    }

    if (record.isCustomSetting) {
      return this.getMetadataSetupUrl(fieldDurableId, "CustomSettings");
    }

    return `https://${sfHost}/lightning/setup/ObjectManager/${encodeURIComponent(entityDurableId)}/FieldsAndRelationships/${encodeURIComponent(fieldDurableId)}/view`;
  }

  backToFields = () => {
    this.setState({
      selectedField: null,
    });
  };

  renderObjectsView() {
    const { filteredObjects, selectedIndex, isLoading } = this.state;
    const safeFilteredObjects = Array.isArray(filteredObjects) ? filteredObjects : [];

    if (isLoading) {
      return React.createElement(
        "div",
        { className: "slds-m-vertical_medium slds-text-align_center" },
        React.createElement("span", { className: "slds-spinner_container slds-spinner_container--small" }, "Loading objects...")
      );
    }

    if (safeFilteredObjects.length === 0) {
      return React.createElement(
        "div",
        { className: "schema-explorer-empty-state slds-text-align_center slds-m-vertical_medium slds-text-color_weak" },
        "No objects found matching your search"
      );
    }

    return React.createElement(
      "div",
      { className: "schema-explorer-objects-view" },
      React.createElement(
        "div",
        { className: "schema-explorer-list" },
        safeFilteredObjects.map((obj, index) =>
          React.createElement(
            "div",
            {
              key: obj.apiName,
              className:
                "schema-explorer-item "
                + (index === selectedIndex ? "schema-explorer-item--selected" : ""),
              onClick: () => this.selectObject(obj),
            },
            React.createElement("div", { className: "schema-explorer-item-label" }, obj.label),
            React.createElement("div", { className: "schema-explorer-item-api" }, obj.apiName),
            React.createElement("span", { className: "schema-explorer-item-type" }, obj.type)
          )
        )
      )
    );
  }

  renderFieldObjectsPanel(fieldGroup) {
    const objects = Array.isArray(fieldGroup.objects) ? fieldGroup.objects : [];

    return React.createElement(
      "div",
      { className: "schema-explorer-field-objects-panel" },
      React.createElement(
        "div",
        { className: "schema-explorer-field-objects-heading" },
        `${objects.length} ${objects.length === 1 ? "object" : "objects"} containing ${fieldGroup.label}`
      ),
      React.createElement(
        "div",
        { className: "schema-explorer-field-objects-list" },
        objects.length === 0
          ? React.createElement(
            "div",
            { className: "schema-explorer-empty-state slds-text-color_weak" },
            "No objects found for this field"
          )
          : objects.map((object) =>
            React.createElement(
              "div",
              {
                key: object.apiName,
                className: "schema-explorer-field-object-row",
                style: { display: "flex", justifyContent: "space-between", alignItems: "center" }
              },
              React.createElement(
                "div",
                {
                  style: { flex: 1, cursor: "pointer" },
                  onClick: (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openFieldRecordInSetup(object.record);
                  },
                  onKeyDown: (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      this.openFieldRecordInSetup(object.record);
                    }
                  },
                  role: "button",
                  tabIndex: 0,
                  title: `Open ${object.apiName}.${object.record?.apiName || fieldGroup.label} in Salesforce setup`,
                },
                React.createElement("div", { className: "schema-explorer-field-object-name" }, object.apiName),
                React.createElement("div", { className: "schema-explorer-field-object-label" }, object.label)
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "slds-button slds-button_brand",
                  style: { padding: "0 8px", border: "none", backgroundColor: "#0176d3", color: "white", fontSize: "11px", height: "22px", lineHeight: "22px", marginLeft: "8px" },
                  onClick: (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const url = chrome.runtime.getURL(`field-analysis.html?host=${encodeURIComponent(this.props.sfHost)}&fieldName=${encodeURIComponent(fieldGroup.apiNames[0])}&objectName=${encodeURIComponent(object.apiName)}`);
                    chrome.tabs.create({ url });
                  },
                  title: `AI Impact Analysis for ${object.apiName}`,
                },
                "✨ AI Analysis"
              )
            )
          )
      )
    );
  }

  renderFieldResultItem(fieldGroup) {
    const { selectedField } = this.state;
    const isExpanded = selectedField?.key === fieldGroup.key;
    const displayFieldGroup = isExpanded ? selectedField : fieldGroup;

    return React.createElement(
      "div",
      {
        key: fieldGroup.key,
        className:
          "schema-explorer-field-item schema-explorer-field-item--drilldown"
          + (isExpanded ? " schema-explorer-field-item--expanded" : ""),
        onClick: (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.selectField(fieldGroup);
        },
        onKeyDown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            this.selectField(fieldGroup);
          }
        },
        role: "button",
        tabIndex: 0,
        title: `Show ${fieldGroup.objectCount} ${fieldGroup.objectCount === 1 ? "object" : "objects"} containing ${fieldGroup.label}`,
      },
      React.createElement("div", { className: "schema-explorer-field-name" }, fieldGroup.label),
      React.createElement(
        "div",
        { className: "schema-explorer-field-label" },
        `${fieldGroup.apiNames.length === 1 ? fieldGroup.apiNames[0] : fieldGroup.apiNames.join(", ")} - ${fieldGroup.objectCount} ${fieldGroup.objectCount === 1 ? "object" : "objects"}`
      ),
      React.createElement("span", { className: "schema-explorer-field-type" }, fieldGroup.dataType || "CustomField"),
      isExpanded ? this.renderFieldObjectsPanel(displayFieldGroup) : null
    );
  }

  renderFieldsView() {
    const { fieldResults, isLoadingFields, searchText, fieldSearchError } = this.state;
    const safeFieldResults = Array.isArray(fieldResults) ? fieldResults : [];

    return React.createElement(
      "div",
      { className: "schema-explorer-fields-view" },
      fieldSearchError
        ? React.createElement(
          "div",
          { className: "schema-explorer-field-search-error slds-notify slds-notify_alert slds-alert_error slds-m-bottom_small" },
          React.createElement("span", {}, `Field search error: ${fieldSearchError}`)
        )
        : null,
      React.createElement(
        "div",
        { className: "schema-explorer-fields-list" },
        isLoadingFields
          ? React.createElement(
            "div",
            { className: "schema-explorer-empty-state slds-text-align_center slds-m-vertical_medium slds-text-color_weak" },
            "Searching fields..."
          )
          : safeFieldResults.length === 0
            ? React.createElement(
              "div",
              { className: "schema-explorer-empty-state slds-text-align_center slds-m-vertical_medium slds-text-color_weak" },
              searchText && searchText.trim().length >= 2
                ? "No fields found matching your search"
                : "Enter 2+ characters to search fields"
            )
            : safeFieldResults.map((fieldGroup) => this.renderFieldResultItem(fieldGroup))
      )
    );
  }

  renderFieldDetails(fieldGroup) {
    const { fieldDependencies, isLoadingDependencies } = this.state;
    return React.createElement(
      "div",
      { className: "schema-explorer-field-details" },
      React.createElement(
        "div",
        { className: "schema-explorer-details-header" },
        React.createElement(
          "div",
          { className: "schema-explorer-details-header-left" },
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
              { className: "schema-explorer-detail-label", style: { textTransform: "none", letterSpacing: "normal" } },
              fieldGroup.apiNames.length === 1 ? fieldGroup.apiNames[0] : `API Names: ${fieldGroup.apiNames.join(", ")}`
            )
          )
        ),
        React.createElement(
          "div",
          { className: "schema-explorer-details-actions", style: { display: "flex", gap: "8px" } },
          React.createElement(
            "button",
            {
              type: "button",
              className: "schema-explorer-details-close slds-button slds-button_brand",
              style: { padding: "0 8px", border: "none", backgroundColor: "#0176d3", color: "white" },
              onClick: () => {
                const objectName = fieldGroup.objects[0]?.apiName || "Unknown";
                const fieldApiName = fieldGroup.apiNames[0];
                const url = chrome.runtime.getURL(`field-analysis.html?host=${encodeURIComponent(this.props.sfHost)}&fieldName=${encodeURIComponent(fieldApiName)}&objectName=${encodeURIComponent(objectName)}`);
                chrome.tabs.create({ url });
              },
              title: "AI Impact Analysis",
            },
            "✨ AI Analysis"
          ),
          React.createElement(
            "button",
            {
              type: "button",
              className: "schema-explorer-details-close slds-button slds-button_neutral",
              style: { padding: "0 8px" },
              onClick: () => this.openFieldInSetup(fieldGroup),
              title: "Open field setup in Salesforce",
            },
            "Open Setup"
          )
        )
      ),
      React.createElement(
        "div",
        { className: "schema-explorer-details-content" },
        React.createElement(
          "div",
          { className: "schema-explorer-detail-section" },
          React.createElement(
            "div",
            { className: "schema-explorer-detail-label" },
            `${fieldGroup.objectCount} ${fieldGroup.objectCount === 1 ? "object" : "objects"} containing this field`
          ),
          React.createElement(
            "div",
            { className: "schema-explorer-objects-list" },
            fieldGroup.objects.map((object) =>
              React.createElement(
                "div",
                {
                  key: object.apiName,
                  className: "schema-explorer-object-badge schema-explorer-object-badge--clickable",
                  onClick: () => this.openFieldRecordInSetup(object.record),
                  onKeyDown: (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      this.openFieldRecordInSetup(object.record);
                    }
                  },
                  role: "button",
                  tabIndex: 0,
                  title: `Open ${object.apiName}.${object.record?.apiName || fieldGroup.label} in Salesforce setup`,
                },
                React.createElement("div", { className: "schema-explorer-object-name" }, object.apiName),
                React.createElement("div", { className: "schema-explorer-object-label" }, object.label)
              )
            )
          )
        ),
        React.createElement(
          "div",
          { className: "schema-explorer-detail-section" },
          React.createElement("div", { className: "schema-explorer-detail-label" }, "Field details"),
          React.createElement("div", { className: "schema-explorer-detail-value" }, `Field Label: ${fieldGroup.label}`),
          React.createElement("div", { className: "schema-explorer-detail-value" }, `API Name(s): ${fieldGroup.apiNames.join(", ")}`),
          React.createElement("div", { className: "schema-explorer-detail-value" }, `Type: ${fieldGroup.dataType || "Unknown"}`),
          React.createElement("div", { className: "schema-explorer-detail-value" }, `Objects: ${fieldGroup.objectCount}`)
        ),
        React.createElement(
          "div",
          { className: "schema-explorer-detail-section" },
          React.createElement("div", { className: "schema-explorer-detail-label" }, "Dependencies"),
          isLoadingDependencies
            ? React.createElement("div", { className: "schema-explorer-empty-state slds-text-align_center" }, "Loading dependencies...")
            : React.createElement(
              React.Fragment,
              null,
              React.createElement(
                "div",
                { className: "schema-explorer-references-list" },
                React.createElement("div", { className: "schema-explorer-detail-value" }, "Field depends on:"),
                fieldDependencies.dependsOn.length === 0
                  ? React.createElement("div", { className: "schema-explorer-reference-item" }, "No upstream dependencies found")
                  : fieldDependencies.dependsOn.map((dep, index) =>
                    React.createElement(
                      "div",
                      { key: `${dep.type}-${dep.id}-${index}`, className: "schema-explorer-reference-item" },
                      `${dep.type}: ${dep.name}${dep.namespace ? ` (${dep.namespace})` : ""}`
                    )
                  )
              ),
              React.createElement(
                "div",
                { className: "schema-explorer-references-list" },
                React.createElement("div", { className: "schema-explorer-detail-value" }, "Referenced by:"),
                fieldDependencies.referencedBy.length === 0
                  ? React.createElement("div", { className: "schema-explorer-reference-item" }, "No downstream references found")
                  : fieldDependencies.referencedBy.map((dep, index) =>
                    React.createElement(
                      "div",
                      { key: `${dep.type}-${dep.id}-${index}`, className: "schema-explorer-reference-item" },
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
    const { searchText, error, activeView, filteredObjects, fieldResults } = this.state;
    const objectCount = Array.isArray(filteredObjects) ? filteredObjects.length : 0;
    const fieldCount = Array.isArray(fieldResults) ? fieldResults.length : 0;

    return h(
      "div",
      { className: "schema-explorer-container tab-container slds-p-horizontal_x-small" },
      h(
        "div",
        { className: "schema-explorer-search slds-m-vertical_small" },
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
        { className: "schema-explorer-segmented-control" },
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
          { className: "slds-notify slds-notify_alert slds-alert_error slds-m-vertical_small" },
          h("span", {}, error)
        )
        : null,
      h(
        "div",
        { className: "schema-explorer-content" },
        activeView === "objects" ? this.renderObjectsView() : this.renderFieldsView()
      )
    );
  }
}

export default AllDataBoxSchemaExplorer;
