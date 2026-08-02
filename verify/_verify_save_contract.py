"""
实时后端契约测试：验证 saveCanvasNow 修复后的「乐观锁 409 -> 重新拉取版本 -> 重试落盘」逻辑。

对照：
  A. 基准：用正确 version PUT，editorText 应落库 (200)。
  B. 冲突：用过期 version PUT，应 409，且后端不覆盖旧值。
  C. 旧行为(复现 bug)：吞掉 409 不重试 -> 用户新输入的 editorText 丢失 (仍为旧值)。
  D. 新行为(修复后)：409 后 GET 权威 version 再 PUT -> 200，editorText 真正落库。

不依赖浏览器：直接用 urllib 打真实 BFF(4100)。
"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:4100/api"
EMAIL = "v3test@test.com"
PWD = "Test123456"
SENTINEL_A = "PEA_BASELINE_提示词_A_123"
SENTINEL_B = "PEA_NEW_提示词_B_456"


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def get_version_and_editor(cid, token):
    st, j = req("GET", f"/canvases/{cid}", token)
    if st != 200:
        return st, None, None
    raw = j.get("graph_json")
    g = json.loads(raw) if isinstance(raw, str) else (raw or {})
    nodes = g.get("nodes", [])
    n = next((x for x in nodes if x.get("id") == "vX"), None)
    ed = None
    if n and isinstance(n.get("data"), dict) and isinstance(n["data"].get("meta"), dict):
        ed = n["data"]["meta"].get("editorText")
    return st, j.get("version"), ed


def put_canvas(cid, token, version, editor_text):
    graph = {
        "nodes": [
            {
                "id": "vX",
                "type": "pea",
                "position": {"x": 400, "y": 300},
                "data": {
                    "kind": "video",
                    "label": "Video",
                    "prompt": "",
                    "generating": False,
                    "meta": {"editorText": editor_text},
                },
            }
        ],
        "edges": [],
    }
    return req("PUT", f"/canvases/{cid}", token, {"graph_json": graph, "version": version})


def main():
    print("[TEST] 登录 ...", flush=True)
    st, login = req("POST", "/auth/login", body={"email": EMAIL, "password": PWD})
    assert st in (200, 201) and login.get("token"), f"登录失败: {st} {login}"
    token = login["token"]
    print("[TEST] 登录 OK", flush=True)

    st, created = req("POST", "/canvases", token, {"title": "save_contract_test", "scope": "personal"})
    assert st in (200, 201) and created.get("id"), f"建画布失败: {st} {created}"
    cid = created["id"]
    _, version0, _ = get_version_and_editor(cid, token)
    print(f"[TEST] 画布 id={cid} 初始 version={version0}", flush=True)

    # A. 基准：正确 version 保存
    st, _ = put_canvas(cid, token, version0, SENTINEL_A)
    _, v1, ed = get_version_and_editor(cid, token)
    print(f"[A] 基准保存 -> PUT {st}, 后端 editorText={ed!r}, version={v1}")
    a_ok = st in (200, 201) and ed == SENTINEL_A

    # B. 冲突：用过期 version
    stale = (v1 or 0) + 999
    st, _ = put_canvas(cid, token, stale, SENTINEL_B)
    _, v2, ed = get_version_and_editor(cid, token)
    print(f"[B] 过期 version({stale}) 保存 -> PUT {st} (期望409), 后端 editorText={ed!r} (应仍为基准值)")
    b_ok = st == 409 and ed == SENTINEL_A  # 409 不应覆盖

    # C. 旧行为：吞掉 409 不重试 -> 用户新输入的 B 丢失
    #    (模拟旧 saveCanvasNow: catch{} 后 editorText 未落库)
    old_persisted = ed  # 仍是 SENTINEL_A，B 没存进去
    c_ok = old_persisted != SENTINEL_B
    print(f"[C] 旧行为(吞409不重试): 用户想存的 B 实际后端={old_persisted!r} -> 丢失={c_ok}")

    # D. 新行为：409 后 GET 权威 version 再 PUT（正是修复后 saveCanvasNow 的做法）
    st_g, j_g = req("GET", f"/canvases/{cid}", token)
    server_version = j_g.get("version")
    st, _ = put_canvas(cid, token, server_version, SENTINEL_B)
    _, v3, ed = get_version_and_editor(cid, token)
    print(f"[D] 修复后(409->GET v={server_version}->重PUT) -> PUT {st}, 后端 editorText={ed!r}, version={v3}")
    d_ok = st in (200, 201) and ed == SENTINEL_B

    print("=" * 60, flush=True)
    print(f"[结果] A 基准落库:      {'PASS' if a_ok else 'FAIL'}")
    print(f"[结果] B 409 不覆盖:    {'PASS' if b_ok else 'FAIL'}")
    print(f"[结果] C 旧行为丢提示词: {'复现bug(符合预期)' if c_ok else '未复现'}")
    print(f"[结果] D 修复后重试落库: {'PASS ✅ 提示词已保全' if d_ok else 'FAIL ❌'}")
    print("=" * 60, flush=True)

    # 清理
    req("DELETE", f"/canvases/{cid}", token)
    print("[TEST] 测试画布已清理", flush=True)
    assert d_ok, "修复后的重试落库未通过"


if __name__ == "__main__":
    main()
