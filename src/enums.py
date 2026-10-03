from __future__ import annotations

import logging
from enum import IntEnum, unique
from typing import override


@unique
class LogLevel(IntEnum):
    """A log level, read from its `logging` number or its name in any case, aliases included.

    Example:
        >>> LogLevel("info"), LogLevel("WARN"), LogLevel("10"), LogLevel(40)
        (<LogLevel.INFO: 20>, <LogLevel.WARNING: 30>, <LogLevel.DEBUG: 10>, <LogLevel.ERROR: 40>)
    """

    DEBUG = logging.DEBUG
    INFO = logging.INFO  # noqa: WPS110  # the standard library named the levels
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    @classmethod
    @override
    def _missing_(cls, value: object) -> LogLevel | None:  # noqa: WPS110, WPS120  # the Enum protocol names the hook and its argument
        if not isinstance(value, str):
            return None
        spelled = value.strip().upper()
        number = int(spelled) if spelled.isdigit() else logging.getLevelNamesMapping().get(spelled)
        return next((level for level in cls if level == number), None)
