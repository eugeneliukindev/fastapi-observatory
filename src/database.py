from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

# The example has no migrations: the table is created on startup.
_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    saved_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def prepare_database(path: Path) -> None:
    """Switch the file to WAL and create the table.

    Not safe from several processes at once: switching the journal does not wait out a busy lock,
    so one of them fails with `database is locked`.
    """
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(_SCHEMA)
