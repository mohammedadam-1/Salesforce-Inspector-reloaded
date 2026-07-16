from sfir_backend.domain.ai.models import AIFeature
from sfir_backend.infrastructure.llm.prompt_template import (
    PromptTemplateEngine,
    PromptVersionManager,
)


class TestPromptTemplateEngine:
    def setup_method(self) -> None:
        self.engine = PromptTemplateEngine()

    def test_get_role_template(self) -> None:
        template = self.engine.get_role_template(AIFeature.EXPLAIN_APEX)
        assert "Apex" in template

    def test_get_role_template_default(self) -> None:
        template = self.engine.get_role_template(AIFeature.QUESTION_ANSWERING)
        assert "Metadata" in template or "Salesforce" in template

    def test_set_role_template(self) -> None:
        self.engine.set_role_template(AIFeature.EXPLAIN_APEX, "Custom Apex template")
        assert self.engine.get_role_template(AIFeature.EXPLAIN_APEX) == "Custom Apex template"

    def test_render_context(self) -> None:
        result = self.engine.render_context("metadata", metadata_content="CustomObject: Account")
        assert "CustomObject: Account" in result

    def test_render_context_unknown(self) -> None:
        result = self.engine.render_context("nonexistent", foo="bar")
        assert result == ""

    def test_register_custom_template(self) -> None:
        self.engine.register_custom_template("test", "Hello {name}")
        tmpl = self.engine.get_custom_template("test")
        assert tmpl == "Hello {name}"

    def test_get_custom_template_missing(self) -> None:
        assert self.engine.get_custom_template("missing") is None


class TestPromptVersionManager:
    def setup_method(self) -> None:
        self.mgr = PromptVersionManager()

    def test_create_version(self) -> None:
        vid = self.mgr.create_version("test-prompt", "Content here")
        assert len(vid) == 12

    def test_get_version(self) -> None:
        vid = self.mgr.create_version("test", "Hello", version="1.0.0")
        v = self.mgr.get_version(vid)
        assert v is not None
        assert v["name"] == "test"
        assert v["version"] == "1.0.0"

    def test_get_version_missing(self) -> None:
        assert self.mgr.get_version("nonexistent") is None

    def test_list_versions(self) -> None:
        self.mgr.create_version("a", "content a")
        self.mgr.create_version("b", "content b")
        all_v = self.mgr.list_versions()
        assert len(all_v) == 2

    def test_list_versions_filtered(self) -> None:
        self.mgr.create_version("filtered", "data")
        results = self.mgr.list_versions(name="filtered")
        assert len(results) == 1

    def test_validate_prompt_valid(self) -> None:
        issues = self.mgr.validate_prompt("Hello {query} and {context}")
        assert len(issues) == 0

    def test_validate_prompt_unknown_placeholder(self) -> None:
        issues = self.mgr.validate_prompt("Hello {unknown_var}")
        assert len(issues) == 1
        assert "unknown_var" in issues[0]
