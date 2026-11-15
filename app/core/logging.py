"""Lightweight structured logging helpers.

The application logs one line per request with method, path, status, duration
and a request id that is also returned to the client (``X-Request-ID``).
"""

from __future__ import annotations

import contextvars
import logging
import sys
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_CONFIGURED = False


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once, writing to stdout."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    _CONFIGURED = True


def new_request_id() -> str:
    """Generate a short correlation id."""
    return uuid.uuid4().hex


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (keeps ``logging.getLogger`` import-free in modules)."""
    return logging.getLogger(name)
