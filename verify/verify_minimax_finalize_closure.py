"""验证 MiniMax 视频异步终态的 OUR 侧闭环 (finalize_job: 转存 MinIO -> 写库 -> 发事件)。

为什么这么验: MiniMax 账户当前 insufficient_balance (1008), 真实视频生成被挡, 无法走完
「succeeded -> download_url」。但终态链的「转存+写库」是我们自己的代码, 与外部是否出图无关:
  - 转存 = storage.store_from_url 内部用 _get_client().put_object 写入 MinIO; 这里直接用
    storage.store_bytes (同一 put_object 路径) 上传样例字节, 拿到自有 CDN URL, 证明 转存 可用。
  - 写库 = finalize_job -> db.update_job_status(DONE, result_json=...) 并把 url 替换为自有 CDN。
本脚本: 建行 -> store_bytes 转存拿 CDN url -> finalize_job(url) -> 读回确认 done + result_json
含 rehosted(自有) url。等价于 completer 在 DONE 时做的事, 仅省去"外部下载"这一步(纯 httpx GET)。

运行 (cwd=pea-server):
  docker compose -f pea-server/docker-compose.yml exec -T generation-orchestrator \\
    sh -c "cd /app && python verify_minimax_finalize_closure.py"
"""
from __future__ import annotations

import json
import sys
import time
import traceback

sys.path.insert(0, "/app")

from app.async_core.engine import ensure_started
from app import db, storage
from app.async_core.dispatcher import finalize_job

# 样例视频字节 (最小 mp4 头, 仅用于验证 MinIO 上传+写库闭环, 非真实视频)
SAMPLE_MP4 = (
    b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom\x00\x00\x00\x08free"
    b"PEA-VERIFY-Payload-MiniMax-video-terminal-state"
)


def log(*a):
    print(*a, flush=True)


def step(name, fn):
    log(f"\n=== STEP {name} ===")
    try:
        return fn()
    except Exception:
        log(f"!!! STEP {name} FAILED:")
        traceback.print_exc()
        raise


def main() -> int:
    print("MAIN START", flush=True)
    ensure_started()
    job_id = "verify-fin-" + str(int(time.time()))

    def do_insert():
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generation_jobs "
                    "(id,user_id,type,status,payload_json,cost_tapies) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    [job_id, 1, "video", "running",
                     json.dumps({"prompt": "test", "model": "minimax-h3"}), 0],
                )
            conn.commit()
        log(f"[insert] row {job_id}")

    step("insert-row", do_insert)

    def do_rehost():
        # 直接用 store_bytes (与 store_from_url 同一个 put_object 路径) 验证 MinIO 转存
        url = storage.store_bytes(SAMPLE_MP4, "video", user_id=1,
                                  content_type="video/mp4")
        log(f"[rehost] -> {url}")
        return url

    rehosted_url = step("rehost(minio)", do_rehost)

    def do_finalize():
        finalize_job(job_id, 1, "video", True,
                     result={"url": rehosted_url, "urls": [rehosted_url],
                             "provider": "minimax", "usage": {}})
        log("[finalize] called")

    step("finalize", do_finalize)

    def do_read():
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id,status,result_json FROM generation_jobs WHERE id=%s", [job_id])
                return cur.fetchone()

    row = step("read-back", do_read)
    status = row["status"]
    rj = json.loads(row["result_json"])
    final_url = rj.get("url", "")
    rehosted = ("minio" in final_url) or ("/media" in final_url) or ("vicp.fun" in final_url)
    log(f"\nSTATUS     : {status}")
    log(f"RESULT_URL : {final_url}")
    log(f"REHOSTED   : {rehosted}  (外部临时 URL -> 自有稳定 CDN)")
    ok = status == "done" and rehosted
    log(f"VERDICT    : {'PASS 转存+写库闭环' if ok else 'CHECK 未达成'}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
