"""
timing_probe_real_image.py — 直接打 BFF, 测真实模型出图的端到端耗时 (不含 UI 开销)。

目的: 验证 ADR-003 超时整改后, 慢生成是否"单次跑完、不再 110s 误杀+重试翻倍"。
对比基线: 整改前观测到单次 route() took 214.65s (110s 超时 -> 重试)。

输出: 受理 -> 轮询 GET /generation/jobs/:jobId 直到 done/failed, 打印总耗时与结果 URL。
"""
import json, time, urllib.request, urllib.error

API = "http://localhost:4100"
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"tp_{STAMP}@pea.ai"
PW = "Password123"


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    st, _ = call("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    print(f"[auth] register -> {st}")
    _, data = call("POST", "/auth/login", body={"email": EMAIL, "password": PW})
    tok = data["token"]
    call("POST", "/plans/purchase", token=tok, body={"planId": "free"})

    st, models = call("GET", "/models/available?type=image", token=tok)
    print(f"[models] status={st} count={len(models)}")
    for m in models[:6]:
        print(f"   - id={m.get('id')} name={m.get('displayName')} model={m.get('modelName')}")
    if not models:
        print("NO IMAGE MODELS — abort")
        return
    mid = models[0]["id"]

    t0 = time.time()
    st, job = call("POST", "/generation/node", token=tok, body={
        "type": "image",
        "prompt": "一只在星空下奔跑的橘猫，霓虹城市，电影感，高清",
        "model": mid,
        "params": {"size": "1024x1024"},
    })
    print(f"[accept] status={st} jobId={job.get('jobId')} status={job.get('status')}")
    jid = job["jobId"]

    last = None
    while True:
        _, d = call("GET", f"/generation/jobs/{jid}", token=tok)
        s = d.get("status")
        if s != last:
            print(f"   t={time.time()-t0:6.1f}s status={s}")
            last = s
        if s in ("done", "failed", "refunded"):
            dt = time.time() - t0
            url = d.get("resultUrl") or ""
            print(f"[RESULT] status={s} elapsed={dt:.1f}s "
                  f"real_cdn={url.startswith('https://platform-outputs.agnes-ai.space')} "
                  f"url={url[:70]}")
            break
        if time.time() - t0 > 400:
            print("[TIMEOUT] >400s, abort")
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
