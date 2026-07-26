"""生成 Worker: 消费 Redis Streams -> 调外部模型 -> 回写状态 -> 发布事件.

失败 -> 置 failed -> 补偿退款 -> 通知 (ARCH D5/D9/D10).
每用户并发上限为软护栏(见 _in_flight); 生产环境替换为 Redis 原子计数器以防单用户打满。
"""
from __future__ import annotations

import json
import os
import threading
import time

from app import db, models, storage, usage
from app.compensation import refund_on_failure
from app.config import settings
from app.llm_router import route, _mock
from app.redis_conn import client, publish_event
from services.shared.events import GEN_QUEUE, job_updated, notification

GROUP = "pea-workers"
CONSUMER = "worker-1"
FAST_QUEUE = f"{GEN_QUEUE}:fast"
STREAMS = [GEN_QUEUE, FAST_QUEUE]

_in_flight_lock = threading.Lock()
_in_flight: dict[int, int] = {}
_stop = False


def _enter(user_id: int) -> bool:
    with _in_flight_lock:
        cur = _in_flight.get(user_id, 0)
        if cur >= settings.per_user_concurrency:
            return False
        _in_flight[user_id] = cur + 1
        return True


def _leave(user_id: int) -> None:
    with _in_flight_lock:
        _in_flight[user_id] = max(0, _in_flight.get(user_id, 1) - 1)


# 硬超时护栏：真实提供商调用（DNS/连接黑洞）可能既不返回也不抛异常，导致单线程
# worker 永久阻塞、任务卡 running。超过此时间强制回退 MockProvider，保证任务总能走到终态。
# 阈值必须 > PEA_PROVIDER_IMAGE_TIMEOUT_S，否则会把正常的慢速生成（Agnes 18~77s 且有波动）
# 误判为卡死而强制 mock。这里派生为 image_timeout + 30s，随 compose 配置自动联动。
_HARD_TIMEOUT = float(os.environ.get("PEA_WORKER_HARD_TIMEOUT_S", str(int(settings.provider_image_timeout_s) + 30)))


def _route_with_watchdog(payload: dict):
    """在独立守护线程执行 route()，加硬超时护栏。

    返回 (GenerationResult, None) 正常；或 (None, Exception) 表示 route 内部抛错
    （交由上层置 FAILED + 退款）；若超时仍未返回则强制 Mock 兜底。
    """
    box: dict = {}
    err: dict = {}

    def _run() -> None:
        try:
            box["r"] = route(payload)
        except Exception as e:  # noqa: BLE001
            err["e"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(_HARD_TIMEOUT)
    if "r" in box:
        print(f"[worker] route() completed normally, provider={box['r'].provider}, url={box['r'].url[:80]}")
        return box["r"], None
    if "e" in err:
        print(f"[worker] route() raised exception: {err['e']}")
        return None, err["e"]
    print(f"[worker] route() exceeded {_HARD_TIMEOUT}s hard timeout (model={payload.get('model')}, type={payload.get('type')}), forcing mock fallback")
    return _mock.generate(payload), None


def _ensure_group() -> None:
    r = client()
    for stream in STREAMS:
        try:
            r.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except Exception:  # noqa: BLE001  (BUSYGROUP 已存在)
            pass


def _process(job_id: str, payload: dict) -> None:
    user_id = int(payload.get("user_id", 0))
    if not _enter(user_id):
        # 超过每用户并发: 本轮跳过(不 ack), 留给下次调度。生产应走 Redis 令牌桶。
        print(f"[worker] user {user_id} at concurrency cap, defer {job_id}")
        time.sleep(0.5)
        return
    try:
        db.update_job_status(job_id, models.JobStatus.RUNNING.value)
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="running", progress=0.1,
        ))
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="running", progress=0.6,
        ))
        # 确保 job_id 进入 payload, 供 MockProvider 生成确定性占位 URL。
        payload.setdefault("job_id", job_id)
        _t0 = time.time()
        result, route_err = _route_with_watchdog(payload)
        _dt = time.time() - _t0
        print(f"[worker] route() for job {job_id} took {_dt:.2f}s (provider={result.provider if result else 'ERR'})")
        if route_err is not None:
            raise route_err
        usage_dict = result.usage or {}
        result_obj: dict = {
            "url": result.url,
            "urls": result.urls,  # 多图生成时的所有图片 URL
            "provider": result.provider,
            "usage": usage_dict
        }
        if result.text is not None:
            result_obj["text"] = result.text
        db.update_job_status(
            job_id, models.JobStatus.DONE.value,
            result_json=json.dumps(result_obj, ensure_ascii=False),
            cost_tapies=int(payload.get("cost_tapies", settings.default_cost_tapies)),
            usage_json=json.dumps(usage_dict, ensure_ascii=False),
        )
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="done", result_url=result.url,
            result_urls=result.urls if result.urls else None,  # 新增多图支持
            cost=int(payload.get("cost_tapies", settings.default_cost_tapies)),
        ))
        # Phase3: 生成后钩子 — 把 token 用量写入 usage_records (审计/统计, 不动计费)
        usage.record_usage(
            job_id=job_id, user_id=user_id, node_type=payload.get("type", "image"),
            model=payload.get("model"), provider=result.provider,
            platform_config_id=payload.get("platform_config_id"),
            usage=usage_dict,
        )
    except Exception as e:  # noqa: BLE001
        db.update_job_status(job_id, models.JobStatus.FAILED.value)
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="failed", error=str(e)[:500],
        ))
        publish_event(notification(
            user_id=user_id, title="生成失败", body=str(e)[:200], level="error",
        ))
        refunded = refund_on_failure(job_id, user_id, int(payload.get("cost_tapies", 0)))
        if refunded:
            # 退款成功 -> 状态机 FAILED -> REFUNDED 合法跳转 (原实现永远停在 FAILED, refunded 状态形同虚设)
            try:
                db.update_job_status(job_id, models.JobStatus.REFUNDED.value)
            except Exception as e:  # noqa: BLE001
                print(f"[worker] mark refunded failed {job_id}: {e}")
    finally:
        _leave(user_id)


def run_once() -> None:
    r = client()
    resp = r.xreadgroup(
        GROUP, CONSUMER,
        {GEN_QUEUE: ">", FAST_QUEUE: ">"},
        count=2, block=200,
    )
    if not resp:
        return
    for _stream, messages in resp:
        for msg_id, fields in messages:
            try:
                job_id = fields["job_id"]
                payload = json.loads(fields["payload"])
                _process(job_id, payload)
                r.xack(_stream, GROUP, msg_id)
            except Exception as e:  # noqa: BLE001
                print(f"[worker] bad message {msg_id}: {e}")


def run_forever() -> None:
    _ensure_group()
    # 后台尽力设置 gen/ 公开读策略(幂等, 不阻塞生成热路径; 冷启动慢调用由重试护栏兜底)。
    threading.Thread(target=storage.ensure_public_policy, daemon=True).start()
    print("[worker] started")
    while not _stop:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001
            print(f"[worker] loop error: {e}")
            time.sleep(1)


def start() -> threading.Thread:
    t = threading.Thread(target=run_forever, daemon=True)
    t.start()
    return t
