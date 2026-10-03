from pathlib import Path
from typing import Annotated, Final, Literal

from opentelemetry.semconv.attributes.deployment_attributes import DeploymentEnvironmentNameValues
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

from enums import LogLevel

_HIGHEST_PORT: Final = 65535


class _ServerSettings(BaseModel):
    """What every server takes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=_HIGHEST_PORT)] = 8000
    workers: PositiveInt = 2

    @property
    def address(self) -> str:
        """The address as `host:port`."""
        return f"{self.host}:{self.port}"


class GunicornSettings(_ServerSettings):
    """Gunicorn's settings."""

    kind: Literal["gunicorn"]
    timeout: PositiveInt = 30
    graceful_timeout: PositiveInt = 30
    keepalive: PositiveInt = 2
    max_requests: NonNegativeInt = 0
    max_requests_jitter: NonNegativeInt = 0
    backlog: PositiveInt = 2048


class UvicornSettings(_ServerSettings):
    """Uvicorn's settings."""

    kind: Literal["uvicorn"]
    timeout_keep_alive: PositiveInt = 5
    timeout_graceful_shutdown: PositiveInt | None = None
    limit_concurrency: PositiveInt | None = None
    limit_max_requests: PositiveInt | None = None
    backlog: PositiveInt = 2048


class HypercornSettings(_ServerSettings):
    """Hypercorn's settings."""

    kind: Literal["hypercorn"]
    keep_alive_timeout: PositiveFloat = 5.0
    graceful_timeout: PositiveFloat = 3.0
    max_requests: PositiveInt | None = None
    max_requests_jitter: NonNegativeInt = 0
    backlog: PositiveInt = 100


class GranianSettings(_ServerSettings):
    """Granian's settings."""

    kind: Literal["granian"]
    runtime_threads: PositiveInt = 1
    blocking_threads: PositiveInt | None = None
    backpressure: PositiveInt | None = None
    backlog: PositiveInt = 1024
    workers_lifetime: Annotated[int, Field(ge=60)] | None = None
    workers_kill_timeout: PositiveInt | None = None


_AnyServerSettings = Annotated[
    GunicornSettings | UvicornSettings | HypercornSettings | GranianSettings,
    Field(discriminator="kind"),
]
"""One server's settings, chosen by `kind`; a setting another server takes is refused."""


class _DatabaseSettings(BaseModel):
    """The SQLite file."""

    model_config = ConfigDict(frozen=True)

    path: Path = Path("observatory.db")
    """Relative to the working directory."""


class _OtlpSettings(BaseModel):
    """Where traces and metrics go."""

    model_config = ConfigDict(frozen=True)

    endpoint: str = "http://localhost:4317"


class _PyroscopeSettings(BaseModel):
    """Where CPU profiles go."""

    model_config = ConfigDict(frozen=True)

    url: str = "http://localhost:4040"


class _FaroSettings(BaseModel):
    """Where the browser sends its telemetry."""

    model_config = ConfigDict(frozen=True)

    collector_url: str = "http://localhost:12347/collect"


class _ObservabilitySettings(BaseModel):
    """Who sends the telemetry and where each kind of it goes."""

    model_config = ConfigDict(frozen=True)

    service_name: str = "api"
    environment: DeploymentEnvironmentNameValues = DeploymentEnvironmentNameValues.DEVELOPMENT

    otlp: _OtlpSettings = Field(default_factory=_OtlpSettings)
    pyroscope: _PyroscopeSettings = Field(default_factory=_PyroscopeSettings)
    faro: _FaroSettings = Field(default_factory=_FaroSettings)


class Settings(BaseSettings):
    """Everything the process reads from the environment: what differs between machines."""

    model_config = SettingsConfigDict(env_prefix="OBSERVATORY__", env_nested_delimiter="__", frozen=True)

    log_level: LogLevel = LogLevel.INFO

    server: _AnyServerSettings
    db: _DatabaseSettings = Field(default_factory=_DatabaseSettings)
    obs: _ObservabilitySettings = Field(default_factory=_ObservabilitySettings)
