"""Metadata synchronization orchestrator.

Coordinates the full pipeline:
1. Initialize sync run record
2. Extract metadata from Salesforce via REST/Tooling APIs
3. Transform and store metadata components
4. Post-process: dependency analysis, indexing
5. Update sync run status
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.database.models.metadata import (
    MetadataComponent,
    MetadataField,
    MetadataRawPayload,
    MetadataSyncRun,
    MetadataVersion,
)
from sfir_backend.infrastructure.database.models.salesforce import SalesforceConnection
from sfir_backend.infrastructure.salesforce.client import SalesforceClient
from sfir_backend.infrastructure.security.encryption import decrypt

logger = structlog.get_logger(__name__)

# Metadata types to sync, ordered by dependency (parents first)
SYNC_PHASES: list[dict[str, Any]] = [
    {
        "name": "objects",
        "rest_endpoint": "sobjects/",
        "component_type": "CustomObject",
        "requires_detail": True,
    },
    {
        "name": "fields",
        "rest_endpoint": None,
        "component_type": "CustomField",
        "parent_type": "CustomObject",
        "requires_detail": False,
    },
    {
        "name": "apex_classes",
        "tooling_query": "SELECT Id, Name, NamespacePrefix, Status, ApiVersion, Body, LengthWithoutComments FROM ApexClass WHERE Status != 'Deleted'",
        "component_type": "ApexClass",
    },
    {
        "name": "apex_triggers",
        "tooling_query": "SELECT Id, Name, NamespacePrefix, Status, ApiVersion, TableEnumOrId, Body FROM ApexTrigger WHERE Status != 'Deleted'",
        "component_type": "ApexTrigger",
    },
    {
        "name": "flows",
        "tooling_query": "SELECT Id, DefinitionId, ApiName, Label, NamespacePrefix, Status, VersionNumber, ProcessType FROM FlowDefinitionView ORDER by ApiName",
        "component_type": "Flow",
    },
    {
        "name": "validation_rules",
        "tooling_query": "SELECT Id, ValidationName, Active, EntityDefinitionId, ErrorDisplayField, ErrorMessage FROM ValidationRule",
        "component_type": "ValidationRule",
    },
    {
        "name": "profiles",
        "metadata_type": "Profile",
        "component_type": "Profile",
    },
    {
        "name": "permission_sets",
        "metadata_type": "PermissionSet",
        "component_type": "PermissionSet",
    },
]


class MetadataSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def start_sync(
        self,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID | None = None,
        sync_type: str = "full",
    ) -> MetadataSyncRun:
        sync_run = MetadataSyncRun(
            id=uuid.uuid4(),
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            status="running",
            sync_type=sync_type,
            api_version=self._settings.salesforce_default_api_version,
            started_at=datetime.now(UTC),
        )
        self._session.add(sync_run)
        await self._session.flush()
        logger.info(
            "metadata_sync_started",
            sync_run_id=str(sync_run.id),
            org_id=str(organization_id),
        )
        return sync_run

    async def _get_salesforce_client(
        self, organization_id: uuid.UUID
    ) -> tuple[SalesforceClient, SalesforceConnection]:
        result = await self._session.execute(
            select(SalesforceConnection).where(
                SalesforceConnection.organization_id == organization_id,
                SalesforceConnection.status == "active",
            )
        )
        conn = result.scalar_one_or_none()
        if not conn:
            raise ValueError(
                f"No active Salesforce connection for organization {organization_id}"
            )

        access_token = decrypt(conn.access_token_encrypted) if conn.access_token_encrypted else None
        refresh_token = decrypt(conn.refresh_token_encrypted) if conn.refresh_token_encrypted else None

        if not access_token:
            raise ValueError("Access token not available. Reconnect the org.")

        client = SalesforceClient(
            instance_url=conn.instance_url,
            api_version=conn.api_version,
            access_token=access_token,
            refresh_token=refresh_token,
            client_id=self._settings.salesforce_client_id,
        )
        return client, conn

    async def sync_organization(
        self,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID | None = None,
    ) -> MetadataSyncRun:
        sync_run = await self.start_sync(organization_id, requested_by_user_id)
        stats = {"components_processed": 0, "fields_processed": 0, "errors": []}

        try:
            client, conn = await self._get_salesforce_client(organization_id)

            api_version = conn.api_version or self._settings.salesforce_default_api_version

            # Phase 1: Describe global objects
            try:
                global_result = await client.describe_global()
                sobjects = (global_result.data or {}).get("sobjects", [])
                for sobj in sobjects:
                    await self._upsert_component(
                        organization_id=organization_id,
                        sync_run_id=sync_run.id,
                        component_type="CustomObject",
                        api_name=sobj["name"],
                        full_name=sobj["name"],
                        label=sobj.get("label"),
                        salesforce_id=sobj.get("keyPrefix"),
                        extra={
                            "custom": sobj.get("custom", False),
                            "custom_setting": sobj.get("customSetting", False),
                            "createable": sobj.get("createable", False),
                            "updateable": sobj.get("updateable", False),
                            "deletable": sobj.get("deletable", False),
                            "queryable": sobj.get("queryable", False),
                            "triggerable": sobj.get("triggerable", False),
                            "replicateable": sobj.get("replicateable", False),
                        },
                    )
                    stats["components_processed"] += 1

                await self._session.flush()
                logger.info(
                    "metadata_sync_objects_complete",
                    count=len(sobjects),
                )
            except Exception as e:
                logger.error("metadata_sync_objects_failed", error=str(e))
                stats["errors"].append(f"objects: {str(e)}")

            # Phase 2: Sync fields for each object
            try:
                components = await self._session.execute(
                    select(MetadataComponent).where(
                        MetadataComponent.organization_id == organization_id,
                        MetadataComponent.component_type == "CustomObject",
                    )
                )
                for component in components.scalars().all():
                    try:
                        field_result = await client.rest(
                            "GET", f"sobjects/{component.api_name}/describe/"
                        )
                        fields_data = (field_result.data or {}).get("fields", [])
                        for field_data in fields_data:
                            await self._upsert_field(
                                organization_id=organization_id,
                                component_id=component.id,
                                sync_run_id=sync_run.id,
                                field_data=field_data,
                            )
                            stats["fields_processed"] += 1

                        await self._session.flush()
                    except Exception as e:
                        logger.error(
                            "field_sync_failed",
                            component=component.api_name,
                            error=str(e),
                        )
                        stats["errors"].append(
                            f"fields_{component.api_name}: {str(e)}"
                        )
            except Exception as e:
                logger.error("metadata_sync_fields_failed", error=str(e))
                stats["errors"].append(f"fields: {str(e)}")

            # Phase 3: Apex classes
            await self._sync_tooling_query(
                organization_id=organization_id,
                sync_run_id=sync_run.id,
                client=client,
                query_str=SYNC_PHASES[2]["tooling_query"],
                component_type="ApexClass",
                stats=stats,
                name_field="Name",
            )

            # Phase 4: Apex triggers
            await self._sync_tooling_query(
                organization_id=organization_id,
                sync_run_id=sync_run.id,
                client=client,
                query_str=SYNC_PHASES[3]["tooling_query"],
                component_type="ApexTrigger",
                stats=stats,
                name_field="Name",
            )

            # Phase 5: Flows
            await self._sync_tooling_query(
                organization_id=organization_id,
                sync_run_id=sync_run.id,
                client=client,
                query_str=SYNC_PHASES[4]["tooling_query"],
                component_type="Flow",
                stats=stats,
                name_field="ApiName",
            )

            # Phase 6: Validation rules
            await self._sync_tooling_query(
                organization_id=organization_id,
                sync_run_id=sync_run.id,
                client=client,
                query_str=SYNC_PHASES[5]["tooling_query"],
                component_type="ValidationRule",
                stats=stats,
                name_field="ValidationName",
            )

            await client.close()

            # Mark sync as completed
            sync_run.status = "completed"
            sync_run.completed_at = datetime.now(UTC)
            sync_run.stats = stats
            await self._session.flush()
            logger.info(
                "metadata_sync_completed",
                sync_run_id=str(sync_run.id),
                stats=stats,
            )

        except Exception as e:
            sync_run.status = "failed"
            sync_run.error_message = str(e)
            sync_run.completed_at = datetime.now(UTC)
            sync_run.stats = stats
            await self._session.flush()
            logger.error("metadata_sync_failed", sync_run_id=str(sync_run.id), error=str(e))

        return sync_run

    async def _sync_tooling_query(
        self,
        organization_id: uuid.UUID,
        sync_run_id: uuid.UUID,
        client: SalesforceClient,
        query_str: str,
        component_type: str,
        stats: dict,
        name_field: str = "Name",
    ) -> None:
        try:
            result = await client.query_tooling(query_str)
            records = (result.data or {}).get("records", [])

            if not records and result.data:
                records = result.data.get("records", [])

            for record in records:
                api_name = record.get(name_field, record.get("Id", "unknown"))
                await self._upsert_component(
                    organization_id=organization_id,
                    sync_run_id=sync_run.id,
                    component_type=component_type,
                    api_name=api_name,
                    full_name=record.get("QualifiedApiName", api_name),
                    label=record.get("Label", api_name),
                    salesforce_id=record.get("Id"),
                    namespace_prefix=record.get("NamespacePrefix", ""),
                    extra={
                        k: v
                        for k, v in record.items()
                        if k not in ("attributes", "Id", name_field)
                    },
                )
                stats["components_processed"] += 1

            await self._session.flush()
        except Exception as e:
            logger.error(
                "tooling_sync_failed",
                component_type=component_type,
                error=str(e),
            )
            stats["errors"].append(f"{component_type}: {str(e)}")

    async def _upsert_component(
        self,
        organization_id: uuid.UUID,
        sync_run_id: uuid.UUID,
        component_type: str,
        api_name: str,
        full_name: str,
        label: str | None = None,
        salesforce_id: str | None = None,
        namespace_prefix: str = "",
        extra: dict | None = None,
    ) -> MetadataComponent:
        existing = await self._session.execute(
            select(MetadataComponent).where(
                MetadataComponent.organization_id == organization_id,
                MetadataComponent.component_type == component_type,
                MetadataComponent.full_name == full_name,
                MetadataComponent.namespace_prefix == namespace_prefix,
            )
        )
        component = existing.scalar_one_or_none()

        now = datetime.now(UTC)
        if component:
            component.label = label or component.label
            component.salesforce_id = salesforce_id or component.salesforce_id
            component.last_seen_at = now
            component.status = "active"
            if extra:
                component.extra = extra
        else:
            component = MetadataComponent(
                id=uuid.uuid4(),
                organization_id=organization_id,
                component_type=component_type,
                api_name=api_name,
                full_name=full_name,
                label=label,
                namespace_prefix=namespace_prefix,
                salesforce_id=salesforce_id,
                status="active",
                api_version=self._settings.salesforce_default_api_version,
                extra=extra or {},
                last_seen_at=now,
                indexed_at=now,
            )
            self._session.add(component)

        return component

    async def _upsert_field(
        self,
        organization_id: uuid.UUID,
        component_id: uuid.UUID,
        sync_run_id: uuid.UUID,
        field_data: dict,
    ) -> MetadataField:
        api_name = field_data["name"]
        existing = await self._session.execute(
            select(MetadataField).where(
                MetadataField.component_id == component_id,
                MetadataField.api_name == api_name,
            )
        )
        field = existing.scalar_one_or_none()

        reference_to = field_data.get("referenceTo", [])
        if isinstance(reference_to, list):
            reference_to = {"refers_to": reference_to}

        field_attrs = {
            "label": field_data.get("label"),
            "data_type": field_data.get("type", "string"),
            "relationship_name": field_data.get("relationshipName"),
            "reference_to": reference_to,
            "is_custom": field_data.get("custom", False),
            "is_formula": field_data.get("formula", False) or bool(field_data.get("formula")),
            "is_required": field_data.get("nillable") is False and not field_data.get("defaultedOnCreate"),
            "is_unique": field_data.get("unique", False),
            "is_external_id": field_data.get("externalId", False),
            "formula": field_data.get("formula"),
            "inline_help_text": field_data.get("inlineHelpText"),
            "extra": {
                "length": field_data.get("length"),
                "precision": field_data.get("precision"),
                "scale": field_data.get("scale"),
                "picklistValues": field_data.get("picklistValues", []),
                "defaultValue": field_data.get("defaultValue"),
                "soapType": field_data.get("soapType"),
                "calculatedFormula": field_data.get("calculatedFormula"),
                "dependentPicklist": field_data.get("dependentPicklist", False),
            },
        }

        if field:
            for attr, value in field_attrs.items():
                setattr(field, attr, value)
        else:
            field = MetadataField(
                id=uuid.uuid4(),
                organization_id=organization_id,
                component_id=component_id,
                api_name=api_name,
                **field_attrs,
            )
            self._session.add(field)

        return field
