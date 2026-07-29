"""异步生成引擎: 单一事件循环 + httpx 承载所有外部模型调用.

为什么需要它
------------
原 Dispatcher 用 ``ThreadPoolExecutor(max_workers=16)`` 跑同步 ``requests.post``,
每张图(18~77s, 晚高峰 5~10min)占满 1 个 OS 线程 -> 第 17 张图只能排队干等 (头阻塞)。
这就是"16 线程会阻塞"的根。

改为: 一条常驻事件循环 + 共享 ``httpx.AsyncClient`` 承载**所有**在途的外部模型调用。
等待外部模型返回的 5~10min 期间, 协程 ``await`` 让出控制权, 单线程即可并发支撑上千个
在途请求; 真正阻塞的"收尾" (转存下载 + 写库 + 发事件) 交给独立线程池, 绝不卡事件循环。

并发上限改由 ``per_user_concurrency`` (12) 与 httpx 连接池上限决定, 不再受 16 线程束缚。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_loop: "asyncio.AbstractEventLoop | None" = None
_loop_thread: "threading.Thread | None" = None
_client: "httpx.AsyncClient | None" = None
_finalize_pool: "ThreadPoolExecutor | None" = None
_lock = threading.Lock()
_ready = threading.Event()


async def _init_client() -> None:
    global _client
    limits = httpx.Limits(
        max_connections=settings.async_max_connections,
        max_keepalive_connections=settings.async_keepalive_connections,
        keepalive_expiry=60.0,
    )
    _client = httpx.AsyncClient(
        # 位置参数=默认(read/write/pool), connect 单独覆盖; httpx 要求四参数或带默认, 缺一不可。
        # trust_env=False: 与 ai-agent 的 httpx(trust_env=False) 等价 —— 强制不走 HTTPS_PROXY 环境变量,
        # 直接出网。否则容器里注入的 HTTPS_PROXY=host.docker.internal:33210(开发机专属死代理)会劫持
        # 所有出网调用(出图/出视频), 在服务器上表现为连接被重置/超时。服务器直连外部 AI 可达(同机
        # ai-agent 已验证), 故默认直连最稳; 真需代理时由 PEA_PROXY_FIX 链路单独处理。
        trust_env=False,
        timeout=httpx.Timeout(
            settings.provider_image_timeout_s,
            connect=settings.provider_http_connect_timeout_s,
        ),
        limits=limits,
    )
    logger.info("[engine] httpx client ready (max_connections=%d)", settings.async_max_connections)


def _run_loop(loop: "asyncio.AbstractEventLoop") -> None:
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_init_client())
    _ready.set()
    logger.info("[engine] event loop running")
    loop.run_forever()


def _ensure_loop() -> None:
    global _loop, _loop_thread, _finalize_pool
    if _loop is not None:
        return
    with _lock:
        if _loop is not None:
            return
        loop = asyncio.new_event_loop()
        _finalize_pool = ThreadPoolExecutor(
            max_workers=settings.async_finalize_workers,
            thread_name_prefix="finalize",
        )
        _loop = loop
        t = threading.Thread(target=_run_loop, args=(loop,), daemon=True, name="async-engine")
        t.start()
        _loop_thread = t
        _ready.wait(timeout=15)


def get_client() -> "httpx.AsyncClient":
    _ensure_loop()
    assert _client is not None, "httpx client not initialized"
    return _client


def ensure_started() -> None:
    """预热事件循环与 httpx 客户端 (应用启动期调用, 避免首个生成请求才懒初始化拖慢首图)。"""
    _ensure_loop()


def get_loop() -> "asyncio.AbstractEventLoop":
    _ensure_loop()
    assert _loop is not None, "event loop not initialized"
    return _loop


def run_finalize(func: Callable[..., Any], *args: Any) -> Awaitable[Any]:
    """把阻塞的收尾工作 (转存下载 / 写库 / 发事件) 丢到线程池, 返回 awaitable, 不卡事件循环。"""
    return get_loop().run_in_executor(_finalize_pool, func, *args)


def _log_exc(fut: Any) -> None:
    try:
        exc = fut.exception()
    except BaseException:
        exc = None
    if exc:
        logger.error("[engine] unhandled coroutine error: %s", exc, exc_info=exc)


def schedule(coro: Awaitable) -> None:
    """将协程提交到事件循环 (fire-and-forget)。协程自身负责终态与并发名额释放。"""
    _ensure_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)  # type: ignore[arg-type]
    fut.add_done_callback(_log_exc)
