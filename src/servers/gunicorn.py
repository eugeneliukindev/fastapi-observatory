from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from gunicorn.app.base import BaseApplication

from app import create_app
from observability import GunicornJsonLogger
from servers.base import Server

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI

    from config import GunicornSettings
    from enums import LogLevel


@final
class GunicornServer(Server):
    """Gunicorn: a master forking Uvicorn workers, each building the application after the fork.

    Not `preload_app`: the application starts threads, and a thread does not survive a fork while
    its locks do — a worker would inherit exporters with no thread to drain them.
    """

    def __init__(self, settings: GunicornSettings, *, log_level: LogLevel) -> None:
        """Configure Gunicorn from `settings`."""
        self._config: Mapping[str, object] = {
            "bind": settings.address,
            "workers": settings.workers,
            "worker_class": "uvicorn_worker.UvicornWorker",
            "preload_app": False,
            "timeout": settings.timeout,
            "graceful_timeout": settings.graceful_timeout,
            "keepalive": settings.keepalive,
            "max_requests": settings.max_requests,
            "max_requests_jitter": settings.max_requests_jitter,
            "backlog": settings.backlog,
            "logger_class": GunicornJsonLogger,
            "loglevel": log_level.name.lower(),
            "accesslog": None,
        }

    @override
    def run(self) -> None:
        _Application(self._config).run()


@final
class _Application(BaseApplication):
    """Gunicorn configured in code, building the application in each worker."""

    def __init__(self, config: Mapping[str, object]) -> None:
        self._config = config
        super().__init__()

    @override
    def load_config(self) -> None:
        for name, chosen in self._config.items():
            self.cfg.set(name, chosen)

    @override
    def load(self) -> FastAPI:
        return create_app()
