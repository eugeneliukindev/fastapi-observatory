<div align="center">

# 🔭 fastapi-observatory

**A FastAPI service under a full observability stack — metrics · logs · traces · profiles · browser — in one `docker compose up`, or in Kubernetes.**

![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.142-009688?logo=fastapi&logoColor=white)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-1.45-425CC7?logo=opentelemetry&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-13.2-F46800?logo=grafana&logoColor=white)
![VictoriaMetrics](https://img.shields.io/badge/VictoriaMetrics-1.153-621773?logo=victoriametrics&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-k3d-326CE5?logo=kubernetes&logoColor=white)

[Quick start](#-quick-start) · [Architecture](#-architecture) · [Dashboard](#-dashboard) ·
[Signal to signal](#-from-signal-to-signal) · [Servers](#-servers) · [Logging](#-logging) ·
[Metrics](#-metrics) · [Configuration](#-configuration) · [Kubernetes](#%EF%B8%8F-kubernetes) ·
[Development](#-development)

![The dashboard](docs/screenshots/01-dashboard-overview.png)

</div>

The handlers have no business logic: they only touch what shows up in Grafana — an in-memory
cache, SQLite, an external API ([JSONPlaceholder](https://jsonplaceholder.typicode.com)) and the
CPU. One application, four servers: **Gunicorn · Uvicorn · Hypercorn · Granian**.

## 🚀 Quick start

Needs Docker and [just](https://just.systems); [uv](https://docs.astral.sh/uv/) only to work on the
code.

```sh
just dc up     # docker compose up --build -d; just k3d up for Kubernetes
just traffic   # RATE=10 DURATION=60 just traffic
```

Both ways to run it live in [`deploy/`](deploy):
[`compose/docker-compose.yaml`](deploy/compose/docker-compose.yaml) and the Kubernetes manifests in
[`kubernetes/`](deploy/kubernetes). The `just` recipes point Compose at its file; by hand it is
`docker compose -f deploy/compose/docker-compose.yaml …`. The same stack runs in a local Kubernetes
cluster with `just k3d up` — see [Kubernetes](#%EF%B8%8F-kubernetes).

| what | where |
|---|---|
| 🐍 the page, the API, `/docs` | http://localhost:8000 |
| 📊 Grafana, no login | http://localhost:3000 |
| 🔀 Alloy: components, live debugging | http://localhost:12345 |

> [!TIP]
> Every button on the page is a trace that starts in the browser. `just dc down -v` wipes the data;
> `just run granian` runs the application outside Docker against the running stack.

![The application's page](docs/screenshots/00-page.png)

## 🧭 Architecture

```mermaid
flowchart LR
    subgraph sources["Sources"]
        direction TB
        browser["🌐 Browser<br/>Faro SDK"]
        api["🐍 api<br/>a server and its workers"]
        docker[("🐳 Docker · ☸️ Kubernetes<br/>container stdout")]
    end

    alloy{{"Alloy<br/>the only collector"}}

    subgraph storage["Storage"]
        direction TB
        vm[("VictoriaMetrics<br/>metrics")]
        loki[("Loki<br/>logs")]
        tempo[("Tempo<br/>traces")]
        pyroscope[("Pyroscope<br/>profiles")]
    end

    grafana["📊 Grafana"]

    api -- "OTLP: traces, metrics<br/>CPU profiles" --> alloy
    api -- "JSON lines" --> docker
    docker -- "logs" --> alloy
    browser -- "Faro: logs, errors,<br/>Web Vitals, spans" --> alloy
    alloy --> vm & loki & tempo & pyroscope
    tempo -. "span metrics" .-> vm
    storage --> grafana

    classDef metrics fill:#B877D9,stroke:#8F3BB8,color:#111
    classDef logs fill:#73BF69,stroke:#56A64B,color:#111
    classDef traces fill:#5794F2,stroke:#3274D9,color:#111
    classDef profiles fill:#FF9830,stroke:#FA6400,color:#111
    classDef collector fill:#F55F3E,stroke:#C4162A,color:#fff
    classDef ui fill:#F46800,stroke:#C34F00,color:#fff
    classDef source fill:#E8E8E8,stroke:#9E9E9E,color:#111
    class vm metrics
    class loki logs
    class tempo traces
    class pyroscope profiles
    class alloy collector
    class grafana ui
    class browser,api,docker source
```

| signal | from the process | through Alloy | stored in |
|---|---|---|---|
| 📈 metrics | OTLP gRPC every 15 s, each worker its own `service.instance.id` | `otelcol.receiver.otlp` → Prometheus model | VictoriaMetrics, 14 days |
| 📜 logs | one JSON object per line on stdout; the browser's through Faro | `loki.source.docker` or `loki.source.kubernetes` · `faro.receiver`: `lvl` a label, ids structured metadata | Loki |
| 🧵 traces | OTLP gRPC; the browser's through Faro | `otelcol.receiver.otlp` · `faro.receiver` | Tempo, 3 days |
| 🔥 profiles | Pyroscope SDK, samples tagged with the root span | `pyroscope.receive_http` | Pyroscope |

> [!NOTE]
> A memory limiter is first in Alloy's line: under pressure it refuses data instead of the
> collector being killed. Tempo derives span metrics and Alloy the service graph, both written to
> VictoriaMetrics.

Alloy draws its own pipeline at http://localhost:12345, with the live rate on every edge: what
comes in, which stage it passes, where it goes.

![Alloy's pipeline](docs/screenshots/20-alloy-pipeline.png)

## 📊 Dashboard

**FastAPI: traffic, latency, errors, traces, logs, profile** — nothing hardcoded: data sources,
service, routes, method, host and thresholds are variables. A series on the route, status code
and exception panels links to its traces or log lines — click it; a route in the Routes table
narrows the whole dashboard to itself, as Grafana's own operations tables do.

| where | variables |
|---|---|
| the top of the dashboard | Metrics · Logs · Traces · Profiles · Service · Routes matching · Route · Method · Host · Apdex satisfied · Apdex tolerated · Slow trace |
| the Status codes row | Status codes — the classes its panel draws, 4xx and 5xx at first |
| the Latency row | Percentiles — P50, P95 and P99, P95 at first |
| the Workers row | Percentiles — the same, for the workers' latency |
| the Profiling row | Profile type |
| the Traces row | Show — slow or failed at first, slow, failed or all |
| the Logs row | Levels — DEBUG, INFO, WARNING, ERROR, CRITICAL, all at first |

A row's picker reshapes its panel and nothing else: every status class at once, every percentile
of the service and of each route.

<p>
<img src="docs/screenshots/25-status-codes-all.png" width="49%" alt="RPS of every status class, in total and by route">
<img src="docs/screenshots/26-latency-percentiles.png" width="49%" alt="P50, P95 and P99, in total and by route">
</p>

The order is the order of an investigation: is the service fine, which requests suffer, is the
promise kept, why, and the evidence. Groups nest — a dashboard in the v2 schema, the one with rows inside rows.

| group | row | what |
|---|---|---|
| top | | RPS · 5xx ratio · P95 now, with sparklines · Apdex · instances · workers · every route with its trend, requests, 2xx, 3xx, 4xx, 5xx, mean, P50, P95 and P99 |
| Requests | Traffic | RPS by route, the total over them and the total yesterday |
| | Status codes | RPS of the classes picked, a total per class and a line per route and code |
| | Latency | the percentiles picked, of the service, yesterday and of each route · the heatmap |
| | Exceptions | by route and type · each message with its type, route and count — from the log |
| | Payload, collapsed | bytes per second · body size P95 by route, requests dashed and responses solid |
| SLO | | error budget left · burn rate over 1 h and 6 h · requests fast enough — all over 7 days, with sparklines · availability against the objective |
| Runtime | Workers | request share against an even split · the percentiles picked, under their total · in flight, stacked · CPU against one core · involuntary context switches · worker starts |
| | Process, collapsed | memory · threads · open files per worker · GC |
| | Profiling, collapsed | flame graph |
| Traces & logs | Traces | the traces picked in Show, newest first |
| | Logs | of the levels picked: lines by level · the stream — time, level, status, duration, request and message in columns |

Every route and every worker is drawn; the variables narrow them — `Route` to some routes, `Host`
to the workers of one container or pod. Each title says what is measured, then how it is cut:
`RPS — total · by route`, `CPU — by worker, one core is 100%`.

A click on `/api/report/{post_id}` in Routes, and the dashboard is about that route alone:

![The dashboard narrowed to one route](docs/screenshots/27-dashboard-route.png)

**In three languages.** English, Русский and 中文 are three dashboards in
[`dashboards/`](observability/grafana/dashboards), each translated whole — title, variables, rows,
panels; pick one in the dashboard list or under All dashboards. Grafana translates its own
interface, which follows the browser's language, but never what a dashboard says: a change to one
is a change to all three.

**On grafana.com.** Its upload takes the classic dashboard JSON, not the v2 schema these are in:
[`grafana-com/fastapi-observatory.json`](observability/grafana/grafana-com/fastapi-observatory.json)
is the English one as Grafana itself converts it — `GET /apis/dashboard.grafana.app/v1beta1/…/dashboards/observatory-api`.
The classic schema has no rows inside rows and no row variables, so the rows lie flat and their
pickers join the variables on top; the data sources stay variables, picked on import.

Lines read the same on every panel. A total is thick, over a light fill, drawn above the rest and
named `total` — white for the service, or the colour of its class: 2xx green, 3xx blue, 4xx orange,
5xx and exceptions red; P50 blue, P95 white, P99 purple. A thin line without fill is one route or
one worker. A dash is kept for two things: grey for yesterday, white for a reference — the
objective, an even split. Latency zones above 500 ms and 1 s are shaded; under the objective,
availability sits in a red zone. A panel of a few lines of their own — bytes, availability, GC —
draws them at middle width; a table legend lists every series that a panel breaks down.

Thresholds: 5xx over 1% orange, over 5% red; P95 over 500 ms orange, over 1 s red. The availability
target of the budget and the burn rate is the hidden variable `slo`, 0.995. Burn rate turns red at
3.36× over 1 h and 1.4× over 6 h — the pace that spends 2% and 5% of a 7-day budget in that window.
`just traffic` fails about 5% of requests on purpose and sends 4% the API refuses (422, 405), so the budget runs out.

A worker is a process: with the GIL it gets about one core, so the CPU panel is in fractions of one
core, not of the machine. One worker slower than the others, busier on CPU and preempted more often
points at a request that hogs it, not at the service as a whole. Worker starts shows when workers
came and went: a deploy, a crash, a recycle, or one Gunicorn killed for missing its 30-second
heartbeat.

<details open>
<summary><b>Requests</b></summary>

![Traffic and status codes](docs/screenshots/19-dashboard-traffic.png)
![Latency](docs/screenshots/02-dashboard-latency.png)
![Exceptions](docs/screenshots/04-dashboard-errors.png)
![Payload](docs/screenshots/03-dashboard-payload.png)
</details>

<details>
<summary><b>SLO</b></summary>

![SLO](docs/screenshots/15-dashboard-slo.png)
</details>

<details open>
<summary><b>Runtime</b></summary>

![Workers](docs/screenshots/18-dashboard-workers.png)
![Process](docs/screenshots/16-dashboard-process.png)
![Profiling](docs/screenshots/07-dashboard-profiling.png)
</details>

<details>
<summary><b>Traces & logs</b></summary>

![Traces](docs/screenshots/05-dashboard-traces.png)
![Logs](docs/screenshots/06-dashboard-logs.png)
</details>

## 🔗 From signal to signal

```mermaid
flowchart LR
    L["📜 Logs<br/>Loki"]
    T["🧵 Traces<br/>Tempo"]
    P["🔥 Profiles<br/>Pyroscope"]
    M["📈 Metrics<br/>VictoriaMetrics"]

    L -- "trace_id · session_id" --> T
    T -- "Logs for this span" --> L
    T -- "Profiles for this span" --> P
    T -- "span metrics: rate · P95" --> M
    M -. "panel links" .-> T
    M -. "panel links" .-> L

    classDef metrics fill:#B877D9,stroke:#8F3BB8,color:#111
    classDef logs fill:#73BF69,stroke:#56A64B,color:#111
    classDef traces fill:#5794F2,stroke:#3274D9,color:#111
    classDef profiles fill:#FF9830,stroke:#FA6400,color:#111
    classDef collector fill:#F55F3E,stroke:#C4162A,color:#fff
    classDef ui fill:#F46800,stroke:#C34F00,color:#fff
    classDef source fill:#E8E8E8,stroke:#9E9E9E,color:#111
    class M metrics
    class L logs
    class T traces
    class P profiles
```

| from | to | how |
|---|---|---|
| a log line, the browser's included | its trace · every line of its request | `trace_id` · `request_id` in structured metadata |
| a browser line | every trace of that browser session | `session_id` → `{span.session.id="…"}` |
| a request key from a header or a complaint | its trace | `{span.http.response.header.x_request_id="…"}` |
| a route in the Routes table | the whole dashboard for that route · its traces | `Route` set on the same dashboard · TraceQL with the route |
| a route on the traffic or latency panel | its traces · its slow traces | panel link → TraceQL with the route and the `Slow trace` threshold |
| a status class or a route with its code | the traces with that class · with that code on that route | panel link → TraceQL with the status code |
| an exception on a route | its log lines and stacks · its traces | panel link → LogQL with `error_type` and `route` · TraceQL with `event.exception.type` |
| an exception message | its log lines | panel link → LogQL with the message |
| a span | its logs · its CPU profile · the rate and P95 of its operation | Tempo data source links |

A series carries its links: a click on a bar of `/api/fail` offers the lines and the traces of
that exception on that route.

![The links of a series](docs/screenshots/24-panel-links.png)

**① A log line** links its trace and every line of its request.

![A log line and its links](docs/screenshots/08-log-to-trace.png)

**② The line and its trace**, side by side — this one started with a click in the page.

![The log line and its trace](docs/screenshots/09-log-and-trace.png)

**③ A span** links its logs, its profile and the metrics of its operation.
**④ Its profile** is the CPU of exactly that request — here one of `/api/cpu`.

> [!NOTE]
> Span profiles label samples by thread. A request that holds the event loop, like `/api/cpu`,
> gets a profile of its own; requests interleaving on the loop may share one.

<p>
<img src="docs/screenshots/10-span-links.png" width="54%" alt="The links of a span">
<img src="docs/screenshots/11-span-profile.png" width="44%" alt="The CPU profile of one request">
</p>

**⑤ A route's line on the latency panel** opens its slow traces. **⑥ The service graph** is drawn from client and
server spans.

<p>
<img src="docs/screenshots/14-slow-traces.png" width="62%" alt="The slow traces of a route, from the latency panel">
<img src="docs/screenshots/13-service-graph.png" width="36%" alt="The service graph">
</p>

**⑦ The rate and P95 of a span's operation** open beside the trace, from span metrics.

![The P95 of a span's operation](docs/screenshots/23-span-metrics.png)

**⑧ An exception's line** holds its type, message and the whole stack. **⑨ A browser error**
arrives through Faro with the session it happened in, and the session links every trace of it.

<p>
<img src="docs/screenshots/22-exception-log.png" width="54%" alt="The log line of an exception, with its stack">
<img src="docs/screenshots/21-browser-error.png" width="44%" alt="A browser error and its session">
</p>

A click on **Report on post 3** is one trace — the browser, the API, the cache, JSONPlaceholder,
SQLite and the CPU work:

```mermaid
sequenceDiagram
    participant B as Browser (Faro)
    participant M as AccessMiddleware
    participant H as build_report
    participant C as MemoryCache
    participant J as JSONPlaceholder
    participant S as SQLite

    B->>M: GET /api/report/3 + traceparent
    M->>H: handle, in the server span
    par the post
        H->>C: cache get (miss)
        H->>J: GET /posts/3
        H->>S: INSERT
        H->>C: cache set
    and its comments
        H->>J: GET /posts/3/comments
    end
    H->>H: count primes (profiled)
    H-->>M: 200
    M->>M: log line with trace_id
    M-->>B: 200 + x-request-id
```

![A trace of GET /api/report/{post_id}](docs/screenshots/12-trace.png)

| handler | the trace shows |
|---|---|
| `GET /api/posts/{id}` | cache → on a miss JSONPlaceholder → `INSERT` → cache |
| `GET /api/posts` | a `SELECT` |
| `POST /api/posts` | an `INSERT` — the only request with a body |
| `GET /api/cpu?below=N` | `count primes` and its profile |
| `GET /api/report/{id}` | all of the above, the fetches in parallel |
| `GET /api/posts/1000` | a 404 from the source |
| `GET /api/fail?kind=…` | a 500 of the kind asked for — `runtime`, `invalid`, `lookup`, `timeout`, `permission`, each its own exception type: the exception on the span, the stack in the log |
| `GET /api/posts/latest` · `GET /api/cpu?below=` past the limit | a 422: FastAPI refuses the parameter before the handler runs |
| `DELETE /api/posts/{id}` | a 405: the route exists, the method does not |

## 💻 Servers

`OBSERVATORY__SERVER__KIND` picks the server; every one implements `servers.Server` and loads the
same factory, `app:create_app`, in each process that serves.

| server | workers | process model | a worker killed with `SIGKILL` |
|---|---|---|---|
| **Gunicorn** + uvicorn-worker | forked by the master | inherits memory, not threads | replaced |
| **Uvicorn** | spawned by a supervisor | a new interpreter | replaced |
| **Hypercorn** | spawned by a master | a new interpreter | ⚠️ the server stops |
| **Granian** | spawned by a master | a new interpreter | replaced |

```mermaid
sequenceDiagram
    autonumber
    participant M as master / supervisor
    participant W as each serving process

    M->>M: Settings() · configure_logging()
    M->>M: prepare_database() — once
    M->>W: fork or spawn
    Note over W: forked: memory without threads<br/>spawned: nothing at all
    W->>W: create_app(): logging · tracing · metrics · profiling
    W->>W: open SQLite, serve
```

> [!IMPORTANT]
> `create_app()` assumes nothing set up before it, so the same code works forked and spawned.
> Telemetry starts threads, and a thread does not survive a fork — that is why Gunicorn's
> `preload_app` stays off: with it, profiles are lost and Python warns about forking a
> multi-threaded process.

**Checked** — each server with two workers, the same traffic:

| | Gunicorn | Uvicorn | Hypercorn | Granian |
|---|:-:|:-:|:-:|:-:|
| requests served | ✅ | ✅ | ✅ | ✅ |
| every log line JSON | ✅ | ✅ | ✅ | ✅ |
| access lines with `trace_id` | ✅ | ✅ | ✅ | ✅ |
| workers sending telemetry | 2 | 2 | 2 | 2 |
| process metrics | ✅ | ✅ | ✅ | ✅ |
| traces and profiles | ✅ | ✅ | ✅ | ✅ |

## 📜 Logging

```mermaid
flowchart LR
    record["logger.info('post created',<br/>extra={'post_id': 8})"]
    factory["record factory<br/>+ request_id · trace_id · span_id"]
    fmt["JSON formatter<br/>on the root's handler"]
    out["stdout"]
    alloy["Alloy<br/>lvl → label<br/>ids → structured metadata"]
    loki[("Loki")]
    record --> factory --> fmt --> out --> alloy --> loki

    classDef metrics fill:#B877D9,stroke:#8F3BB8,color:#111
    classDef logs fill:#73BF69,stroke:#56A64B,color:#111
    classDef traces fill:#5794F2,stroke:#3274D9,color:#111
    classDef profiles fill:#FF9830,stroke:#FA6400,color:#111
    classDef collector fill:#F55F3E,stroke:#C4162A,color:#fff
    classDef ui fill:#F46800,stroke:#C34F00,color:#fff
    classDef source fill:#E8E8E8,stroke:#9E9E9E,color:#111
    class loki logs
    class alloy collector
    class record,factory,fmt,out source
```

```json
{"ts":"2026-10-03T10:19:44.631+00:00","lvl":"INFO","msg":"HTTP request handled","logger":"observatory","caller":"middleware:_write:70","request_id":"7cefc9e7…","trace_id":"ef23e199…","span_id":"…","method":"GET","path":"/api/posts/3","route":"/api/posts/{post_id}","status":200,"duration_ms":297}
```

| who writes | logger | level |
|---|---|---|
| the application, the telemetry setup | `observatory` | `OBSERVATORY__LOG_LEVEL` |
| Gunicorn · Uvicorn · Hypercorn · Granian | their own, formatted as JSON | `OBSERVATORY__LOG_LEVEL` |
| libraries: httpx, OpenTelemetry, … | their own | the root's `WARNING` |

The access line's level follows the status: `INFO`, `WARNING` for a 4xx, `ERROR` for a 5xx. An
unhandled exception becomes `error_type`, `error_message`, `error_stack`. `route` is the matched template,
the one the metrics carry as `http_route`, so a line and its metrics group alike. `AccessMiddleware`
writes one line per response inside the request span and returns `x-request-id`, which the FastAPI
instrumentation also records on the span; the servers' access logs are off.

Browser lines arrive through Faro. Every one carries its `session_id`, and those of the page's own
HTTP calls their `trace_id` and `span_id` — all three in structured metadata, like the
application's keys.

<details>
<summary><b>How every line becomes JSON</b></summary>

`configure_logging(level)` runs in every process that writes lines — `main()` and `create_app()`:
it gives the root a stdout handler, puts the JSON formatter on it and sets `observatory`'s level.
A repeat call stacks nothing.

- Levels are checked on the logger called, not on its ancestors: the root stays at `WARNING`, yet
  `observatory`'s `INFO` reaches the root's handler.
- `observatory` keeps `propagate = True` — with `False` its lines would never reach that handler.
- Servers with handlers of their own get them formatted too (`GunicornJsonLogger`); the others are
  pointed at the root.

</details>

## 📈 Metrics

The process ships only the server's and its own metrics: a view in `configure_metrics` keeps
`http.server.*`, `process.*` and `cpython.*`. httpx and SQLite still give spans, not metrics.

> [!NOTE]
> VictoriaMetrics turns OpenTelemetry names into Prometheus ones: dots become `_`, the unit a
> suffix — `http.server.request.duration` (s) → `http_server_request_duration_seconds`.

Alloy's `otelcol.exporter.prometheus` turns OTLP into Prometheus series by the
[OpenTelemetry → Prometheus mapping](https://opentelemetry.io/docs/specs/otel/compatibility/prometheus_and_openmetrics/#otlp-metric-points-to-prometheus);
each of its options is written out in `observability/alloy/receiver.alloy`.

| on the series | from |
|---|---|
| the name | the metric name, `.` → `_`, with the unit and `_total` for counters |
| `job` | resource `service.name` |
| `instance` | resource `service.instance.id` — `<host>-<pid>`, one per worker |
| every other label | the data point's attributes, `.` → `_` |
| `target_info{job, instance, …}` | one series per worker with the rest of the resource: `host_name`, `deployment_environment_name`, the SDK — joined on `job` and `instance` when needed |

`otel_scope_name` and `otel_scope_version` are switched on but do not arrive yet: Alloy 1.20.1
ignores `include_scope_labels` ([grafana/alloy#6787](https://github.com/grafana/alloy/pull/6787)).

| metric | from | its own labels |
|---|---|---|
| `http_server_request_duration_seconds` | FastAPI | `http_route`, `http_request_method`, `http_response_status_code`, `error_type`, `url_scheme`, `network_protocol_version` |
| `http_server_active_requests` | FastAPI | `http_request_method`, `url_scheme` |
| `http_server_request_body_size_bytes`, `http_server_response_body_size_bytes` | FastAPI | as the duration |
| `process_cpu_time_seconds_total`, `process_memory_usage_bytes`, `process_thread_count`, `process_open_file_descriptor_count`, … | each worker about itself | — |
| `cpython_gc_collections_total`, `cpython_gc_collected_objects_total`, … | each worker's GC | `generation` and `cpython_gc_generation` — the instrumentation sends both |
| `traces_spanmetrics_calls_total`, `traces_spanmetrics_latency` | Tempo, from spans of both services | `service`, `span_name`, `span_kind`, `status_code`, the `dimensions` of `tempo.yaml`, `source="tempo"`, Tempo's `__metrics_gen_instance` |
| `traces_service_graph_request_*` | Alloy, from span pairs | `client`, `server`, `connection_type`, `failed`, `virtual_node` |

Sources:
[OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/) ·
[FastAPI instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html) ·
[system metrics](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/system_metrics/system_metrics.html) ·
[span metrics](https://grafana.com/docs/tempo/latest/metrics-generator/span_metrics/).

## 🔧 Configuration

Environment variables with the `OBSERVATORY__` prefix; groups nest with `__`.

| variable | default |
|---|---|
| `OBSERVATORY__SERVER__KIND` | **required**: `gunicorn` · `uvicorn` · `hypercorn` · `granian` |
| `OBSERVATORY__SERVER__HOST` · `PORT` · `WORKERS` | `127.0.0.1` · `8000` · `2` |
| `OBSERVATORY__LOG_LEVEL` | `info` |
| `OBSERVATORY__DB__PATH` | `observatory.db` |
| `OBSERVATORY__OBS__SERVICE_NAME` · `ENVIRONMENT` | `api` · `development` — or `production`, `staging`, `test` |
| `OBSERVATORY__OBS__OTLP__ENDPOINT` | `http://localhost:4317` |
| `OBSERVATORY__OBS__PYROSCOPE__URL` | `http://localhost:4040` |
| `OBSERVATORY__OBS__FARO__COLLECTOR_URL` | `http://localhost:12347/collect` — as the browser sees it |

<details>
<summary><b>Each server's own options</b></summary>

Under the same `OBSERVATORY__SERVER__` prefix; another server's option is refused at startup.

| `KIND` | options |
|---|---|
| `gunicorn` | `TIMEOUT` · `GRACEFUL_TIMEOUT` · `KEEPALIVE` · `MAX_REQUESTS` · `MAX_REQUESTS_JITTER` · `BACKLOG` |
| `uvicorn` | `TIMEOUT_KEEP_ALIVE` · `TIMEOUT_GRACEFUL_SHUTDOWN` · `LIMIT_CONCURRENCY` · `LIMIT_MAX_REQUESTS` · `BACKLOG` |
| `hypercorn` | `KEEP_ALIVE_TIMEOUT` · `GRACEFUL_TIMEOUT` · `MAX_REQUESTS` · `MAX_REQUESTS_JITTER` · `BACKLOG` |
| `granian` | `RUNTIME_THREADS` · `BLOCKING_THREADS` · `BACKPRESSURE` · `BACKLOG` · `WORKERS_LIFETIME` · `WORKERS_KILL_TIMEOUT` |

`MAX_REQUESTS=1000 MAX_REQUESTS_JITTER=100` under Gunicorn restarts each worker after 1000–1100
requests.

</details>

## ☸️ Kubernetes

`just k3d up` runs the same stack in a local [k3d](https://k3d.io) cluster: it builds the image,
imports it, applies [`deploy/kubernetes/`](deploy/kubernetes) and waits for the rollout; `just k3d
down` deletes the cluster. The ports are Compose's — 3000, 8000, 12345, 12347 — so stop one
before starting the other.

Nothing is copied. Kustomize builds the ConfigMaps from the files Compose mounts, and the Services
carry the Compose service names, so `loki:3100` and `alloy:4317` mean the same on both. The
dashboard does not know the platform either: it asks only for `service.name` and
`service.instance.id`.

| | Compose | Kubernetes |
|---|---|---|
| Alloy reads | `receiver.alloy` + `docker.alloy` | `receiver.alloy` + `kubernetes.alloy` |
| container output | `loki.source.docker`, through `docker.sock` | `loki.source.kubernetes`, through the API; a Role reads the pods and their logs in one namespace |
| a log line's `service_name` | the Compose service | the pod's `app.kubernetes.io/name` |
| an instance — `host_name` | the container | the pod; the API runs two, of two workers each |
| where a process runs | — | `k8s.pod.name`, `k8s.pod.uid`, `k8s.namespace.name`, `k8s.node.name` from the downward API, in `OTEL_RESOURCE_ATTRIBUTES` |

> [!NOTE]
> Alloy reads pod output through the API server, which is enough for one small cluster. A large one
> reads the nodes' log files from a DaemonSet, as Grafana's k8s-monitoring chart does, and runs
> `receiver.alloy` in a Deployment of its own.

## 🧰 Development

`just` is the command line: a command, then what it acts on. A value it does not know is an error
that lists the ones it does; `just` alone lists the commands.

| command | does |
|---|---|
| `just install` · `just hooks` | the venv · git hooks via prek |
| `just lint` | every check — what CI would run |
| `just lint ruff` · `flake8` · `mypy` | ruff format and check · wemake-python-styleguide · mypy |
| `just lint slotscheck` · `spelling` · `pyproject` | slotscheck · codespell and typos · pyproject-fmt |
| `just dc up` · `down` · `ps` · `logs` | the stack in Compose; `just docker-compose …` is the same |
| `just k3d up` · `down` · `ps` · `logs` | the stack in a k3d cluster |
| `just dc logs api grafana` · `just k3d logs api` | the logs of chosen services only |
| `just traffic` | requests at the running stack, either one: `RATE`, `DURATION`, and the mix — `CPU_PERCENT`, `REPORT_PERCENT`, `CPU_BELOW_MAX`, `FAIL_PERCENT`, `INVALID_PERCENT`; `API_WORKERS=8 just dc up` for a heavier one |
| `just run gunicorn` | the application outside Docker, against the running stack |

## 🧱 Stack

| | version | port | role |
|---|---|---|---|
| **Grafana** | 13.2.3 | `3000` | dashboards, Explore, Drilldown |
| **Alloy** | 1.20.1 | `12345` · `12347` | the only collector · the Faro receiver |
| **VictoriaMetrics** | 1.153.0 | `8428` | metrics |
| **Loki** | 3.7.8 | `3100` | logs |
| **Tempo** | 3.1.0 | `3200` | traces, span metrics |
| **Pyroscope** | 2.3.1 | `4040` | CPU profiles |
| **Faro Web SDK** | 2.12.1 | — | the browser's telemetry |
| **Gunicorn** · **Uvicorn** · **Hypercorn** · **Granian** | 26.2 · 0.54 · 0.18 · 2.8.4 | `8000` | the servers; Gunicorn in Docker |

Everything is published on `127.0.0.1` only.
