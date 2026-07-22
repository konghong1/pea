"""Orchestrator 配置 (env-driven, 12-factor)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEA_", env_file=".env", extra="ignore")

    # 服务
    service_name: str = "generation-orchestrator"
    port: int = 8000
    # 调用 BFF 内部接口(退款等)的 service token
    internal_service_token: str = "change-me-in-prod"
    bff_internal_base_url: str = "http://bff:4000"

    # MySQL
    db_host: str = "mysql"
    db_port: int = 3306
    db_user: str = "pea"
    db_password: str = "pea_dev"
    db_name: str = "pea"

    # Redis (队列 + 事件)
    redis_url: str = "redis://redis:6379/0"

    # 对象存储 (S3 兼容)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "pea-media"
    cdn_base_url: str = "http://localhost:9000/pea-media"

    # 生成护栏
    per_user_concurrency: int = 3
    default_cost_tapies: int = 10
    # 主/备 provider (LiteLLM 路由, 失败自动回退)
    provider_primary: str = "mock"
    provider_fallback: str = "mock"

    # Worker
    worker_enabled: bool = True
    worker_poll_ms: int = 500


settings = Settings()
