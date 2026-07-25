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

    # 外部提供商调用 (Agnes 等 OpenAI 兼容)
    # 图像同步出图较慢, 用较长超时; 视频提交后异步轮询。
    provider_image_timeout_s: int = 300
    provider_video_submit_timeout_s: int = 120
    provider_http_connect_timeout_s: int = 15
    # 视频轮询: 每 interval 秒查一次, 最多等 max 秒 (超时 -> 失败 -> 退款)。
    video_poll_interval_s: int = 5
    video_poll_max_s: int = 300
    # 真实提供商失败时是否回退到 Mock。
    # 生产必须为 False: 回退会给已扣费的用户返回假图并掩盖真实故障。
    # 仅离线联调 (无外网) 时可临时置 True。
    allow_mock_fallback: bool = False
    # 生成结果在对象存储中的公开前缀 (浏览器可直接读取 CDN URL)。
    media_public_prefix: str = "gen"

    # Worker
    worker_enabled: bool = True
    worker_poll_ms: int = 500


settings = Settings()
