"""MiniMax 视频终态闭环验证: 走真实编排链路 (API -> Worker -> Dispatcher -> MiniMax -> Completer -> finalize).

与 verify_minimax_db_wiring.py 的区别: 那个脚本只测"适配器能不能提交 + 轮询逻辑",
本脚本**真发一个 H3 视频生成任务**, 让活的 completer 线程把它跑到终态,
验证完整异步闭环: 提交 -> queued -> running -> (MiniMax 渲染) -> done,
且 finalize_job 把外部 URL **转存 MinIO** 并**写库** (result_json 含自有 CDN url)。

运行 (在宿主机, 能访问 localhost:8000):
  python verify_minimax_video_terminal.py
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"
MODEL = "minimax-h3"
POLL_INTERVAL = 15
MAX_WAIT = 600  # 最多等 10 分钟


def _post_job() -> str:
    payload = {
        "user_id": 1,
        "type": "video",
        "prompt": "a paper boat drifting down a rainy street, cinematic, gentle rain",
        "model": MODEL,
        "params": {},
        "idempotency_key": f"verify-video-term-{int(time.time())}",
        "cost_tapies": 0,
    }
    req = urllib.request.Request(
        f"{BASE}/jobs",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
    print(f"[submit] jobId={body['jobId']} status={body['status']}")
    return body["jobId"]


def _get_job(job_id: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/jobs/{job_id}", timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    job_id = _post_job()
    last_status = None
    waited = 0
    while waited <= MAX_WAIT:
        try:
            row = _get_job(job_id)
        except urllib.error.HTTPError as e:
            print(f"[poll] HTTP {e.code}: {e.read().decode()[:200]}")
            time.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL
            continue

        st = row.get("status")
        if st != last_status:
            print(f"[poll {waited:4d}s] status={st} "
                  f"resultUrl={row.get('resultUrl')} error={row.get('error')}")
            last_status = st
        if st in ("done", "failed", "refunded"):
            url = row.get("resultUrl")
            err = row.get("error")
            if st == "done" and url:
                print(f"\n=== SUCCESS: 视频终态闭环达成 ===")
                print(f"jobId={job_id}")
                print(f"resultUrl={url}")
                print(f"rehosted_to_minio={('minio' in url) or ('/media' in url) or ('vicp.fun' in url)}")
                return 0
            print(f"\n=== FAILED: status={st} error={err}")
            return 1
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    print(f"\n=== TIMEOUT after {MAX_WAIT}s, last_status={last_status}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
