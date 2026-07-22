import uuid

from sfir_backend.domain.security.models import (
    AbusePatternType,
    SecurityEventType,
)
from sfir_backend.infrastructure.security.abuse_detection import AbuseDetector


class TestAbuseDetector:
    def setup_method(self) -> None:
        self.detector = AbuseDetector()

    def test_default_patterns_registered(self) -> None:
        assert len(self.detector._patterns) == 4

    def test_single_event_no_trigger(self) -> None:
        result = self.detector.record_event(
            user_id=uuid.uuid4(),
            ip_address="192.168.1.1",
            event_type=SecurityEventType.USER_LOGIN_FAILED,
        )
        assert len(result) == 0

    def test_brute_force_pattern_triggered(self) -> None:
        user_id = uuid.uuid4()
        for _ in range(12):
            result = self.detector.record_event(
                user_id=user_id,
                ip_address="192.168.1.1",
                event_type=SecurityEventType.USER_LOGIN_FAILED,
            )
        triggered_types = [p.pattern_type for p in result]
        assert AbusePatternType.BRUTE_FORCE in triggered_types

    def test_cleanup_removes_old_events(self) -> None:
        self.detector.record_event(
            user_id=uuid.uuid4(),
            ip_address="10.0.0.1",
            event_type=SecurityEventType.USER_LOGIN,
        )
        assert len(self.detector._event_store) > 0

        self.detector.cleanup(max_age_seconds=0)
        for events in self.detector._event_store.values():
            assert len(events) == 0

    def test_different_users_independent(self) -> None:
        for _ in range(15):
            self.detector.record_event(
                user_id=uuid.uuid4(),
                ip_address="10.0.0.1",
                event_type=SecurityEventType.USER_LOGIN_FAILED,
            )

        result = self.detector.record_event(
            user_id=uuid.uuid4(),
            ip_address="10.0.0.2",
            event_type=SecurityEventType.USER_LOGIN_FAILED,
        )
        assert len(result) == 0
