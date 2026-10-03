from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Final

APP_FACTORY: Final = "app:create_app"
"""The application factory, called in each process that serves."""


class Server(ABC):
    """A server running the application from `APP_FACTORY`, its own log lines written as JSON lines."""

    @abstractmethod
    def run(self) -> None:
        """Serve until stopped, in the calling process."""
