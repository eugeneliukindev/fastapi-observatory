set shell := ["bash", "-uc"]

# Compose lives beside the Kubernetes manifests, under deploy/.
export COMPOSE_FILE := "deploy/compose/docker-compose.yaml"

_cluster := "fastapi-observatory"
_kubectl := "kubectl --context k3d-" + _cluster + " --namespace " + _cluster

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
[doc("Lint and format: all, or one of ruff · flake8 · mypy · slotscheck · spelling · pyproject · dashboards")]
[arg("tool", pattern="all|ruff|flake8|mypy|slotscheck|spelling|pyproject|dashboards", help="what to run; all by default")]
lint tool="all":
    @just _lint-{{ tool }}

[group("stack")]
[doc("The stack in Docker Compose: up · down · ps · logs, then what docker compose takes")]
[arg("command", pattern="up|down|ps|logs", help="up, down, ps or logs")]
dc command *args:
    @just _dc-{{ command }} {{ args }}

alias docker-compose := dc

# The same host ports as Compose — 3000, 8000, 12345, 12347: stop one before starting the other.
[group("stack")]
[doc("The stack in a local k3d cluster: up · down · ps · logs")]
[arg("command", pattern="up|down|ps|logs", help="up, down, ps or logs")]
k3d command *args:
    @just _k3d-{{ command }} {{ args }}

[group("stack")]
[doc("Drive traffic at the app: RATE=10 DURATION=60 just traffic")]
traffic:
    ./scripts/traffic.sh

# Outside Docker, against a stack already running.
[group("stack")]
[doc("Run the app here under a server")]
[arg("kind", pattern="gunicorn|uvicorn|hypercorn|granian", help="gunicorn, uvicorn, hypercorn or granian")]
run kind:
    OBSERVATORY__SERVER__KIND={{ kind }} uv run python src

[private]
_lint-all: _lint-ruff _lint-pyproject _lint-flake8 _lint-slotscheck _lint-spelling _lint-mypy _lint-dashboards

[private]
_lint-ruff:
    uv run ruff format .
    uv run ruff check --fix --exit-non-zero-on-fix .

# The style beyond ruff: wemake-python-styleguide.
[private]
_lint-flake8:
    uv run flake8 src

[private]
_lint-mypy:
    uv run mypy src scripts

# Slots work only when every ancestor declares them: skip one, and instances get a __dict__ again
# while the memory saving disappears silently.
[private]
_lint-slotscheck:
    PYTHONPATH=src uv run slotscheck -m app -m cache -m config -m database -m dependencies -m enums -m middleware -m observability -m router -m servers

# Two checkers, because they look at different things: codespell knows "typo — fix" pairs and is
# silent on anything else, typos splits identifiers into words and sees a typo inside a name.
[private]
_lint-spelling:
    uv run codespell src
    uv run typos src

[private]
_lint-pyproject:
    uv run pyproject-fmt pyproject.toml

# Grafana has no translations for what a dashboard says: each language is a dashboard of its own,
# built from observability/grafana/source/ — the English api.json and a dictionary per language.
# It fails on a string a dictionary lacks.
[private]
_lint-dashboards:
    uv run python scripts/localize_dashboards.py

[private]
_dc-up *services:
    docker compose up --build -d {{ services }}

[private]
_dc-down *args:
    docker compose down {{ args }}

[private]
_dc-ps *args:
    docker compose ps {{ args }}

[private]
_dc-logs *services:
    docker compose logs -f {{ services }}

[private]
_k3d-up:
    k3d cluster list {{ _cluster }} >/dev/null 2>&1 || k3d cluster create {{ _cluster }} --wait \
        --port 3000:3000@loadbalancer --port 8000:8000@loadbalancer \
        --port 12345:12345@loadbalancer --port 12347:12347@loadbalancer
    docker build --tag observatory-api:dev .
    k3d image import observatory-api:dev --cluster {{ _cluster }}
    kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/kubernetes \
        | kubectl --context k3d-{{ _cluster }} apply --server-side --force-conflicts -f -
    # The tag stays `dev`: without a restart the pods keep the image they started with.
    {{ _kubectl }} rollout restart deployment/api
    {{ _kubectl }} rollout status deployment/api --timeout=5m
    {{ _kubectl }} rollout status statefulset --timeout=5m

# The data lives in the cluster: deleting it wipes everything.
[private]
_k3d-down:
    k3d cluster delete {{ _cluster }}

[private]
_k3d-ps:
    {{ _kubectl }} get pods

# Every workload carries app.kubernetes.io/name, the name of its Compose service.
[private]
_k3d-logs *services:
    {{ _kubectl }} logs -f --prefix --all-containers --max-log-requests=20 \
        --selector '{{ if services == "" { "app.kubernetes.io/name" } else { "app.kubernetes.io/name in (" + replace(services, " ", ",") + ")" } }}'
