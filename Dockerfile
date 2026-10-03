FROM ghcr.io/astral-sh/uv:0.12.7 AS uv

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies in a separate stage: a code change does not download them again.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --create-home observatory && mkdir /data && chown observatory /data
COPY --from=build /app/.venv /app/.venv
COPY src /app/src
# Stable OpenTelemetry names for HTTP and databases: `http.route` instead of the raw path and
# `db.system.name` instead of `db.system`. They can only be chosen with an environment variable —
# the instrumentations read it themselves, once, on the first `instrument()`.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    OTEL_SEMCONV_STABILITY_OPT_IN=http,database
USER observatory
WORKDIR /data
EXPOSE 8000
CMD ["python", "/app/src"]
