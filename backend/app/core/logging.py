"""Structured logging.

Logs are keyed by deal id and state so a money movement can be traced end to
end. Nothing secret is ever logged: a processor drops known-sensitive keys
on the way out, as a backstop to not logging them in the first place.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# Dropped from every event, whatever the call site passed.
SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "token",
        "authorization",
        "password",
        "password_hash",
        "client_secret",
        "paypal_client_secret",
        "api_key",
        "anthropic_api_key",
        "jwt_secret",
        "secret",
        "payload",
    }
)
REDACTED = "[redacted]"


def _redact(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_deal_context(deal_id: object, state: object = None) -> None:
    """Attach deal identity to every subsequent log line in this task."""
    structlog.contextvars.bind_contextvars(deal_id=str(deal_id))
    if state is not None:
        structlog.contextvars.bind_contextvars(deal_state=str(state))


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
