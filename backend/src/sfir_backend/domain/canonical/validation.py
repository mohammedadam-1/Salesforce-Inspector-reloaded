from __future__ import annotations

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataFormula(MetadataComponent):
    type: str = "formula"
    object_api_name: str = ""
    field_api_name: str | None = None
    formula_expression: str = ""
    formula_type: str = "formula"
    formula_treat_blanks_as: str = "BlankAsBlank"
    return_type: str = "Text"


class MetadataValidationRule(MetadataComponent):
    type: str = "validation_rule"
    object_api_name: str = ""
    active: bool = True
    error_message: str = ""
    error_display_field: str | None = None
    formula: str = ""
    description: str | None = None
