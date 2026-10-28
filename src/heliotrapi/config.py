import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    suppress_polling_logs: bool = False


class RabbitMQConfig(BaseModel):
    enabled: bool = False
    host: str = "ixx-rabbitmq-daq.diamond.ac.uk"
    username: str = "guest"
    password: str = "guest"
    port: int = 61613
    destinations: list[str] = [
        "/topic/public.worker.event",  # bluesky scans
        "/topic/gda.messages.scan",  # gda scans"
        "/topic/gda.messages.processing",  # swmr dawn stuff
    ]
    # this is where rabbitmq listens

    @property
    def address(self):
        return f"stomp://{self.username}:{self.password}@{self.host}:{self.port}/"


class QueueConfig(BaseModel):
    workers: int = 2


class ResultsConfig(BaseModel):
    # time to live seconds - how long the results
    # from a process can live before being being valid for removal
    ttl_seconds: int = 3600  # 3600s = 1hr
    # sqlite file the results are stored in
    db_path: str = "results.db"


class CleanupConfig(BaseModel):
    # how frequently the cleanup job actually runs
    interval_seconds: int = 300


class MessageFunctionsConfig(BaseModel):
    # dotted paths (relative to a repo's src) of the function to run on each
    # STOMP message, e.g. xrpd_toolbox.i15_1.handlers.on_start
    start: str | None = None
    stop: str | None = None
    nexus_started: str | None = None
    nexus_updated: str | None = None
    nexus_finished: str | None = None


class GithubRepoConfig(BaseModel):
    url: str
    # read every file in the repo and register every public function
    register_all: bool = False
    # dotted paths (relative to the repo's src) of packages/modules/functions
    # to register when not register_all
    include: list[str] = []


class PluginsConfig(BaseModel):
    paths: list[str] = []
    github_repos: list[GithubRepoConfig] | None = []
    # one function per STOMP message type, looked up across all repos
    message_functions: MessageFunctionsConfig = Field(
        default_factory=MessageFunctionsConfig
    )

    @field_validator("github_repos", mode="before")
    @classmethod
    def _repo_urls_to_config(cls, repos: list | None) -> list | None:
        # allow plain URL strings as shorthand for {url: ...}
        if repos is None:
            return None
        return [{"url": r} if isinstance(r, str) else r for r in repos]


class AlertConfig(BaseModel):
    slack_webhook_url: str | None = None


class AuthConfig(BaseModel):
    # HTTP Basic auth for endpoints that submit analyses
    enabled: bool = True
    username: str = "admin"
    password: str = "password"


class Config(BaseSettings):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    results: ResultsConfig = Field(default_factory=ResultsConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )

    @model_validator(mode="after")
    def auth_credentials_from_env(self) -> Self:
        # credentials come from env vars (a SealedSecret on Kubernetes),
        # so they never need to be written in the config file
        self.auth.username = os.getenv("HELIOTRAPI_USERNAME", self.auth.username)
        self.auth.password = os.getenv("HELIOTRAPI_PASSWORD", self.auth.password)
        return self

    @classmethod
    def load_config(cls, path: str | Path | None = None) -> Self:
        if path is None:
            env_path = os.getenv("CONFIG_PATH")
            if env_path:
                path = Path(env_path)
            else:
                candidate = Path("/etc/config/config.yaml")
                path = candidate if candidate.exists() else Path("config.yaml")

        path = Path(path)

        data = {}
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        # 1. load YAML into model
        # 2. allow env vars to override it
        return cls.model_validate(data)


def load_config(path: str | Path | None = None) -> Config:
    return Config.load_config(path)
