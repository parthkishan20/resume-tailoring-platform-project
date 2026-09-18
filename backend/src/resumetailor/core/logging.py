"""Structured logging, and a request id that travels with the request.

Before this module there was no logging configuration anywhere in the backend.
The one logger in the codebase (`yaml_utils`) emitted warnings into a root
logger with no handler, so every one of them was dropped, and every
`except Exception` turned a traceback into a string and threw the traceback
away. Production failures were unattributable. That is PLAN.md D-52.

What is here:

* :data:`request_id_var`, a ``ContextVar`` set by the middleware and read by
  the formatter. Anything logged while handling a request carries the id,
  including from a worker thread started with ``asyncio.to_thread``, because
  context is copied into the thread.
* :class:`JsonFormatter`, one JSON object per line on stdout.
* :func:`configure_logging`, which actually attaches a handler — to the root
  logger, so third-party loggers are captured too — and hands uvicorn's three
  loggers the same one.

``configure_logging`` is idempotent. It is called from the app factory rather
than from the lifespan so that logging is configured before anything the
factory itself does can fail.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from resumetailor.core.config import Settings

#: The id of the request being handled on this task, or "-" outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

#: Attributes `logging.LogRecord` sets itself. Anything else on a record came
#: from an `extra={...}` at the call site and belongs in the JSON output.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | frozenset({"message", "asctime", "taskName"})

_TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s"


class RequestIdFilter(logging.Filter):
    """Put the current request id on every record, for either formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, message, request id.

    Any keyword passed as ``extra={...}`` at the call site is merged in at the
    top level, so a field can be grepped or indexed without parsing the message.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_var.get()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "request_id":
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Attach a single stdout handler to the root logger.

    Safe to call more than once: the handler is tagged and replaced rather than
    stacked, so a second call does not double every line.
    """
    formatter: logging.Formatter = (
        JsonFormatter()
        if settings.LOG_FORMAT == "json"
        else logging.Formatter(_TEXT_FORMAT)
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    handler.set_name("resumetailor")

    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.get_name() == "resumetailor"]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())

    # uvicorn installs its own handlers at import time and sets propagate=False.
    # Hand them back to the root handler so every line in the process has the
    # same shape and carries the request id.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
