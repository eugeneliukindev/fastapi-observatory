set shell := ["bash", "-uc"]

# Compose lives beside the Kubernetes manifests, under deploy/.
export COMPOSE_FILE := "deploy/compose/docker-compose.yaml"

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

# Grafana has no translations for what a dashboard says: each language is a dashboard of its own,
# built from observability/grafana/source/ — the English api.json and a dictionary per language.
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

# The same host ports as Compose — 3000, 8000, 12345, 12347: stop one before starting the other.
[group("kubernetes")]
[doc("Run the stack in a local k3d cluster, building and importing the application's image")]
k8s-up:
    k3d cluster list observatory >/dev/null 2>&1 || k3d cluster create observatory --wait \
        --port 3000:3000@loadbalancer --port 8000:8000@loadbalancer \
        --port 12345:12345@loadbalancer --port 12347:12347@loadbalancer
    docker build --tag observatory-api:dev .
    k3d image import observatory-api:dev --cluster observatory
    kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/kubernetes \
        | kubectl --context k3d-observatory apply --server-side --force-conflicts -f -
    # The tag stays `dev`: without a restart the pods keep the image they started with.
    kubectl --context k3d-observatory --namespace observatory rollout restart deployment/api
    kubectl --context k3d-observatory --namespace observatory rollout status deployment/api --timeout=5m
    kubectl --context k3d-observatory --namespace observatory rollout status statefulset --timeout=5m

[group("kubernetes")]
[doc("Delete the k3d cluster with everything in it")]
k8s-down:
    k3d cluster delete observatory
