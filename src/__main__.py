from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from config import GranianSettings, GunicornSettings, HypercornSettings, Settings, UvicornSettings
from database import prepare_database
from observability import configure_logging
from servers import GranianServer, GunicornServer, HypercornServer, UvicornServer

if TYPE_CHECKING:
    from servers import Server


def main() -> None:
    """Read the settings, set up logging and the database file, and run the chosen server."""
    settings = Settings()
    configure_logging(settings.log_level)
    prepare_database(settings.db.path)
    _build_server(settings).run()


def _build_server(settings: Settings) -> Server:
    """Build the server its settings name."""
    match settings.server:
        case GranianSettings():
            return GranianServer(settings.server, log_level=settings.log_level)
        case GunicornSettings():
            return GunicornServer(settings.server, log_level=settings.log_level)
        case HypercornSettings():
            return HypercornServer(settings.server, log_level=settings.log_level)
        case UvicornSettings():
            return UvicornServer(settings.server, log_level=settings.log_level)
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    main()
