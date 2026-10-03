from __future__ import annotations

import logging
from typing import TYPE_CHECKING, final, override

from hypercorn.config import Config
from hypercorn.run import run

from servers.base import APP_FACTORY, Server

if TYPE_CHECKING:
    from config import HypercornSettings
    from enums import LogLevel


@final
class HypercornServer(Server):
    """Hypercorn: a master spawning workers.

    A worker that dies stops the whole server: Hypercorn restarts only the workers that exit cleanly.
    """

    def __init__(self, settings: HypercornSettings, *, log_level: LogLevel) -> None:
        """Configure Hypercorn from `settings`."""
        self._config = Config()
        # A call in the path: Hypercorn evaluates it and serves what the factory returns.
        self._config.application_path = f"{APP_FACTORY}()"
        self._config.bind = [settings.address]
        self._config.workers = settings.workers
        self._config.keep_alive_timeout = settings.keep_alive_timeout
        self._config.graceful_timeout = settings.graceful_timeout
        self._config.max_requests = settings.max_requests
        self._config.max_requests_jitter = settings.max_requests_jitter
        self._config.backlog = settings.backlog
        self._config.errorlog = logging.getLogger("hypercorn.error")
        self._config.accesslog = None
        self._config.logconfig_dict = {
            "version": 1,
            "disable_existing_loggers": False,
            "loggers": {"hypercorn.error": {"level": log_level.name}},
        }

    @override
    def run(self) -> None:
        run(self._config)
