"""对象存储 (MinIO): 把外部提供商返回的临时媒体 URL 落到自有桶, 返回稳定的公开 CDN URL.

为什么要转存 (资深复核):
- 外部 (Agnes) 返回的 URL 往往是临时/带签名/会过期的, 直接存进 generation_jobs.result_json
  会导致历史记录后续 404。转存到自有桶得到永久可读地址。
- 生成结果需要在画布/前端直接展示, 故 `gen/` 前缀设为匿名只读, 浏览器可凭
  `{cdn_base_url}/{key}` 直接加载; 用户私有上传仍位于 `u:<id>/` 前缀走签名访问, 不受影响。

线程安全: bucket/policy 只在首次惰性初始化一次 (双重检查 + 锁), 之后 put_object 由
MinIO 客户端自身保证并发安全。
"""
from __future__ import annotations

import io
import logging
import mimetypes
import threading
import uuid
from datetime import datetime

import requests
import urllib3
from minio import Minio

from app.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None
_init_lock = threading.Lock()
_bucket_ready = False
_policy_ok = False  # gen/ 公开读策略是否已确认生效 (决策①稳定性护栏)

# MinIO 客户端必须有超时: 历史上因缺省无超时, 在某些 MinIO 服务端组合下
# bucket_exists/put_object/set_bucket_policy 会无限挂死, 直接拖垮生成链路
# (worker 卡死 / 看门狗超时后被迫回退 Mock 假图)。这里设连接 10s + 读取 60s。
_HTTP_CLIENT = urllib3.PoolManager(
    timeout=urllib3.Timeout(connect=10, read=60),
    retries=urllib3.Retry(total=2, backoff_factor=0.5,
                           status_forcelist=[500, 502, 503, 504]),
)


def _get_client() -> Minio:
    global _client
    if _client is None:
        with _init_lock:
            if _client is None:
                _client = Minio(
                    settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_secure,
                    http_client=_HTTP_CLIENT,
                )
    return _client


def _public_policy(bucket: str, prefix: str) -> str:
    """仅对 `{prefix}/*` 开放匿名只读, 不暴露其余对象 (如用户私有上传)。"""
    import json

    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/{prefix}/*"],
                }
            ],
        }
    )


def _do_ensure_bucket() -> None:
    """仅做建桶(若不存在)。策略设置移到 ensure_public_policy, 避免冷启动慢调用阻塞生成。"""
    client = _get_client()
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _ensure_bucket() -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    with _init_lock:
        if _bucket_ready:
            return
        # 只做轻量建桶检查(快), 策略设置在 worker 启动时后台重试, 绝不在生成热路径上
        # 调用可能冷启动缓慢的 set_bucket_policy, 否则会拖垮真实生成 -> 看门狗 -> Mock 假图。
        try:
            _do_ensure_bucket()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure bucket best-effort failed: %s", exc)
        _bucket_ready = True


def _apply_policy_now(client, bucket: str, policy: str) -> bool:
    """单次尝试设置公开读策略, 10s 护栏. 返回是否成功."""
    box: dict = {}

    def _run() -> None:
        try:
            client.set_bucket_policy(bucket, policy)
            box["ok"] = True
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(10)
    return bool(box.get("ok"))


def ensure_public_policy(max_retries: int = 8, retry_gap_s: float = 3.0) -> None:
    """后台尽力设置 `gen/` 前缀公开读策略(幂等, 持久化在桶上, 只需成功一次)。

    【关键修复 2026-07-28】原实现直接 set_bucket_policy, 但 pea-media 桶是首次 store
    时才由 _ensure_bucket 懒创建 -> worker 启动瞬间桶还不存在 -> set_bucket_policy 全部
    重试失败 -> 策略从未生效 -> gen/ 对象永远私有 -> 浏览器 403 裂图。现改为: 每次重试前
    先 ensure_bucket 建桶, 成功即置 _policy_ok, 首图也能匿名访问。
    """
    import time

    client = _get_client()
    bucket = settings.minio_bucket
    prefix = settings.media_public_prefix
    policy = _public_policy(bucket, prefix)
    for attempt in range(1, max_retries + 1):
        # 关键修复: 每次尝试前确保桶存在(首启时桶尚未懒创建)。
        try:
            _ensure_bucket()
        except Exception as e:  # noqa: BLE001
            logger.warning("ensure bucket before policy failed: %s", e)
        if _apply_policy_now(client, bucket, policy):
            global _policy_ok
            _policy_ok = True
            logger.info("bucket public policy applied (attempt %d)", attempt)
            return
        logger.warning("set public policy attempt %d/%d failed", attempt, max_retries)
        if attempt < max_retries:
            time.sleep(retry_gap_s)
    logger.warning("set public policy gave up after %d attempts; gen/ objects may be private", max_retries)


def ensure_public_policy_once() -> None:
    """热路径兜底: 若启动线程未能设上策略(如首启桶还不存在), 首次存图时再试一次。

    仅在 _policy_ok 为 False 时执行(成功后置位, 之后所有 store 跳过)。命中后最多阻塞
    10s(常态 <1s), 仅影响极个别首图, 换取"第一张图也必然可匿名访问"。
    """
    global _policy_ok
    if _policy_ok:
        return
    client = _get_client()
    bucket = settings.minio_bucket
    prefix = settings.media_public_prefix
    policy = _public_policy(bucket, prefix)
    try:
        _ensure_bucket()
    except Exception as e:  # noqa: BLE001
        logger.warning("lazy ensure bucket failed: %s", e)
    if _apply_policy_now(client, bucket, policy):
        _policy_ok = True
    else:
        logger.warning("lazy set public policy failed; gen/ object may be private")


def _guess_ext(url: str, content_type: str | None, media_type: str) -> str:
    if content_type and "/" in content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip(), strict=False)
        if ext:
            return ext
    ext = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "", strict=False)
    if ext:
        return ext
    return ".mp4" if media_type == "video" else ".png"


def _build_key(media_type: str, user_id: int | str | None, ext: str) -> str:
    owner = str(user_id) if user_id not in (None, "", 0) else "anon"
    date_dir = datetime.now().strftime("%Y/%m/%d")
    return f"{settings.media_public_prefix}/{media_type}s/{owner}/{date_dir}/{uuid.uuid4().hex}{ext}"


def store_bytes(
    data: bytes,
    media_type: str,
    *,
    user_id: int | str | None = None,
    content_type: str | None = None,
) -> str:
    """上传字节到公开前缀, 返回可直接访问的 CDN URL。失败抛出 (由上层转失败+退款)。"""
    _ensure_bucket()
    # 兜底: 若启动线程未设上公开策略(首启桶还不存在), 首次存图时补设一次,
    # 确保 gen/ 对象匿名可读(否则浏览器 403 裂图)。成功后 _policy_ok 置位, 后续跳过。
    ensure_public_policy_once()
    ct = content_type or ("video/mp4" if media_type == "video" else "image/png")
    ext = mimetypes.guess_extension(ct.split(";")[0].strip(), strict=False) or (
        ".mp4" if media_type == "video" else ".png"
    )
    key = _build_key(media_type, user_id, ext)
    _get_client().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=ct,
    )
    logger.info("stored %s bytes=%d -> %s", media_type, len(data), key)
    return f"{settings.cdn_base_url}/{key}"


def store_from_url(
    external_url: str,
    media_type: str,
    *,
    user_id: int | str | None = None,
    timeout: int | None = None,
) -> str:
    """下载外部 URL 并转存, 返回自有 CDN URL。

    仅接受 http(s) 外链; 下载/上传任一失败均抛出 (真实生成必须暴露失败以触发退款,
    绝不静默返回原始临时链接)。
    """
    if not external_url or not external_url.startswith("http"):
        raise ValueError(f"invalid external media url: {external_url!r}")
    _ensure_bucket()
    # 兜底: 同 store_bytes, 首图前确保 gen/ 公开读策略已生效。
    ensure_public_policy_once()
    dl_timeout = timeout or settings.provider_image_timeout_s
    resp = requests.get(
        external_url,
        timeout=(settings.provider_http_connect_timeout_s, dl_timeout),
        stream=True,
    )
    resp.raise_for_status()
    data = resp.content
    if not data:
        raise ValueError("downloaded empty media body")
    content_type = resp.headers.get("Content-Type")
    ext = _guess_ext(external_url, content_type, media_type)
    key = _build_key(media_type, user_id, ext)
    _get_client().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=(content_type or "application/octet-stream"),
    )
    logger.info("rehosted %s from %s -> %s (%d bytes)", media_type, external_url[:80], key, len(data))
    return f"{settings.cdn_base_url}/{key}"
