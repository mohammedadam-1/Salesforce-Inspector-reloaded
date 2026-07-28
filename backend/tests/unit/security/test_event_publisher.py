

from sfir_backend.domain.security.models import SecurityEventType
from sfir_backend.infrastructure.security.security_event_publisher import (
    SecurityEventPublisher,
)


class TestSecurityEventPublisher:
    def setup_method(self) -> None:
        self.publisher = SecurityEventPublisher()

    def test_subscribe(self) -> None:
        def handler(e):
            return None
        self.publisher.subscribe(SecurityEventType.USER_LOGIN, handler)
        assert SecurityEventType.USER_LOGIN.value in self.publisher._subscribers

    def test_subscribe_all(self) -> None:
        def handler(e):
            return None
        self.publisher.subscribe_all(handler)
        assert len(self.publisher._subscribers) == len(SecurityEventType)

    async def test_publish_calls_handler(self) -> None:
        called = []

        async def handler(event):
            called.append(event)

        self.publisher.subscribe(SecurityEventType.USER_LOGIN, handler)

        from sfir_backend.domain.security.models import SecurityEvent
        event = SecurityEvent.create(SecurityEventType.USER_LOGIN)
        await self.publisher.publish(event)
        assert len(called) == 1

    def test_unsubscribe(self) -> None:
        def handler(e):
            return None
        self.publisher.subscribe(SecurityEventType.USER_LOGIN, handler)
        self.publisher.unsubscribe(SecurityEventType.USER_LOGIN, handler)
        assert handler not in self.publisher._subscribers[
            SecurityEventType.USER_LOGIN.value
        ]

    async def test_publish_with_metrics(self) -> None:
        from unittest.mock import MagicMock
        mock_metrics = MagicMock()
        publisher = SecurityEventPublisher(metrics_collector=mock_metrics)

        event = type("Event", (), {
            "event_type": SecurityEventType.USER_LOGIN,
            "severity": type("sev", (), {"value": "info"})(),
            "category": type("cat", (), {"value": "auth"})(),
        })()

        await publisher.publish(event)
        mock_metrics.record_custom.assert_called()
