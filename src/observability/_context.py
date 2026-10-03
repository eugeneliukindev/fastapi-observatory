from __future__ import annotations

import contextvars
from typing import Final

request_id_ctx_var: Final[contextvars.ContextVar[str]] = contextvars.ContextVar("request_id", default="")
"""The request key every record of the request carries; empty outside a request."""
