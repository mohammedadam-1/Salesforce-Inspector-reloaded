from sfir_backend.infrastructure.llm.safety_filter import SafetyFilter


class TestSafetyFilter:
    def setup_method(self) -> None:
        self.filter = SafetyFilter()

    def test_check_input_safe(self) -> None:
        result = self.filter.check_input("Explain this Apex class")
        assert result.passed is True

    def test_check_input_blocked_salesforce_connect(self) -> None:
        result = self.filter.check_input("connect to salesforce and get data")
        assert result.passed is False
        assert "restricted_action" in result.categories

    def test_check_input_blocked_parse_metadata(self) -> None:
        result = self.filter.check_input("parse metadata from salesforce")
        assert result.passed is False

    def test_check_input_blocked_build_graph(self) -> None:
        result = self.filter.check_input("build a dependency graph")
        assert result.passed is False

    def test_check_input_blocked_calculate_impact(self) -> None:
        result = self.filter.check_input("calculate impact analysis")
        assert result.passed is False

    def test_check_output_safe(self) -> None:
        result = self.filter.check_output("This is a safe response")
        assert result.passed is True

    def test_check_output_blocked(self) -> None:
        result = self.filter.check_output("You can connect to salesforce using...")
        assert result.passed is False

    def test_check_context_safe(self) -> None:
        result = self.filter.check_context({"query": "explain apex"})
        assert result.passed is True

    def test_check_context_blocked(self) -> None:
        result = self.filter.check_context({"query": "connect to salesforce and modify"})
        assert result.passed is False

    def test_add_blocked_pattern(self) -> None:
        self.filter.add_blocked_pattern(r"(?i)prohibited_term")
        result = self.filter.check_input("this has a prohibited_term")
        assert result.passed is False

    def test_add_allowed_domain(self) -> None:
        self.filter.add_allowed_domain("example.com")
        assert "example.com" in self.filter._allowed_domains
