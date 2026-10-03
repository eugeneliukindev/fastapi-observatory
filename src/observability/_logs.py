from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, final, override

from gunicorn.glogging import Logger
from opentelemetry.trace import format_span_id, format_trace_id, get_current_span

from observability._context import request_id_ctx_var

if TYPE_CHECKING:
    from gunicorn.config import Config

logger: Final = logging.getLogger("observatory")
"""The logger of our own code; `caller` tells where a line is from."""

_OUTSIDE_TRACE: Final = ""

_OWN_FIELDS: Final = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "color_message",  # uvicorn repeats its message with terminal colours
}


@final
class _JsonFormatter(logging.Formatter):
    """A log line as one JSON object: fields stay fields instead of becoming text."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        written: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
            "caller": f"{record.module}:{record.funcName}:{record.lineno}",
        }
        written.update({name: given for name, given in record.__dict__.items() if name not in _OWN_FIELDS})

        if record.exc_info:
            # Three fields rather than text: lines are filtered by the kind of failure.
            error = record.exc_info[1]
            written["error_type"] = type(error).__qualname__ if error else ""
            written["error_message"] = str(error) if error else ""
            written["error_stack"] = self.formatException(record.exc_info)

        # An unserializable value is shown as its repr: the record matters more than one field.
        return json.dumps(written, default=str, ensure_ascii=False, separators=(",", ":"))


def contextualize_logging() -> None:
    """Stamp every record with the request key and the current trace and span; a repeat call changes nothing."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, "contextualizes", False):
        return

    def make_record(*args: object, **kwargs: object) -> logging.LogRecord:  # noqa: WPS430  # the closure remembers the previous factory
        record = previous(*args, **kwargs)
        record.request_id = request_id_ctx_var.get()
        found = get_current_span().get_span_context()
        record.trace_id = format_trace_id(found.trace_id) if found.is_valid else _OUTSIDE_TRACE
        record.span_id = format_span_id(found.span_id) if found.is_valid else _OUTSIDE_TRACE
        return record

    make_record.contextualizes = True  # type: ignore[attr-defined]  # the mark a repeat call looks for
    logging.setLogRecordFactory(make_record)


def configure_logging(level: int) -> None:
    """Make this process write JSON lines to stdout, ours from `level`; a repeat call stacks nothing."""
    # Does nothing when the root already has a handler.
    logging.basicConfig(stream=sys.stdout)
    format_as_json(*logging.getLogger().handlers)
    # Only our own logger: the libraries keep the root's WARNING.
    logger.setLevel(level)


def format_as_json(*handlers: logging.Handler) -> None:
    """Make `handlers` write JSON lines."""
    for writer in handlers:
        writer.setFormatter(_JsonFormatter())


@final
class GunicornJsonLogger(Logger):
    """Gunicorn's logger, whose handlers and the root's write JSON lines."""

    @override
    def setup(self, cfg: Config) -> None:
        """Set the handlers up and make them write JSON lines; a repeat call stacks nothing."""
        super().setup(cfg)
        configure_logging(self.loglevel)
        format_as_json(*self.error_log.handlers, *self.access_log.handlers)
