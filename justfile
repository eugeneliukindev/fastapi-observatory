set shell := ["bash", "-uc"]

[doc("All command information")]
default:
    @just --list --unsorted --list-heading $'Available commands…\n'

[group("setup")]
[doc("Install the full dev environment")]
install:
    uv sync

[group("setup")]
[doc("Install git hooks via prek")]
hooks:
    uv run prek install

[group("lint")]
[doc("Format all code")]
fmt *p=".":
    uv run ruff format {{ p }}

[group("lint")]
[doc("Lint and autofix")]
lint *p=".":
    uv run ruff check --fix --exit-non-zero-on-fix {{ p }}

[group("lint")]
[doc("Static type check")]
typecheck *p="src scripts":
    uv run mypy {{ p }}

[group("lint")]
[doc("Lint the style beyond ruff")]
lint-style *p="src":
    uv run flake8 {{ p }}

# Slots work only when every ancestor declares them: skip one, and instances get a __dict__ again
# while the memory saving disappears silently.
[group("lint")]
[doc("Check that `__slots__` really work")]
lint-slots:
    PYTHONPATH=src uv run slotscheck -m app -m cache -m config -m database -m dependencies -m enums -m middleware -m observability -m router -m servers

# Two checkers, because they look at different things: codespell knows "typo — fix" pairs and is
# silent on anything else, typos splits identifiers into words and sees a typo inside a name.
[group("lint")]
[doc("Spell-check the sources")]
lint-spelling *p="src":
    uv run codespell {{ p }}
    uv run typos {{ p }}

[group("lint")]
[doc("Format pyproject.toml")]
fmt-pyproject:
    uv run pyproject-fmt pyproject.toml

# Grafana has no translations for what a dashboard says: the dashboard holds its rows once per
# language, built from observability/grafana/source/ — the English api.json and a dictionary each.
[group("lint")]
[doc("Build the dashboard in every language; fails on a string a dictionary lacks")]
dashboards:
    uv run python scripts/localize_dashboards.py

[group("ci")]
[doc("CI-equivalent aggregate gate")]
check: fmt fmt-pyproject lint lint-style lint-slots lint-spelling typecheck dashboards

# Outside Docker, against a stack already running.
[group("infra")]
[doc("Run the app here under a server: just run gunicorn | uvicorn | hypercorn | granian")]
run kind:
    OBSERVATORY__SERVER__KIND={{ kind }} uv run python src

[group("infra")]
[doc("Build and start the app with the whole stack")]
up:
    docker compose up --build -d

[group("infra")]
[doc("Stop everything; `just down -v` also drops the data")]
down *args:
    docker compose down {{ args }}

[group("infra")]
[doc("Follow logs, optionally of specific services")]
logs *services:
    docker compose logs -f {{ services }}

[group("infra")]
[doc("Show stack status")]
ps:
    docker compose ps

[group("infra")]
[doc("Drive traffic at the app: RATE=10 DURATION=60 just traffic")]
traffic:
    ./scripts/traffic.sh
