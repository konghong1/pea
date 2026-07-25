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
from minio import Minio

from app.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None
_init_lock = threading.Lock()
_bucket_ready = False


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


def ensure_public_policy(max_retries: int = 8, retry_gap_s: float = 3.0) -> None:
    """后台尽力设置 `gen/` 前缀公开读策略(幂等, 持久化在桶上, 只需成功一次)。

    set_bucket_policy 在 MinIO 冷启动/部分部署下偶发缓慢(无内置超时), 若放在生成热路径
    会卡死整条链路。故放到 worker 启动时独立守护线程, 多次重试 + 每次 10s 护栏,
    成功即返回; 全部失败仅告警(此时 gen/ 对象可能私有, 前端裂图, 但生成本身不阻塞)。
    """
    import time

    client = _get_client()
    bucket = settings.minio_bucket
    prefix = settings.media_public_prefix
    policy = _public_policy(bucket, prefix)
    for attempt in range(1, max_retries + 1):
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
        if box.get("ok"):
            logger.info("bucket public policy applied (attempt %d)", attempt)
            return
        logger.warning(
            "set public policy attempt %d/%d failed: %s",
            attempt, max_retries, box.get("e", "<timeout>"),
        )
        if attempt < max_retries:
            time.sleep(retry_gap_s)
    logger.warning("set public policy gave up after %d attempts; gen/ objects may be private", max_retries)


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
