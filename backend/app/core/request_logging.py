"""Per-request access logging with a correlation id.

Every HTTP request is assigned a request id that is bound to the structlog
context, so *all* log lines emitted while it is handled — the access log here,
the audit entries, the PayPal calls, the agent decisions, the email
notifications — carry the same ``request_id`` and can be traced as one
transaction. The id is also returned in the ``X-Request-Id`` response header so
a client (or a demo viewer) can quote it.

This is a pure ASGI middleware on purpose: it runs in the same task as the
downstream app, so the context it binds actually reaches the endpoint and the
services beneath it (a ``BaseHTTPMiddleware`` would not propagate contextvars
reliably).
"""

from __future__ import annotations

import time
import uuid

import structlog

logger = structlog.get_logger("request")


class RequestLoggingMiddleware:
    """Logs the start and completion of every HTTP request."""

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex[:16]
        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client")
        client_host = client[0] if client else None

        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=method, path=path
        )
        start = time.perf_counter()
        logger.info("request.started", client=client_host)

        status_code = 500

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.exception("request.failed", duration_ms=duration_ms)
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            # One line per request, whatever the outcome — the access log.
            logger.info("request.completed", status_code=status_code, duration_ms=duration_ms)
        finally:
            structlog.contextvars.clear_contextvars()


def _incoming_request_id(scope) -> str | None:
    """Honour a client-supplied X-Request-Id so a trace can span the stack."""
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1").strip()
            # Bound length, and only safe characters, so a header cannot inject
            # junk into every log line.
            if candidate and len(candidate) <= 64 and candidate.replace("-", "").isalnum():
                return candidate
    return None
