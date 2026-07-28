from sfir_backend.infrastructure.llm.response_validator import (
    ResponseFormatter,
    ResponseStreamer,
    ResponseValidator,
)


class TestResponseValidator:
    def setup_method(self) -> None:
        self.validator = ResponseValidator()

    def test_validate_json_structure_valid(self) -> None:
        result = self.validator.validate_json_structure("Valid content")
        assert result["valid"] is True

    def test_validate_empty(self) -> None:
        result = self.validator.validate_json_structure("")
        assert result["valid"] is False

    def test_validate_with_required_sections(self) -> None:
        content = "# Summary\n## Details\nHere are the details."
        result = self.validator.validate_json_structure(content, required_sections=["Summary", "Details"])
        assert result["valid"] is True

    def test_validate_missing_section(self) -> None:
        result = self.validator.validate_json_structure("Some text", required_sections=["Summary"])
        assert result["valid"] is False

    def test_validate_json(self) -> None:
        result = self.validator.validate_json('{"key": "value"}')
        assert result["valid"] is True

    def test_validate_json_invalid(self) -> None:
        result = self.validator.validate_json("{invalid}")
        assert result["valid"] is False

    def test_check_empty_refusal_refusal(self) -> None:
        assert self.validator.check_empty_or_refusal("I'm sorry, I cannot do that")

    def test_check_empty_refusal_ok(self) -> None:
        assert not self.validator.check_empty_or_refusal("Here is the analysis")

    def test_check_length_limits_ok(self) -> None:
        result = self.validator.check_length_limits("short", max_chars=100)
        assert result["valid"] is True

    def test_check_length_limits_exceeded(self) -> None:
        result = self.validator.check_length_limits("x" * 200, max_chars=100)
        assert result["valid"] is False


class TestResponseFormatter:
    def setup_method(self) -> None:
        self.formatter = ResponseFormatter()

    def test_format_markdown(self) -> None:
        formatted = self.formatter.format_markdown("# Hello\nWorld")
        assert "# Hello" in formatted

    def test_trim_to_token_limit(self) -> None:
        text = "word " * 100
        trimmed = self.formatter.trim_to_token_limit(text, max_tokens=10)
        assert len(trimmed.split()) <= 15  # 10 tokens + truncated message


class TestResponseStreamer:
    def setup_method(self) -> None:
        self.streamer = ResponseStreamer()

    def test_cancel(self) -> None:
        self.streamer.cancel("req1")
        assert self.streamer.is_cancelled("req1") is True

    def test_not_cancelled(self) -> None:
        assert self.streamer.is_cancelled("req2") is False
