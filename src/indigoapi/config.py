import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


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


class CleanupConfig(BaseModel):
    # how frequently the cleanup job actually runs
    interval_seconds: int = 300


class PluginsConfig(BaseModel):
    paths: list[str] = []
    github_repos: list[str] | None = []
    register_all: bool = False


class Config(BaseSettings):
    server: ServerConfig = ServerConfig()
    queue: QueueConfig = QueueConfig()
    results: ResultsConfig = ResultsConfig()
    cleanup: CleanupConfig = CleanupConfig()
    plugins: PluginsConfig = PluginsConfig()
    rabbitmq: RabbitMQConfig = RabbitMQConfig()

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )

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
        return cls(**data)


def load_config(path: str | Path | None = None) -> Config:
    return Config.load_config(path)
