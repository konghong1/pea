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
    per_user_concurrency: int = 12  # 决策④: 每用户同时进行任务上限 (原 3)
    per_user_concurrency_ttl_s: int = 3600  # 并发计数兜底 TTL, 防异常未释放永久泄漏
    default_cost_tapies: int = 10
    # 主/备 provider (LiteLLM 路由, 失败自动回退)
    provider_primary: str = "mock"
    provider_fallback: str = "mock"

    # 外部提供商调用 (Agnes 等 OpenAI 兼容)
    # 图像同步出图较慢, 用较长超时; 视频提交后异步轮询。
    # 2026-07-28 调整: 实际观测到 Agnes 在晚高峰 submit 阶段需要 5-10 分钟,
    # 原 300s/120s 阈值过紧, 频繁误杀。放宽到 900s (15min) 覆盖峰值, 同时
    # 仍受外部 nginx/上游进一步超时约束, 不会无限挂住线程。
    provider_image_timeout_s: int = 900
    provider_video_submit_timeout_s: int = 900
    provider_http_connect_timeout_s: int = 15
    # AI 网关兜底地址: 当 provider 官方 base_url 不可达(连接错误)时, 自动回退到此网关。
    # ★ 默认为空 = 不兜底。之前默认 host.docker.internal:33210 是开发机专属代理,
    #   服务器上无此代理时兜底请求必然 ECONNREFUSED, 且会把真实的主地址错误
    #   掩盖成 "connect ECONNREFUSED 172.17.0.1:33210"。
    #   确有网关时通过环境变量 PEA_AI_GATEWAY 显式配置。
    ai_gateway: str = ""
    # 视频轮询: 每 interval 秒查一次, 最多等 max 秒 (超时 -> 失败 -> 退款)。
    # 2026-07-28 修正: Agnes 晚高峰真实出片常需 5-10 分钟 (见 provider_video_submit_timeout_s 注释),
    # 原 300s 会把正常长任务误杀成 failed。与 submit 超时对齐放宽到 900s (15min)。
    video_poll_interval_s: int = 5
    video_poll_max_s: int = 900
    # 真实提供商失败时是否回退到 Mock。
    # 生产必须为 False: 回退会给已扣费的用户返回假图并掩盖真实故障。
    # 仅离线联调 (无外网) 时可临时置 True。
    allow_mock_fallback: bool = False
    # 生成结果在对象存储中的公开前缀 (浏览器可直接读取 CDN URL)。
    media_public_prefix: str = "gen"

    # ── 异步完成层 (async_core) ───────────────────────────────
    # 决策①: 外部临时 URL 转存到自有对象存储, 给前端稳定地址
    rehost_enabled: bool = True
    # 决策②: 每厂商各一把 webhook 密钥 (落在 ai_providers.webhook_secret);
    #   下方 webhook_base_url 为对外可达回调基址, webhook_secret 仅作兜底/测试占位.
    webhook_base_url: str = ""
    webhook_secret: str = ""
    webhook_grace_s: int = 120  # webhook 多久没来就转轮询兜底
    # Completer (后台轮询回路)
    completer_batch: int = 50          # 每批并发查询数
    completer_tick_s: int = 2          # 扫描周期
    completer_stale_s: int = 180       # 句柄被"已死实例"占住的回收阈值
    # Dispatcher 提交执行线程池 —— 已废弃: 同步出图改为异步事件循环 (见 async_core/engine.py),
    # 不再用固定线程池, 故该值不再被消费。保留字段仅为兼容既有 compose/env 覆盖, 勿依赖。
    dispatch_executor_workers: int = 16
    # ── 异步生成引擎 (替代 16 线程池, 见 async_core/engine.py) ──────
    # 单一事件循环 + 共享 httpx 客户端并发承载在途请求, 不再受 OS 线程数上限束缚。
    async_max_connections: int = 200            # httpx 总并发连接上限 (并发在途生成数硬上限)
    async_keepalive_connections: int = 50       # 常驻 keep-alive 连接数
    async_finalize_workers: int = 32            # 收尾线程池大小 (转存下载 + 写库 + 发事件), 不卡事件循环
    # 图像生成对瞬时 5xx 的重试次数: 调大=更稳但晚高峰慢(503 会翻倍等待), 调小(=1)=峰值更快但失败率略升。
    # 默认值 2 与原行为一致 (保持"图不出"不恶化)。若想压晚高峰延迟可临时置 1。
    provider_image_retry_attempts: int = 2
    # 决策③: 失败告警滑动窗口
    failure_alert_window_s: int = 300
    failure_alert_threshold: int = 5

    # 开发/联调极速开关: 逗号分隔的 type 列表 (如 "image,video") 强制走 MockProvider。
    # 真实图像/视频提供商 (Agnes 等) 单张出图 18~77s, 物理上无法达到 1~3s; 联调/演示期
    # 用 mock 可在 ~0.5s 内返回占位图。生产务必留空以走真实提供商。
    # 取值示例: "" (关闭, 走真实) | "image,video" (图像/视频走 mock) | "image,video,text"
    force_mock_types: str = ""

    # Worker
    worker_enabled: bool = True
    worker_poll_ms: int = 500

    @property
    def force_mock_types_set(self) -> set[str]:
        return {s.strip() for s in self.force_mock_types.split(",") if s.strip()}


settings = Settings()
