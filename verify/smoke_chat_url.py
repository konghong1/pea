import json
import os
import sys
import time
import urllib.request
import urllib.error

API = "http://localhost:4100"
ECHO_LOG = r"C:\workspace\pea\verify\.echo_path.log"

ADMIN = ("admin@pea.ai", "admin12345")
VERIFY = ("verify@pea.ai", "password123")

PROVIDER_ID = "echo-v1-provider"
MODEL_ID = "echo-v1-model"


def post(path, token, body, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode()
            return (r.status, txt if raw else json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return (e.code, e.read().decode())


def login(email, pw):
    st, body = post("/auth/login", None, {"email": email, "password": pw})
    if st not in (200, 201) or not body:
        raise RuntimeError(f"login failed {email}: {st} {body}")
    return body["token"]


def delete(path, token):
    req = urllib.request.Request(API + path, method="DELETE")
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    # 0) 清空 echo 日志
    open(ECHO_LOG, "w", encoding="utf-8").close()

    # 1) admin 登录 + 建 provider(base_url 带 /v1) + model
    atok = login(*ADMIN)
    st, body = post("/admin/providers", atok, {
        "id": PROVIDER_ID,
        "name": "echo-v1",
        "providerType": "text",
        "baseUrl": "http://host.docker.internal:9199/v1",
        "apiKey": "x",
        "kind": "text",
        "enabled": True,
    })
    print(f"[setup] create provider -> {st}")
    st, body = post("/admin/models", atok, {
        "id": MODEL_ID,
        "providerId": PROVIDER_ID,
        "modelName": MODEL_ID,
        "modelType": "text",
        "enabled": True,
        "minPlanLevel": 0,
        "pricing": {"base": 1},
    })
    print(f"[setup] create model -> {st}")

    # 2) verify 登录 + 真实 SSE 聊天 (走修复后的 BFF URL 构造)
    vtok = login(*VERIFY)
    body = json.dumps({
        "nodeId": "n1",
        "kind": "text",
        "prompt": "hello",
        "model": MODEL_ID,
    }).encode()
    req = urllib.request.Request(API + "/chat/stream", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + vtok)

    got_done = False
    got_delta = False
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            for line in r:
                s = line.decode().rstrip("\n")
                if s.startswith("event:"):
                    ev = s.split(":", 1)[1].strip()
                    if ev == "done":
                        got_done = True
                if s.startswith("data:") and "delta" in s:
                    got_delta = True
    except urllib.error.HTTPError as e:
        print(f"[FAIL] /chat/stream HTTP {e.code}: {e.read().decode()[:300]}")
        cleanup(atok)
        return 2

    print(f"[chat] got_delta={got_delta} got_done={got_done}")

    # 3) 读 echo 服务器实际收到的路径
    time.sleep(0.5)
    try:
        with open(ECHO_LOG, "r", encoding="utf-8") as f:
            paths = [p.strip() for p in f if p.strip()]
    except FileNotFoundError:
        paths = []
    print(f"[echo] received paths = {paths}")

    cleanup(atok)

    # 4) 断言
    ok = got_done and paths and paths[0] == "/v1/chat/completions" and "/v1/v1" not in paths[0]
    if ok:
        print(f"\n[PASS] 文本节点 SSE 打到 {paths[0]} (单一 /v1), 上游 404 已修复")
        return 0
    print(f"\n[FAIL] got_done={got_done}, echo_path={paths}")
    return 1


def cleanup(atok):
    delete(f"/admin/models/{MODEL_ID}", atok)
    delete(f"/admin/providers/{PROVIDER_ID}", atok)
    print("[cleanup] removed temp provider/model")


if __name__ == "__main__":
    sys.exit(main())
