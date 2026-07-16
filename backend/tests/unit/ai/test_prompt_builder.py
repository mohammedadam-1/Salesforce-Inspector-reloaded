from sfir_backend.application.use_cases.ai.prompt_builder import PromptBuilder
from sfir_backend.domain.ai.models import AIFeature, Citation, CitationSourceType


class TestPromptBuilder:
    def setup_method(self) -> None:
        self.builder = PromptBuilder()

    def test_build_chat_messages(self) -> None:
        messages = self.builder.build_chat_messages(
            feature=AIFeature.EXPLAIN_APEX,
            query="Explain this code",
            context="Some context about the code",
        )
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Explain this code"

    def test_build_chat_with_history(self) -> None:
        history = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]
        messages = self.builder.build_chat_messages(
            feature=AIFeature.QUESTION_ANSWERING,
            query="Follow up",
            history=history,
        )
        assert len(messages) == 4
        assert messages[1].content == "Previous question"
        assert messages[2].content == "Previous answer"

    def test_build_chat_with_citations(self) -> None:
        citations = [
            Citation(
                source_type=CitationSourceType.METADATA,
                source_id="01pABC",
                source_name="Account",
            ),
        ]
        messages = self.builder.build_chat_messages(
            feature=AIFeature.EXPLAIN_APEX,
            query="test",
            context="metadata info",
            citations=citations,
        )
        system_msg = messages[0].content
        assert "01pABC" in system_msg
        assert "[type:id]" in system_msg

    def test_build_explain_prompt(self) -> None:
        messages = self.builder.build_explain_prompt(
            feature=AIFeature.EXPLAIN_FLOW,
            component_type="Flow",
            component_data="Flow XML data here",
        )
        assert len(messages) == 2
        assert "Component Type: Flow" in messages[1].content

    def test_build_summarize_prompt(self) -> None:
        messages = self.builder.build_summarize_prompt(
            feature=AIFeature.SUMMARIZE_DEPENDENCY_GRAPH,
            data_summary="Graph has 50 nodes",
        )
        assert len(messages) == 2
        assert "Graph has 50 nodes" in messages[1].content
