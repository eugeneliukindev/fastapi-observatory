from __future__ import annotations

import multiprocessing
from typing import TYPE_CHECKING, final, override

from granian import Granian
from granian.constants import Interfaces
from granian.log import LogLevels

from servers.base import APP_FACTORY, Server

if TYPE_CHECKING:
    from config import GranianSettings
    from enums import LogLevel


@final
class GranianServer(Server):
    """Granian, its Python workers spawned rather than forked.

    Its master runs threads of its own before it starts the workers, and forking a multi-threaded
    process may leave a child holding a lock nobody releases.
    """

    def __init__(self, settings: GranianSettings, *, log_level: LogLevel) -> None:
        """Serve with `settings`."""
        self._settings = settings
        self._log_level = log_level

    @override
    def run(self) -> None:
        multiprocessing.set_start_method("spawn", force=True)
        Granian(
            APP_FACTORY,
            factory=True,
            interface=Interfaces.ASGI,
            address=self._settings.host,
            port=self._settings.port,
            workers=self._settings.workers,
            runtime_threads=self._settings.runtime_threads,
            blocking_threads=self._settings.blocking_threads,
            backpressure=self._settings.backpressure,
            backlog=self._settings.backlog,
            workers_lifetime=self._settings.workers_lifetime,
            workers_kill_timeout=self._settings.workers_kill_timeout,
            respawn_failed_workers=True,
            log_level=LogLevels(self._log_level.name.lower()),
            # Built here, not shared: Granian writes the level into the dictionary it is given.
            log_dictconfig={
                "version": 1,
                "disable_existing_loggers": False,
                "loggers": {
                    "_granian": {"handlers": [], "propagate": True},
                    "granian.access": {"handlers": [], "propagate": True},
                },
            },
            log_access=False,
        ).serve()
