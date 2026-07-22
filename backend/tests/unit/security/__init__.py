import pytest

pytest.register_assert_rewrite("tests.unit.security.test_models")
pytest.register_assert_rewrite("tests.unit.security.test_encryption")
pytest.register_assert_rewrite("tests.unit.security.test_authorization")
pytest.register_assert_rewrite("tests.unit.security.test_audit")
pytest.register_assert_rewrite("tests.unit.security.test_rate_limiter")
pytest.register_assert_rewrite("tests.unit.security.test_abuse")
pytest.register_assert_rewrite("tests.unit.security.test_session_security")
pytest.register_assert_rewrite("tests.unit.security.test_policy")
pytest.register_assert_rewrite("tests.unit.security.test_event_publisher")
pytest.register_assert_rewrite("tests.unit.security.test_secrets_manager")
pytest.register_assert_rewrite("tests.unit.security.test_security_manager")