"""Canonical parser adapter.

Bridges the broad, richer parser framework (``infrastructure.parsers``,
canonical ``MetadataComponent`` producers) into the frozen runtime
``MetadataParser`` contract used by ``ParserStage``.

The runtime pipeline only ever depends on ``MetadataParser``; it never knows
whether a component was produced by a narrow legacy parser or by a broad
canonical parser behind this adapter. This is the Phase 3.2 integration
point: reuse the richer parsing logic behind the existing interface without
redesigning the pipeline.
"""

from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.infrastructure.parsers.base import BaseParser as BroadBaseParser
from sfir_backend.infrastructure.parsers.base import ParserContext
from sfir_backend.infrastructure.salesforce.parsers.base import (
    MetadataParser,
    ParsingResult,
)


class CanonicalParserAdapter(MetadataParser[MetadataComponent]):
    """Adapts a broad ``BaseParser`` to the runtime ``MetadataParser`` contract.

    Attributes:
        metadata_type: snake_case canonical type handled (used as the registry key).
        _component_types: Salesforce API type names this adapter answers to.
        _parser: the wrapped broad parser.
    """

    def __init__(
        self,
        component_types: list[str],
        parser: BroadBaseParser,
        *,
        context: ParserContext | None = None,
    ) -> None:
        self.metadata_type = parser.metadata_type
        self._component_types = frozenset(component_types)
        self._parser = parser
        self._context = context

    def can_parse(self, component_type: str) -> bool:
        return component_type in self._component_types

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[MetadataComponent]:
        result = await self._parser.parse(raw, context=self._context)
        if result.component is not None:
            return ParsingResult(
                success=True,
                data=result.component,
                errors=[],
                warnings=list(result.warnings),
            )
        errors = list(result.errors)
        if not errors:
            errors = [
                f"Canonical parser '{self.metadata_type}' produced no component",
            ]
        return ParsingResult(
            success=False,
            data=None,
            errors=errors,
            warnings=list(result.warnings),
        )

    async def parse_body(self, body: str) -> ParsingResult[MetadataComponent]:
        return await self.parse({"Body": body})


def build_canonical_parser_adapters(
    *,
    context: ParserContext | None = None,
) -> list[CanonicalParserAdapter]:
    """Build adapters for every broad parser not covered by the narrow parsers.

    The narrow runtime parsers already cover: ApexClass, ApexTrigger,
    CustomObject, Layout and ValidationRule. Those five keep winning in the
    registry (registered first, first ``can_parse`` match wins), so the
    adapters only add coverage for the remaining broad-parser types. This
    preserves backward compatibility while extending rich parsing to the
    rest of the metadata surface.
    """
    from sfir_backend.infrastructure.parsers.access import (
        PublicGroupParser,
        QueueParser,
        RoleParser,
        SharingRuleParser,
    )
    from sfir_backend.infrastructure.parsers.core import (
        FieldParser,
        GlobalValueSetParser,
        RelationshipParser,
    )
    from sfir_backend.infrastructure.parsers.custom import (
        CustomMetadataParser,
        CustomSettingParser,
    )
    from sfir_backend.infrastructure.parsers.flows import (
        FlowParser,
        FlowVersionParser,
    )
    from sfir_backend.infrastructure.parsers.integration import (
        ConnectedAppParser,
        EmailTemplateParser,
        NamedCredentialParser,
    )
    from sfir_backend.infrastructure.parsers.layouts import RecordTypeParser
    from sfir_backend.infrastructure.parsers.permissions import (
        PermissionSetParser,
        ProfileParser,
    )
    from sfir_backend.infrastructure.parsers.reporting import (
        DashboardParser,
        ReportParser,
    )
    from sfir_backend.infrastructure.parsers.ui import (
        LightningPageParser,
        QuickActionParser,
    )
    from sfir_backend.infrastructure.parsers.validation_rules import FormulaParser
    from sfir_backend.infrastructure.parsers.workflows import (
        ApprovalProcessParser,
        WorkflowParser,
    )

    return [
        CanonicalParserAdapter(["Role", "UserRole"], RoleParser(), context=context),
        CanonicalParserAdapter(["Queue"], QueueParser(), context=context),
        CanonicalParserAdapter(["PublicGroup"], PublicGroupParser(), context=context),
        CanonicalParserAdapter(["SharingRule"], SharingRuleParser(), context=context),
        CanonicalParserAdapter(["CustomField", "Field"], FieldParser(), context=context),
        CanonicalParserAdapter(
            ["GlobalValueSet"], GlobalValueSetParser(), context=context,
        ),
        CanonicalParserAdapter(
            ["Relationship"], RelationshipParser(), context=context,
        ),
        CanonicalParserAdapter(
            ["CustomMetadata"], CustomMetadataParser(), context=context,
        ),
        CanonicalParserAdapter(["CustomSetting"], CustomSettingParser(), context=context),
        CanonicalParserAdapter(["Flow"], FlowParser(), context=context),
        CanonicalParserAdapter(["FlowVersion"], FlowVersionParser(), context=context),
        CanonicalParserAdapter(
            ["EmailTemplate"], EmailTemplateParser(), context=context,
        ),
        CanonicalParserAdapter(
            ["NamedCredential"], NamedCredentialParser(), context=context,
        ),
        CanonicalParserAdapter(
            ["ConnectedApp"], ConnectedAppParser(), context=context,
        ),
        CanonicalParserAdapter(["RecordType"], RecordTypeParser(), context=context),
        CanonicalParserAdapter(
            ["PermissionSet"], PermissionSetParser(), context=context,
        ),
        CanonicalParserAdapter(["Profile"], ProfileParser(), context=context),
        CanonicalParserAdapter(["Report"], ReportParser(), context=context),
        CanonicalParserAdapter(["Dashboard"], DashboardParser(), context=context),
        CanonicalParserAdapter(
            ["LightningPage", "FlexiPage"], LightningPageParser(), context=context,
        ),
        CanonicalParserAdapter(["QuickAction"], QuickActionParser(), context=context),
        CanonicalParserAdapter(["Formula"], FormulaParser(), context=context),
        CanonicalParserAdapter(
            ["Workflow", "WorkflowRule"], WorkflowParser(), context=context,
        ),
        CanonicalParserAdapter(
            ["ApprovalProcess"], ApprovalProcessParser(), context=context,
        ),
    ]
