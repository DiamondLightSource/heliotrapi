import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    suppress_polling_logs: bool = False


class ListenerLockConfig(BaseModel):
    """Tuning for the Redis lock that lets only one uvicorn.workers process
    run the RabbitMQ listener at a time (STOMP topic subscriptions are
    pub/sub, so every worker process would otherwise receive and enqueue
    every message). If the holder dies, the lock expires and another
    process's retry loop takes over - no manual failover needed."""

    ttl_seconds: int = 15
    renew_interval_seconds: float = 5.0
    retry_interval_seconds: float = 5.0


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

    listener_lock: ListenerLockConfig = Field(default_factory=ListenerLockConfig)

    @property
    def address(self):
        return f"stomp://{self.username}:{self.password}@{self.host}:{self.port}/"


class QueueConfig(BaseModel):
    # concurrent async consumer loops *per OS process* pulling from the
    # shared Redis job queue - not a global total across uvicorn.workers
    workers: int = 2


class ResultsConfig(BaseModel):
    # time to live seconds - how long a result lives in Redis before it
    # expires; replaces the old in-memory cleanup poll entirely
    ttl_seconds: int = 3600  # 3600s = 1hr


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    key_prefix: str = "heliotrapi"
    # Where the embedded redis-server (see redis_service.py) persists its
    # append-only file, so data survives a restart. Only used when
    # heliotrapi itself starts Redis - back this with a persistent volume
    # in deployment so it isn't lost when the pod restarts.
    data_dir: str = "./data/redis"


class UvicornConfig(BaseModel):
    # number of OS-level Gunicorn worker processes. 1 (default) runs plain
    # uvicorn in-process (dev/local); >1 launches Gunicorn with
    # UvicornWorker + --preload so plugins/analyses load once before fork.
    workers: int = 1


class PluginsConfig(BaseModel):
    paths: list[str] = []
    github_repos: list[str] | None = []
    register_all: bool = False


class AlertConfig(BaseModel):
    slack_webhook_url: str | None = None


class Config(BaseSettings):
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    results: ResultsConfig = Field(default_factory=ResultsConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    uvicorn: UvicornConfig = Field(default_factory=UvicornConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)

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
        return cls.model_validate(data)


def load_config(path: str | Path | None = None) -> Config:
    return Config.load_config(path)
