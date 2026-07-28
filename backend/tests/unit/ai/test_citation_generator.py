from sfir_backend.domain.ai.models import Citation, CitationSourceType
from sfir_backend.infrastructure.llm.citation_generator import CitationGenerator


class TestCitationGenerator:
    def setup_method(self) -> None:
        self.generator = CitationGenerator()

    def test_extract_inline_citations(self) -> None:
        response = "The component [metadata:01pABC] is used by [dep:XYZ123]"
        context = [
            Citation(source_type=CitationSourceType.METADATA, source_id="01pABC", source_name="Account"),
            Citation(source_type=CitationSourceType.DEPENDENCY, source_id="XYZ123", source_name="SomeDep"),
        ]
        citations = self.generator.extract_citations_from_response(response, context)
        assert len(citations) >= 1
        found_ids = {c.source_id for c in citations}
        assert "01pABC" in found_ids

    def test_extract_contextual_citations(self) -> None:
        response = "The Account object is critical"
        context = [
            Citation(source_type=CitationSourceType.METADATA, source_id="01pABC", source_name="Account"),
        ]
        citations = self.generator.extract_citations_from_response(response, context)
        assert len(citations) >= 1

    def test_validate_citations(self) -> None:
        context = [
            Citation(source_type=CitationSourceType.METADATA, source_id="valid1", source_name="V1"),
        ]
        test_citations = [
            Citation(source_type=CitationSourceType.METADATA, source_id="valid1", source_name="V1"),
            Citation(source_type=CitationSourceType.DEPENDENCY, source_id="fake", source_name="Fake"),
        ]
        valid = self.generator.validate_citations(test_citations, context)
        assert len(valid) == 1
        assert valid[0].source_id == "valid1"

    def test_format_citations(self) -> None:
        citations = [
            Citation(source_type=CitationSourceType.METADATA, source_id="id1", source_name="Name1"),
        ]
        formatted = self.generator.format_citations(citations)
        assert "**References:**" in formatted
        assert "Name1" in formatted

    def test_format_citations_empty(self) -> None:
        assert self.generator.format_citations([]) == ""

    def test_check_hallucination(self) -> None:
        content = "The component MyCustomController handles the logic"
        context = [
            Citation(source_type=CitationSourceType.METADATA, source_id="id1", source_name="other_thing"),
        ]
        warnings = self.generator.check_hallucination(content, context)
        assert len(warnings) > 0
