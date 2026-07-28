import {apiVersion, sfConn} from "./inspector.js";

const USER_FIELDS = [
  "Id",
  "Name",
  "Email",
  "Username",
  "Alias",
  "IsActive",
  "LastLoginDate",
  "ProfileId",
  "Profile.Name",
  "UserRoleId",
  "UserRole.Name"
];

const SECTION_LABELS = {
  owned: "Owned Records",
  created: "Created Records",
  activity: "Activity"
};

const CANDIDATE_OBJECTS = [
  {name: "Account", label: "Accounts", displayField: "Name", owned: true, created: true, extraFields: ["Type", "LastModifiedDate"]},
  {name: "Opportunity", label: "Opportunities", displayField: "Name", owned: true, created: true, extraFields: ["StageName", "CloseDate", "LastModifiedDate"]},
  {name: "Case", label: "Cases", displayField: "CaseNumber", owned: true, created: true, extraFields: ["Subject", "Status", "LastModifiedDate"]},
  {name: "Task", label: "Tasks", displayField: "Subject", owned: true, created: true, activity: true, extraFields: ["Status", "Priority", "ActivityDate", "WhatId", "WhoId"]},
  {name: "Event", label: "Events", displayField: "Subject", owned: true, created: true, activity: true, extraFields: ["StartDateTime", "EndDateTime", "WhatId", "WhoId"]},
  {name: "Contact", label: "Contacts", displayField: "Name", owned: true, created: true, extraFields: ["Email", "LastModifiedDate"]},
  {name: "Lead", label: "Leads", displayField: "Name", owned: true, created: true, extraFields: ["Company", "Status", "LastModifiedDate"]},
  {name: "Campaign", label: "Campaigns", displayField: "Name", owned: true, created: true, extraFields: ["Type", "Status", "LastModifiedDate"]}
];

function escapeSoqlLiteral(value) {
  return String(value || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

function isSalesforceId(value) {
  return /^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$/.test(value || "");
}

function sendSalesforceRequest({sfHost, path, method = "GET", body}) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      message: "salesforceRestRequest",
      sfHost,
      sessionId: sfConn.sessionId,
      path,
      method,
      body
    }, response => {
      if (!response) {
        reject(new Error("Salesforce request returned no response."));
      } else if (!response.success) {
        reject(new Error(response.error || "Salesforce request failed."));
      } else {
        resolve(response.data);
      }
    });
  });
}

function queryPath(soql) {
  return `/services/data/v${apiVersion}/query/?q=${encodeURIComponent(soql)}`;
}

function buildSafeQuery(config, filterField, userId) {
  const fields = ["Id", config.displayField, ...config.extraFields]
    .filter((field, index, list) => field && list.indexOf(field) === index);
  return `SELECT ${fields.join(", ")} FROM ${config.name} WHERE ${filterField} = '${escapeSoqlLiteral(userId)}' WITH USER_MODE`;
}

function createInventoryItem(config, sobject) {
  const filterFields = [];
  const sections = [];
  if (config.owned) {
    filterFields.push("OwnerId");
    sections.push("owned");
  }
  if (config.created) {
    filterFields.push("CreatedById");
    sections.push("created");
  }
  if (config.activity) {
    sections.push("activity");
  }
  return {
    objectApiName: config.name,
    label: sobject?.label || config.label,
    keyPrefix: sobject?.keyPrefix || "",
    displayField: config.displayField,
    filterFields,
    sections: [...new Set(sections)],
    extraFields: config.extraFields
  };
}

function getInventoryConfig(objectInventory, objectApiName) {
  return objectInventory.find(item => item.objectApiName === objectApiName);
}

function createQueryKey(query, index) {
  return `${query.section}-${query.objectApiName}-${query.filterField}-${index}`;
}

function normalizeQuerySoql(query, config, userId) {
  const allowedFilters = config.filterFields || [];
  const filterField = allowedFilters.includes(query.filterField) ? query.filterField
    : query.section === "created" ? "CreatedById" : "OwnerId";

  // Always rebuild SOQL from scratch via buildSafeQuery — never trust the AI's
  // raw WHERE clause. Despite prompt instructions the model routinely adds extra
  // conditions such as:
  //   AND CreatedDate = LAST_N_DAYS:30
  //   AND IsActive = true
  //   AND LastModifiedDate >= THIS_YEAR
  // Those conditions pass structural validation but silently restrict results to
  // recently-touched or active records only (the root cause of the retrieval bug).
  // buildSafeQuery always returns ALL records matching the owner/creator filter.
  return buildSafeQuery({
    name: config.objectApiName,
    displayField: config.displayField,
    extraFields: config.extraFields
  }, filterField, userId);
}

function getRecordLabel(record, query) {
  const displayField = query.displayField;
  return record[displayField]
    || record.Name
    || record.Subject
    || record.CaseNumber
    || record.Id;
}

function getRecordMeta(record) {
  return [
    record.StageName,
    record.Status,
    record.Type,
    record.Priority,
    record.CloseDate,
    record.ActivityDate,
    record.StartDateTime,
    record.LastModifiedDate
  ].filter(Boolean).join(" | ");
}

function summarizeForAi(sections) {
  return Object.fromEntries(Object.entries(sections).map(([key, groups]) => [
    key,
    groups.map(group => ({
      title: group.title,
      objectApiName: group.objectApiName,
      totalSize: group.totalSize,
      returnedRows: group.records.length,
      error: group.error || null,
      sampleRecords: group.records.slice(0, 5).map(record => ({
        Id: record.Id,
        label: record.label,
        meta: record.meta
      }))
    }))
  ]));
}

export class SalesforceUserInsightService {
  constructor(sfHost) {
    this.sfHost = sfHost;
  }

  async searchUsers(input) {
    const trimmed = String(input || "").trim();
    if (!trimmed) {
      return [];
    }
    const escaped = escapeSoqlLiteral(trimmed);
    const whereClause = isSalesforceId(trimmed)
      ? `Id = '${escaped}'`
      : `Name LIKE '%${escaped}%' OR Email LIKE '%${escaped}%' OR Username LIKE '%${escaped}%' OR Alias LIKE '%${escaped}%'`;
    const soql = `SELECT ${USER_FIELDS.join(", ")} FROM User WHERE ${whereClause} WITH USER_MODE ORDER BY IsActive DESC, LastLoginDate DESC NULLS LAST LIMIT 20`;
    const response = await sendSalesforceRequest({
      sfHost: this.sfHost,
      path: queryPath(soql)
    });
    return response.records || [];
  }

  async getUserDetails(userId) {
    const soql = `SELECT ${USER_FIELDS.join(", ")} FROM User WHERE Id = '${escapeSoqlLiteral(userId)}' WITH USER_MODE LIMIT 1`;
    const response = await sendSalesforceRequest({
      sfHost: this.sfHost,
      path: queryPath(soql)
    });
    return response.records?.[0] || null;
  }

  async getObjectInventory() {
    try {
      const response = await sendSalesforceRequest({
        sfHost: this.sfHost,
        path: `/services/data/v${apiVersion}/sobjects/`
      });
      const available = new Map((response.sobjects || [])
        .filter(sobject => sobject.queryable !== false)
        .map(sobject => [sobject.name, sobject]));
      return CANDIDATE_OBJECTS
        .filter(config => available.has(config.name))
        .map(config => createInventoryItem(config, available.get(config.name)));
    } catch (e) {
      console.warn("Unable to retrieve sObject inventory, using built-in common objects.", e);
      return CANDIDATE_OBJECTS.map(config => createInventoryItem(config, null));
    }
  }

  sanitizeQueryPlan(queryPlan, {objectInventory, userId, maxQueries}) {
    const rawQueries = Array.isArray(queryPlan?.queries) ? queryPlan.queries : [];
    return rawQueries
      .slice(0, maxQueries)
      .map((query, index) => {
        const config = getInventoryConfig(objectInventory, query.objectApiName);
        if (!config || !["owned", "created", "activity"].includes(query.section)) {
          return null;
        }
        const filterField = config.filterFields.includes(query.filterField) ? query.filterField
          : query.section === "created" ? "CreatedById" : "OwnerId";
        if (!config.filterFields.includes(filterField)) {
          return null;
        }
        return {
          key: createQueryKey(query, index),
          section: query.section,
          objectApiName: config.objectApiName,
          objectLabel: config.label,
          displayField: config.displayField,
          filterField,
          title: query.title || `${SECTION_LABELS[query.section]}: ${config.label}`,
          rationale: query.rationale || "",
          soql: normalizeQuerySoql({...query, filterField}, config, userId)
        };
      })
      .filter(Boolean);
  }

  buildDefaultQueryPlan({objectInventory, userId, maxQueries}) {
    const requests = [
      ["owned", "Account", "OwnerId", "All Accounts"],
      ["owned", "Opportunity", "OwnerId", "All Opportunities"],
      ["owned", "Case", "OwnerId", "All Cases"],
      ["owned", "Task", "OwnerId", "All Tasks"],
      ["created", "Account", "CreatedById", "All Accounts"],
      ["created", "Opportunity", "CreatedById", "All Opportunities"],
      ["created", "Case", "CreatedById", "All Cases"],
      ["activity", "Task", "OwnerId", "All Tasks"],
      ["activity", "Event", "OwnerId", "All Events"]
    ];
    return requests
      .map(([section, objectApiName, filterField, title], index) => {
        const config = getInventoryConfig(objectInventory, objectApiName);
        if (!config || !config.filterFields.includes(filterField)) {
          return null;
        }
        return {
          key: `${section}-${objectApiName}-${filterField}-${index}`,
          section,
          objectApiName,
          objectLabel: config.label,
          displayField: config.displayField,
          filterField,
          title,
          rationale: "Built-in safe fallback query.",
          soql: buildSafeQuery({
            name: objectApiName,
            displayField: config.displayField,
            extraFields: config.extraFields
          }, filterField, userId)
        };
      })
      .filter(Boolean)
      .slice(0, maxQueries);
  }

  async fetchAllQueryRecords(initialBody) {
    const records = [...(initialBody?.records || [])];
    let nextRecordsUrl = initialBody?.done === false ? initialBody?.nextRecordsUrl : null;

    while (nextRecordsUrl) {
      const page = await sendSalesforceRequest({
        sfHost: this.sfHost,
        path: nextRecordsUrl
      });
      records.push(...(page.records || []));
      nextRecordsUrl = page.done === false ? page.nextRecordsUrl : null;
    }

    return records;
  }

  async executeQueryPlan(queries) {
    if (queries.length === 0) {
      return {
        owned: [],
        created: [],
        activity: []
      };
    }

    // Salesforce Composite API allows a maximum of 5 query subrequests per call.
    // Split queries into chunks of 5 and execute each batch sequentially to avoid
    // the "Limit number of query or Collections in Rest Operations reached" error.
    const COMPOSITE_QUERY_LIMIT = 5;
    const batches = [];
    for (let i = 0; i < queries.length; i += COMPOSITE_QUERY_LIMIT) {
      batches.push(queries.slice(i, i + COMPOSITE_QUERY_LIMIT));
    }

    const allCompositeResponses = [];
    for (const batch of batches) {
      const payload = {
        allOrNone: false,
        compositeRequest: batch.map(query => ({
          method: "GET",
          referenceId: query.key.replace(/[^A-Za-z0-9_]/g, "_"),
          url: queryPath(query.soql)
        }))
      };
      const response = await sendSalesforceRequest({
        sfHost: this.sfHost,
        path: `/services/data/v${apiVersion}/composite`,
        method: "POST",
        body: payload
      });
      allCompositeResponses.push(...(response.compositeResponse || []));
    }

    const sections = {
      owned: [],
      created: [],
      activity: []
    };
    const groups = await Promise.all(queries.map(async (query, index) => {
      const compositeResponse = allCompositeResponses[index];
      const body = compositeResponse?.body || {};
      const error = compositeResponse?.httpStatusCode >= 400
        ? (Array.isArray(body) ? body.map(item => item.message).join(", ") : body.message || "Query failed")
        : null;
      const rawRecords = error ? [] : await this.fetchAllQueryRecords(body);
      const records = rawRecords.map(record => ({
        ...record,
        label: getRecordLabel(record, query),
        meta: getRecordMeta(record),
        link: `https://${this.sfHost}/${record.Id}`
      }));
      return {
        ...query,
        totalSize: body.totalSize || records.length,
        done: error ? body.done !== false : true,
        records,
        error
      };
    }));
    groups.forEach(group => {
      sections[group.section].push(group);
    });
    return sections;
  }

  summarizeSectionsForAi(sections) {
    return summarizeForAi(sections);
  }
}
