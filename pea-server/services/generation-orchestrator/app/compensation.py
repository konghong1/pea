"""失败补偿: 生成失败后调用 BFF 内部退款接口退还 Tapies (ARCH D12 / ADR-006)."""
from __future__ import annotations

import httpx

from app.config import settings


def refund_on_failure(job_id: str, user_id: int, cost_tapies: int) -> bool:
    """调用 BFF 内部退款. 成功返回 True. 失败记录日志(对账脚本兜底)."""
    url = f"{settings.bff_internal_base_url}/internal/billing/refund"
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.post(
                url,
                json={
                    "userId": user_id,
                    "amount": cost_tapies,
                    "txnId": f"{job_id}:refund",
                    "jobId": job_id,
                    "reason": "generation_failed",
                },
                headers={"X-Service-Token": settings.internal_service_token},
            )
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception as e:  # noqa: BLE001
        # 退款失败: 不阻塞主流程, 依赖每日对账脚本 + 双记账本兜底 (ARCH R4)
        print(f"[compensation] refund failed for {job_id}: {e}")
        return False
