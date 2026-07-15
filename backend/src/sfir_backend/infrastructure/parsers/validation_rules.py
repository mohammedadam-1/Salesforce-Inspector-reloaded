from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataFormula, MetadataValidationRule
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class ValidationRuleParser(BaseParser):
    metadata_type = "validation_rule"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataValidationRule:
        _ = context
        full_name = data.get("fullName", "")
        object_api_name = data.get("object_api_name", "")
        if not object_api_name and "." in full_name:
            parts = full_name.split(".")
            object_api_name = parts[0] if len(parts) > 1 else ""

        return MetadataValidationRule(
            api_name=full_name,
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=object_api_name,
            active=data.get("active", True),
            error_message=data.get("errorMessage", data.get("error_message", "")),
            error_display_field=data.get("errorDisplayField", data.get("error_display_field")),
            formula=data.get("formula", ""),
        )


class FormulaParser(BaseParser):
    metadata_type = "formula"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataFormula:
        _ = context
        return MetadataFormula(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=data.get("object_api_name", ""),
            field_api_name=data.get("field_api_name"),
            formula_expression=data.get("formula", data.get("formula_expression", "")),
            formula_type=data.get("formulaType", data.get("formula_type", "formula")),
            formula_treat_blanks_as=data.get(
                "formulaTreatBlanksAs",
                data.get("formula_treat_blanks_as", "BlankAsBlank"),
            ),
            return_type=data.get("returnType", data.get("return_type", "Text")),
        )
