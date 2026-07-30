"""Reproduce + verify group error. Captures full pageerror stack."""
import os, re, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "grpf_%s@pea.ai" % STAMP
PW = "Password123"
errors = []
log = []

def ls_set(page, key, value):
    # 用 JSON.stringify 写入，避免把 JS 对象 toString 成 "[object Object]" 导致 app 解析崩溃
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))

def shot(page, name):
    p = os.path.join(SHOTS, "grpf_%s_%s.png" % (name, STAMP))
    page.screenshot(path=p)
    log.append("[shot] %s -> %s" % (name, p))

def apipost(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer %s" % token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    def on_console(m):
        if m.type == "error":
            errors.append("console.error: %s" % m.text)
    def on_pageerror(e):
        stack = getattr(e, "stack", "") or ""
        errors.append("pageerror: %s\nSTACK:\n%s" % (e, stack))
    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("response", lambda r: log.append("[http] %s -> %s" % (r.url, r.status)) if r.status >= 400 else None)

    st, _ = apipost("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    tok = None
    try:
        tok = json.loads(urllib.request.urlopen(
            urllib.request.Request(BASE + "/auth/login", method="POST",
                data=json.dumps({"email": EMAIL, "password": PW}).encode(),
                headers={"Content-Type": "application/json"}), timeout=15).read().decode())["token"]
    except Exception as ex:
        log.append("[warn] login failed: %s" % ex)
    cvs = None
    if tok:
        try:
            cvs = json.loads(urllib.request.urlopen(
                urllib.request.Request(BASE + "/canvases", method="POST",
                    data=json.dumps({"title": "group repro", "type": "personal"}).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer %s" % tok}), timeout=15).read().decode())
        except Exception as ex:
            log.append("[warn] create canvas failed: %s" % ex)

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok or "x")
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    # 让 App 启动即切到 canvas 视图，确保 CanvasEditor 挂载（否则 window.__canvas 不存在）
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})
    # mock 后端：Workspace 启动会 refreshMe/refreshToken；若 401 会触发登出跳转。
    # 这里直接 mock 成 200，避免测试被无关的后端状态带偏。
    page.route("**/users/me", lambda route, request: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"id": 1, "email": EMAIL, "displayName": "Tester",
                         "balance": 0, "isAdmin": False, "planLevel": 0,
                         "effectivePlanLevel": 0, "planExpiresAt": None})))
    page.route("**/auth/refresh", lambda route, request: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"token": tok or "x"})))
    # 用正则匹配所有可能 401 的 API，全部 mock 成 200，避免测试被后端状态带偏
    def mock_json(payload):
        return lambda route, request: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload))
    page.route(re.compile(r"http://[^/]+/canvases.*"), mock_json({"ok": True, "data": []}))
    page.route(re.compile(r"http://[^/]+/models/.*"), mock_json([]))
    page.route(re.compile(r"http://[^/]+/files/.*"), mock_json({"ok": True}))
    page.route(re.compile(r"http://[^/]+/providers/.*"), mock_json({"ok": True}))
    page.route(re.compile(r"http://[^/]+/generation/.*"), mock_json({"ok": True}))

    page.goto(BASE + "/", wait_until="domcontentloaded")
    try:
        page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
    except Exception as ex:
        log.append("[warn] window.__canvas never appeared: %s" % ex)
    page.wait_for_timeout(800)

    canvas_id = cvs["id"] if cvs else 1
    canvas_ver = cvs["version"] if cvs else 1
    canvas_title = cvs["title"] if cvs else "group repro"
    setup_js = (
        "const ui = window.__ui.getState();"
        "const cs = window.__canvas.getState();"
        "ui.setActive('canvas');"
        "cs.setCanvasMeta(%s, %s, %s);"
        "cs.loadGraph(["
        "{id:'n1', type:'pea', position:{x:300,y:300}, data:{kind:'text', label:'Text', html:'文本节点'}},"
        "{id:'n2', type:'pea', position:{x:700,y:300}, data:{kind:'image', label:'Image', resultUrl:'https://placehold.co/300x400/png?text=Image'}}"
        "], [], %s);"
        "cs.setSelection(['n1','n2']);"
    ) % (json.dumps(canvas_id), json.dumps(canvas_ver), json.dumps(canvas_title), json.dumps(canvas_ver))
    page.evaluate(setup_js)
    page.wait_for_timeout(1200)
    sel = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds = %s" % sel)
    ncount = page.evaluate("() => window.__canvas.getState().nodes.length")
    log.append("[state] before group node count = %s" % ncount)
    shot(page, "before_group")

    # 验证：点击选区外部（画布空白处）能取消选择
    page.mouse.click(1200, 700)
    page.wait_for_timeout(400)
    sel_out = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after click outside = %s" % sel_out)
    # 重新选中，准备打组
    page.evaluate("() => window.__canvas.getState().setSelection(['n1','n2'])")
    page.wait_for_timeout(400)

    gid = page.evaluate("() => window.__canvas.getState().groupNodes(['n1','n2'])")
    log.append("[state] groupNodes returned gid = %s" % gid)
    page.wait_for_timeout(1200)
    shot(page, "after_group")

    nodes = page.evaluate("() => window.__canvas.getState().nodes.map(n => ({id:n.id, type:n.type, parentNode:n.parentNode, extent:n.extent, selected:n.selected}))")
    log.append("[state] nodes after group: %s" % json.dumps(nodes, ensure_ascii=False))
    sel2 = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after group = %s" % sel2)

    page.mouse.click(200, 700)
    page.wait_for_timeout(500)
    shot(page, "click_outside")

    dom_js = (
        "() => {"
        "var all = Array.from(document.querySelectorAll('.react-flow__node')).map(function(el){return el.getAttribute('data-id');});"
        "var grp = document.querySelector('.pea-group-node') ? 'present' : 'absent';"
        "return JSON.stringify({all: all, grp: grp});"
        "}"
    )
    dom = page.evaluate(dom_js)
    try:
        dom_obj = json.loads(dom)
    except Exception:
        dom_obj = dom
    log.append("[dom] react-flow nodes: %s" % json.dumps(dom_obj, ensure_ascii=False))

    print("\n".join(log))
    print("\n===== ERRORS =====")
    print("\n".join(errors) if errors else "NO ERRORS")
    browser.close()
