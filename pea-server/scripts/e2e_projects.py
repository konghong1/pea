"""
pea 项目页 (T-M3-01 重做) 端到端冒烟 — 跑通 "新建 → 打开 → 编辑 → 重命名 → 团队 → 分享 → 删除" 全链路。

用法:
    python scripts/e2e_projects.py
前置:
    BFF 跑在 :4100, Web 跑在 :8088, MySQL/Redis 健康。
"""
import json
import time
import uuid
import urllib.request
import urllib.parse
import urllib.error

BASE = "http://localhost:4100"


def _req(method, path, *, token=None, body=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"content-type": "application/json", "accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            payload = resp.read().decode() or "{}"
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads((e.read() or b"{}").decode() or "{}")


def step(n, t):
    print(f"\n[{n}] {t}")


def assert_eq(a, b, label):
    if a == b:
        print(f"   ✓ {label} == {b!r}")
    else:
        print(f"   ✗ {label}: got {a!r}, expected {b!r}")
        raise SystemExit(1)


def assert_ne(a, b, label):
    if a != b:
        print(f"   ✓ {label} ({a!r} != {b!r})")
    else:
        print(f"   ✗ {label}: should differ from {b!r}")
        raise SystemExit(1)


def main():
    suffix = uuid.uuid4().hex[:8]
    email = f"proj_{suffix}@pea.ai"
    password = "Test12345"

    step(1, f"注册 {email}")
    code, r = _req("POST", "/auth/register", body={"email": email, "password": password, "displayName": f"Proj {suffix}"})
    assert_eq(code, 201, "register status")
    token = r["token"]
    user_id = r["user"]["id"]

    step(2, "登录（再次获取 token）")
    code, r = _req("POST", "/auth/login", body={"email": email, "password": password})
    assert_eq(code, 201, "login status")
    token = r["token"]

    step(3, "列出我的画布 (空)")
    code, items = _req("GET", "/canvases", token=token, params={"scope": "personal"})
    assert_eq(code, 200, "list status")
    print(f"   count={len(items)}")
    for it in items:
        print(f"     - id={it['id']} title={it['title']} scope={it['scope']} deleted_at={it.get('deleted_at')}")

    step(4, "新建画布 A（个人空间）")
    code, a = _req("POST", "/canvases", token=token, body={"title": "画布A", "scope": "personal"})
    assert_eq(code, 201, "create A")
    print(f"   id={a['id']} version={a['version']} scope={a['scope']}")
    a_id = a["id"]

    step(5, "新建画布 B（团队空间）")
    code, b = _req("POST", "/canvases", token=token, body={"title": "画布B", "scope": "team"})
    assert_eq(code, 201, "create B")
    b_id = b["id"]

    step(6, "打开画布 A（模拟编辑器自动加载）")
    code, g = _req("GET", f"/canvases/{a_id}", token=token)
    assert_eq(code, 200, "get A")
    assert_eq(g["title"], "画布A", "title")
    graph = g["graph_json"]
    if isinstance(graph, str):
        graph = json.loads(graph)
    assert_eq(graph.get("nodes"), [], "nodes empty")

    step(7, "自动保存：PUT /canvases/:id 带 graph 与 version (E3 乐观锁)")
    new_graph = {"nodes": [
        {"id": "n1", "type": "pea", "position": {"x": 0, "y": 0}, "data": {"label": "Text", "kind": "text", "prompt": "hello"}},
        {"id": "n2", "type": "pea", "position": {"x": 200, "y": 0}, "data": {"label": "Image", "kind": "image", "prompt": "cat"}},
    ], "edges": []}
    code, sv = _req("PUT", f"/canvases/{a_id}", token=token, body={"graph_json": new_graph, "version": g["version"]})
    assert_eq(code, 200, "save status")
    assert_eq(sv["version"], g["version"] + 1, "version bumped")

    step(8, "再次 GET 画布 A：节点内容应回放 (核心需求：只有点击才进入画布 + 带出工作内容)")
    code, g2 = _req("GET", f"/canvases/{a_id}", token=token)
    assert_eq(code, 200, "get A2")
    g2graph = g2["graph_json"]
    if isinstance(g2graph, str):
        g2graph = json.loads(g2graph)
    assert_eq(len(g2graph["nodes"]), 2, "node count persisted")
    assert_eq(g2graph["nodes"][0]["data"]["kind"], "text", "node[0] kind persisted")
    assert_eq(g2graph["nodes"][1]["data"]["prompt"], "cat", "node[1] prompt persisted")
    print(f"   ✓ 画布内容已成功从 DB 回放 (nodes={len(g2graph['nodes'])})")

    step(9, "重命名 (PATCH)")
    code, u = _req("PATCH", f"/canvases/{a_id}", token=token, body={"title": "画布A-改"})
    assert_eq(code, 200, "rename status")

    step(10, "移动至团队 (PATCH scope)")
    code, u = _req("PATCH", f"/canvases/{a_id}", token=token, body={"scope": "team"})
    assert_eq(code, 200, "move-to-team status")
    code, g3 = _req("GET", f"/canvases/{a_id}", token=token)
    assert_eq(g3["scope"], "team", "scope now team")

    step(11, "按 scope=team 列出应包含 A,B")
    code, team_items = _req("GET", "/canvases", token=token, params={"scope": "team"})
    assert_eq(code, 200, "list team status")
    ids = sorted([it["id"] for it in team_items])
    assert_eq(ids, sorted([a_id, b_id]), "team contains A and B")

    step(12, "生成分享链接")
    code, s = _req("POST", f"/canvases/{a_id}/share", token=token)
    assert_eq(code, 200, "share status")
    token_share = s["token"]
    print(f"   share_token={token_share}")

    step(13, "公开访问 /shared/:token (无 JWT)")
    code, pub = _req("GET", f"/shared/{token_share}")
    assert_eq(code, 200, "public read status")
    assert_eq(pub["title"], "画布A-改", "public title")

    step(14, "撤销分享")
    code, rv = _req("DELETE", f"/canvases/{a_id}/share", token=token)
    assert_eq(code, 200, "revoke share")
    code, pub2 = _req("GET", f"/shared/{token_share}")
    assert_eq(code, 404, "shared link revoked")

    step(15, "创建文件夹")
    code, f1 = _req("POST", "/canvases/folders", token=token, body={"name": "客户提案", "scope": "personal"})
    assert_eq(code, 201, "create folder")
    f1_id = f1["id"]
    code, fs = _req("GET", "/canvases/folders/list", token=token, params={"scope": "personal"})
    assert_eq(code, 200, "list folders")
    assert_ne(len([x for x in fs if x["id"] == f1_id]), 0, "folder present")

    step(16, "把画布 B 移入文件夹")
    code, m = _req("PATCH", f"/canvases/{b_id}", token=token, body={"folder_id": f1_id})
    assert_eq(code, 200, "move B to folder")
    code, gb = _req("GET", f"/canvases/{b_id}", token=token)
    assert_eq(gb["folder_id"], f1_id, "B in folder")

    step(17, "删除文件夹 -> B 应回到根目录 (ON DELETE SET NULL)")
    code, df = _req("DELETE", f"/canvases/folders/{f1_id}", token=token)
    assert_eq(code, 200, "delete folder")
    code, gb2 = _req("GET", f"/canvases/{b_id}", token=token)
    assert_eq(gb2["folder_id"], None, "B back to root")

    step(18, "删除画布 A")
    code, d = _req("DELETE", f"/canvases/{a_id}", token=token)
    assert_eq(code, 200, "delete A")
    code, ggone = _req("GET", f"/canvases/{a_id}", token=token)
    assert_eq(code, 404, "A gone")

    step(19, "乐观锁冲突测试 (用旧 version 二次保存应 409)")
    # 先正常保存一次把 B.version 从 1 -> 2
    code, _ = _req("PUT", f"/canvases/{b_id}", token=token, body={"graph_json": {"nodes": [], "edges": []}, "version": 1})
    assert_eq(code, 200, "first save bumps version")
    # 再用旧 version 1 应 409
    code, sv2 = _req("PUT", f"/canvases/{b_id}", token=token, body={"graph_json": {"nodes": [], "edges": []}, "version": 1})
    assert_eq(code, 409, "old version conflict")

    print("\n[OK] 全部断言通过 ✅")


if __name__ == "__main__":
    main()