from __future__ import annotations

import sqlite3
from typing import Annotated

import httpx
from fastapi import Depends, Request

from cache import MemoryCache
from config import Settings


async def _http(request: Request) -> httpx.AsyncClient:
    http: httpx.AsyncClient = request.app.state.http
    return http


async def _cache(request: Request) -> MemoryCache[dict[str, object]]:
    cache: MemoryCache[dict[str, object]] = request.app.state.cache
    return cache


async def _database(request: Request) -> sqlite3.Cursor:
    # Only cursors are traced: `execute` on the connection itself bypasses the instrumentation.
    # The dependency is async so it runs on the event loop thread — the thread the connection belongs to.
    cursor: sqlite3.Cursor = request.app.state.database.cursor()
    return cursor


async def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


Http = Annotated[httpx.AsyncClient, Depends(_http)]
"""The JSONPlaceholder client, with its base address."""

Cache = Annotated[MemoryCache[dict[str, object]], Depends(_cache)]
"""The posts recently read, by key."""

Database = Annotated[sqlite3.Cursor, Depends(_database)]
"""A traced cursor of the connection opened for the lifetime of the application."""

SettingsDep = Annotated[Settings, Depends(_settings)]
"""The settings the application was built with."""
