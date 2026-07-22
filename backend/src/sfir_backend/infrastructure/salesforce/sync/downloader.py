"""MetadataDownloadManager - downloads metadata from Salesforce APIs."""

import structlog

from sfir_backend.infrastructure.salesforce.client import SalesforceClient

logger = structlog.get_logger(__name__)


class MetadataDownloadError(Exception):
    pass


class MetadataDownloadManager:
    """Downloads metadata from Salesforce via Tooling API and Metadata API.

    Delegates HTTP calls to the SalesforceClient from Phase 7.
    """

    def __init__(self) -> None:
        self._client: SalesforceClient | None = None

    def set_client(self, client: SalesforceClient) -> None:
        self._client = client

    async def list_metadata_types(self) -> list[dict]:
        self._ensure_client()
        return await self._client.rest("/tooling/sobjects")

    async def describe_metadata_type(self, metadata_type: str) -> dict:
        self._ensure_client()
        return await self._client.rest(
            f"/tooling/sobjects/{metadata_type}/describe",
        )

    async def query_metadata(self, soql: str) -> list[dict]:
        self._ensure_client()
        return await self._client.query(soql)

    async def get_metadata_components(
        self, metadata_type: str, fields: str = "Id, Name, LastModifiedDate",
    ) -> list[dict]:
        soql = f"SELECT {fields} FROM {metadata_type} ORDER BY Name"
        return await self.query_metadata(soql)

    async def get_component_detail(
        self, metadata_type: str, component_id: str,
    ) -> dict:
        self._ensure_client()
        return await self._client.rest(
            f"/tooling/sobjects/{metadata_type}/{component_id}",
        )

    async def get_all_objects(self) -> list[dict]:
        self._ensure_client()
        result = await self._client.rest("/sobjects")
        return result.get("sobjects", [])

    async def get_object_describe(self, object_name: str) -> dict:
        self._ensure_client()
        return await self._client.rest(f"/sobjects/{object_name}/describe")

    async def get_apex_classes(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, Body, LastModifiedDate, ApiVersion "
            "FROM ApexClass ORDER BY Name",
        )

    async def get_apex_triggers(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, Body, LastModifiedDate, TableEnumOrId "
            "FROM ApexTrigger ORDER BY Name",
        )

    async def get_flows(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Definition.DeveloperName, Status, LastModifiedDate, "
            "VersionNumber, DefinitionId "
            "FROM FlowDefinitionView ORDER BY Definition.DeveloperName",
        )

    async def get_profiles(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, LastModifiedDate, UserLicenseId "
            "FROM Profile ORDER BY Name",
        )

    async def get_permission_sets(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, Label, LastModifiedDate "
            "FROM PermissionSet ORDER BY Name",
        )

    async def get_validation_rules(self, object_name: str) -> list[dict]:
        return await self.query_metadata(
            f"SELECT Id, ValidationName, Active, ErrorDisplayField, "
            f"ErrorMessage, LastModifiedDate "
            f"FROM ValidationRule WHERE TableEnumOrId = '{self._escape_soql(object_name)}' "
            f"ORDER BY ValidationName",
        )

    async def get_layouts(self, object_name: str) -> list[dict]:
        return await self.query_metadata(
            f"SELECT Id, Name, LastModifiedDate, LayoutType "
            f"FROM Layout WHERE TableEnumOrId = '{self._escape_soql(object_name)}' "
            f"ORDER BY Name",
        )

    async def get_record_types(self, object_name: str) -> list[dict]:
        return await self.query_metadata(
            f"SELECT Id, Name, DeveloperName, NamespacePrefix, "
            f"LastModifiedDate "
            f"FROM RecordType WHERE SobjectType = '{self._escape_soql(object_name)}' "
            f"ORDER BY Name",
        )

    async def get_fields_for_object(self, object_name: str) -> list[dict]:
        describe = await self.get_object_describe(object_name)
        return describe.get("fields", [])

    async def get_workflow_rules(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, TableEnumOrId, Active, "
            "LastModifiedDate FROM WorkflowRule ORDER BY Name",
        )

    async def get_approval_processes(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, TableEnumOrId, Active, "
            "LastModifiedDate FROM ProcessDefinition ORDER BY Name",
        )

    async def get_reports(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, LastModifiedDate, OwnerId "
            "FROM Report ORDER BY Name",
        )

    async def get_dashboards(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, LastModifiedDate, OwnerId "
            "FROM Dashboard ORDER BY Name",
        )

    async def get_email_templates(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, DeveloperName, TemplateType, "
            "LastModifiedDate FROM EmailTemplate ORDER BY Name",
        )

    async def get_custom_labels(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, Language, Protected, "
            "LastModifiedDate FROM ExternalString ORDER BY Name",
        )

    async def get_global_value_sets(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, LastModifiedDate "
            "FROM GlobalValueSet ORDER BY Name",
        )

    async def get_roles(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, DeveloperName, LastModifiedDate "
            "FROM UserRole ORDER BY Name",
        )

    async def get_queues(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, QueueSobject.Type, LastModifiedDate "
            "FROM QueueSobject ORDER BY QueueSobject.Type",
        )

    async def get_sharing_rules(self) -> list[dict]:
        return await self.query_metadata(
            "SELECT Id, Name, Type, LastModifiedDate "
            "FROM SharingRule ORDER BY Name",
        )

    async def download_component_body(
        self, metadata_type: str, component_id: str,
    ) -> str | None:
        try:
            detail = await self.get_component_detail(metadata_type, component_id)
            return detail.get("Body")
        except Exception:
            logger.warning(
                "failed_to_download_component_body",
                metadata_type=metadata_type,
                component_id=component_id,
            )
            return None

    def _ensure_client(self) -> None:
        if not self._client:
            raise MetadataDownloadError("SalesforceClient not set")

    @staticmethod
    def _escape_soql(value: str) -> str:
        return value.replace("'", "\\'")
