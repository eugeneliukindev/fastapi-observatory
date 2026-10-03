from __future__ import annotations

from typing import TYPE_CHECKING, final, override

import uvicorn

from servers.base import APP_FACTORY, Server

if TYPE_CHECKING:
    from config import UvicornSettings
    from enums import LogLevel


@final
class UvicornServer(Server):
    """Uvicorn: a single process, or a supervisor spawning workers."""

    def __init__(self, settings: UvicornSettings, *, log_level: LogLevel) -> None:
        """Serve with `settings`."""
        self._settings = settings
        self._log_level = log_level

    @override
    def run(self) -> None:
        uvicorn.run(
            APP_FACTORY,
            factory=True,
            host=self._settings.host,
            port=self._settings.port,
            workers=self._settings.workers,
            timeout_keep_alive=self._settings.timeout_keep_alive,
            timeout_graceful_shutdown=self._settings.timeout_graceful_shutdown,
            limit_concurrency=self._settings.limit_concurrency,
            limit_max_requests=self._settings.limit_max_requests,
            backlog=self._settings.backlog,
            log_config=None,
            log_level=self._log_level.name.lower(),
            access_log=False,
        )
