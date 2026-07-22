from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import (
    MetadataPublicGroup,
    MetadataQueue,
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class RoleParser(BaseParser):
    metadata_type = "role"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataRole:
        _ = context
        return MetadataRole(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            parent_role=data.get("parentRole", data.get("parent_role")),
            case_access_level=data.get(
                "caseAccessLevel", data.get("case_access_level", "None"),
            ),
            contact_access_level=data.get(
                "contactAccessLevel", data.get("contact_access_level", "None"),
            ),
            opportunity_access_level=data.get(
                "opportunityAccessLevel",
                data.get("opportunity_access_level", "None"),
            ),
            account_access_level=data.get(
                "accountAccessLevel", data.get("account_access_level", "None"),
            ),
            may_forecast_manager=data.get(
                "mayForecastManager", data.get("may_forecast_manager", False),
            ),
        )


class QueueParser(BaseParser):
    metadata_type = "queue"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataQueue:
        _ = context
        return MetadataQueue(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            email=data.get("email"),
            queue_sobjects=data.get(
                "queueSobjects", data.get("queue_sobjects", []),
            ),
            queue_members=data.get(
                "queueMembers", data.get("queue_members", []),
            ),
            queue_rules=data.get(
                "queueRules", data.get("queue_rules", []),
            ),
        )


class PublicGroupParser(BaseParser):
    metadata_type = "public_group"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataPublicGroup:
        _ = context
        return MetadataPublicGroup(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            members=data.get("members", []),
        )


class SharingRuleParser(BaseParser):
    metadata_type = "sharing_rule"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataSharingRule:
        _ = context
        return MetadataSharingRule(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=data.get("object_api_name", ""),
            shared_to=data.get("sharedTo", data.get("shared_to", "")),
            shared_from=data.get("sharedFrom", data.get("shared_from", "")),
            access_level=data.get("accessLevel", data.get("access_level", "Read")),
            rule_type=data.get("ruleType", data.get("rule_type", "CriteriaBased")),
        )
