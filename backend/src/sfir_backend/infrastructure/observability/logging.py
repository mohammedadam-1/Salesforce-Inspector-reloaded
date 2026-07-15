from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from structlog.processors import JSONRenderer

from sfir_backend.domain.observability.models import LogEvent, LogLevel

SENSITIVE_KEYS = {
    "password", "secret", "token", "api_key", "authorization",
    "jwt", "refresh_token", "access_token", "session_key",
    "private_key", "encryption_key", "client_secret",
}


def configure_logging(
    log_format: str = "json",
) -> None:
    """Configure structured logging for the application."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.dev.set_exc_info,
        _add_service_name,
        _mask_sensitive_data,
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(sort_keys=False)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_service_name(
    _logger: structlog.BoundLogger,
    _method_name: str,
    event_dict: dict,
) -> dict:
    event_dict["service"] = "sfir-backend"
    return event_dict


def _mask_sensitive_data(
    _logger: structlog.BoundLogger,
    _method_name: str,
    event_dict: dict,
) -> dict:
    for key, value in event_dict.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS) and not isinstance(value, (int, float)):
            event_dict[key] = "***"
    return event_dict


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)


class LoggingManager:
    def __init__(self) -> None:
        self._loggers: dict[str, structlog.BoundLogger] = {}

    def get_logger(self, name: str | None = None) -> structlog.BoundLogger:
        if name not in self._loggers:
            self._loggers[name or "root"] = structlog.get_logger(name)
        return self._loggers[name or "root"]

    def bind_context(self, **kwargs: Any) -> None:
        structlog.contextvars.bind_contextvars(**kwargs)

    def clear_context(self) -> None:
        structlog.contextvars.clear_contextvars()

    def to_log_event(self, _record: structlog.BoundLogger, event_dict: dict) -> LogEvent:
        return LogEvent(
            timestamp=event_dict.get("timestamp", datetime.now(tz=UTC)),
            level=LogLevel(event_dict.get("level", "info")),
            message=event_dict.get("event", ""),
            logger=event_dict.get("logger", ""),
            correlation_id=event_dict.get("correlation_id", ""),
            trace_id=event_dict.get("trace_id", ""),
            span_id=event_dict.get("span_id", ""),
            tenant_id=event_dict.get("tenant_id", ""),
            organization_id=event_dict.get("organization_id", ""),
            user_id=event_dict.get("user_id", ""),
            component=event_dict.get("component", ""),
            operation=event_dict.get("operation", ""),
            duration_ms=event_dict.get("duration_ms", 0.0),
            error=event_dict.get("error", ""),
            context=event_dict,
        )
