from __future__ import annotations

import asyncio
import math
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Final, NoReturn

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict

from dependencies import Cache, Database, Http, SettingsDep
from observability import logger

_SAVE_POST: Final = """
INSERT INTO posts (id, user_id, title, body) VALUES (?, ?, ?, ?)
ON CONFLICT (id) DO UPDATE SET saved_at = CURRENT_TIMESTAMP
"""

_ADD_POST: Final = "INSERT INTO posts (user_id, title, body) VALUES (?, ?, ?) RETURNING id"

_RECENT_POSTS: Final = "SELECT id, user_id, title, body FROM posts ORDER BY saved_at DESC LIMIT 20"

_CACHE_TTL_SECONDS: Final = 30  # short on purpose: cache misses happen even under light traffic
_TEMPLATES: Final = Jinja2Templates(directory=Path(__file__).parent / "templates")

_MAX_PRIMES_BELOW: Final = 2_000_000  # a few seconds of pure Python: enough to stand out in a profile
_REPORT_PRIMES_BELOW: Final = 100_000

_tracer = trace.get_tracer(__name__)
router = APIRouter()


class _PostDraft(BaseModel):
    """A post as the client writes it: the id is given by the database."""

    # The schema keeps the public name: the underscore only says no other module uses the class.
    model_config = ConfigDict(title="PostDraft")

    user_id: int
    title: str
    body: str


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def show_page(request: Request, settings: SettingsDep) -> HTMLResponse:
    """Serve the page."""
    return _TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {"faro_url": settings.obs.faro.collector_url, "environment": settings.obs.environment.value},
    )


@router.get("/health", include_in_schema=False)
async def check_health() -> dict[str, str]:
    """Answer the liveness probe."""
    return {"status": "ok"}


@router.get("/api/posts/{post_id}")
async def get_post(post_id: int, http: Http, cache: Cache, database: Database) -> dict[str, object]:
    """Read a post: from the cache, on a miss from JSONPlaceholder, then save it and cache it."""
    cached = cache.get(f"post:{post_id}")
    if cached is not None:
        return cached

    response = await http.get(f"/posts/{post_id}")
    if response.status_code == HTTPStatus.NOT_FOUND:
        raise HTTPException(HTTPStatus.NOT_FOUND, f"post {post_id} not found")
    post: dict[str, object] = response.json()

    # A local file answers in microseconds: the query runs right on the event loop, without a thread.
    database.execute(_SAVE_POST, (post["id"], post["userId"], post["title"], post["body"]))
    cache.set(f"post:{post_id}", post, ttl_seconds=_CACHE_TTL_SECONDS)
    logger.info("post fetched from JSONPlaceholder and cached", extra={"post_id": post_id})
    return post


@router.get("/api/posts")
async def list_posts(database: Database) -> list[dict[str, object]]:
    """List the most recently read posts."""
    return [dict(row) for row in database.execute(_RECENT_POSTS)]


@router.post("/api/posts", status_code=HTTPStatus.CREATED)
async def add_post(draft: _PostDraft, database: Database) -> dict[str, object]:
    """Save the post sent in the request body."""
    post = dict(database.execute(_ADD_POST, (draft.user_id, draft.title, draft.body)).fetchone()) | draft.model_dump()
    logger.info("post created", extra={"post_id": post["id"]})
    return post


@router.get("/api/cpu")
async def burn_cpu(below: Annotated[int, Query(le=_MAX_PRIMES_BELOW)] = 200_000) -> dict[str, int]:
    """Count the primes below `below`, on the event loop."""
    return {"primes": _count_primes(below)}


@router.get("/api/report/{post_id}")
async def build_report(post_id: int, http: Http, cache: Cache, database: Database) -> dict[str, object]:
    """Do everything at once: the post and its comments in parallel, then CPU work."""
    post, comments = await asyncio.gather(
        get_post(post_id, http, cache, database),
        http.get(f"/posts/{post_id}/comments"),
    )
    return {"title": post["title"], "comments": len(comments.json()), "primes": _count_primes(_REPORT_PRIMES_BELOW)}


@router.get("/api/fail", response_model=None)
async def fail() -> NoReturn:
    """Raise an unhandled error."""
    raise RuntimeError("failure requested on purpose")


def _count_primes(below: int) -> int:
    """Count the primes below `below` by trial division — expensive on purpose.

    Example:
        >>> _count_primes(30)
        10
    """
    with _tracer.start_as_current_span("count primes"):
        return sum(1 for number in range(2, below) if _is_prime(number))


def _is_prime(number: int) -> bool:
    return all(number % divisor for divisor in range(2, math.isqrt(number) + 1))
