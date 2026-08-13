"""失败补偿: 生成失败后调用 BFF 内部退款接口退还 Tapies (ARCH D12 / ADR-006).

资深开发复核修复 (T-GEN-07):
  - 原实现退款失败仅 print 即返回, BFF 抖动会**永久丢钱**且无任何兜底。
  - 现加重试 + 指数退避; 返回 True 表示已成功退款 (worker 据此把 job 翻到 refunded)。
  - 每日对账脚本仍作为最后兜底 (见 scripts/reconcile_ledger.py)。

T-FIX-REFUND-201-2026-07-28:
  - 之前只把 status_code == 200 视为成功; 但 BFF /internal/billing/refund 实际
    返 201 Created (POST 创建成功), 旧逻辑把每次 refund 都判失败, 3 次重试
    全部 EXHAUSTED -> 积分靠每日对账脚本兜底, 用户体感"扣了但没退"。
  - 现改成"2xx 范围 + body.ok == True"才算成功; 4xx/5xx 维持重试 (BFF 真出错
    不放过, 仍兜底到对账脚本)。
"""
from __future__ import annotations

import time

import httpx

from app.config import settings

_MAX_RETRIES = 3


def refund_on_failure(job_id: str, user_id: int, cost_tapies: int, *, reason: str = "generation_failed") -> bool:
    """调用 BFF 内部退款. 成功返回 True; 穷尽重试仍失败返回 False (交对账脚本兜底)."""
    # BFF 全局路由前缀为 /api (main.ts setGlobalPrefix('api')), 内部退款接口真实路径
    # 为 /api/internal/billing/refund. 之前漏掉 /api 导致 404, 失败补偿退款全部落空,
    # 预扣积分只能靠每日对账脚本兜底. 见 2026-08-13 排查.
    url = f"{settings.bff_internal_base_url}/api/internal/billing/refund"
    last_err: str | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.post(
                    url,
                    json={
                        "userId": user_id,
                        "amount": cost_tapies,
                        "txnId": f"{job_id}:refund",
                        "jobId": job_id,
                        "reason": reason,
                    },
                    headers={"X-Service-Token": settings.internal_service_token},
                )
            # T-FIX-REFUND-201-2026-07-28: 2xx 都视为成功 (含 201 Created).
            # 4xx/5xx 才是真错误, 进入重试分支.
            if 200 <= r.status_code < 300 and r.json().get("ok") is True:
                return True
            last_err = f"status={r.status_code} body={(r.text or '')[:120]}"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:200]
        print(f"[compensation] refund attempt {attempt}/{_MAX_RETRIES} failed for {job_id}: {last_err}")
        if attempt < _MAX_RETRIES:
            time.sleep(min(2 ** attempt, 10))  # 指数退避, 上限 10s
    print(f"[compensation] refund EXHAUSTED for {job_id}: {last_err} (交由每日对账脚本兜底)")
    return False
