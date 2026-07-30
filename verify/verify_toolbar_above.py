"""Verify the multi-select toolbar floats ABOVE the selection box (issue 3).

Reuses the mocked-route harness from verify_selection_visibility.py so it runs
against the dev server on :5180 without a live backend. After a box-select of two
nodes we assert:
  - .multiselect-toolbar exists and is portaled to document.body
  - computed position == fixed and z-index == 100
  - the toolbar sits ABOVE the selection rect (toolbar.bottom <= rect.top + tol)
"""
import os, re, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "toolbar_%s@pea.ai" % STAMP
PW = "Password123"
errors = []
log = []
checks = []

def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))

def shot(page, name):
    p = os.path.join(SHOTS, "tb_%s_%s.png" % (name, STAMP))
    page.screenshot(path=p)
    log.append("[shot] %s -> %s" % (name, p))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    def on_console(m):
        if m.type == "error":
            errors.append("console.error: %s" % m.text)
    def on_pageerror(e):
        errors.append("pageerror: %s" % e)
    page.on("console", on_console)
    page.on("pageerror", on_pageerror)

    st, _ = urllib.request.urlopen(urllib.request.Request(
        BASE + "/auth/register", method="POST",
        data=json.dumps({"email": EMAIL, "password": PW}).encode(),
        headers={"Content-Type": "application/json"}), timeout=15).read().decode() if False else (None, None)
    tok = None
    try:
        tok = json.loads(urllib.request.urlopen(
            urllib.request.Request(BASE + "/auth/login", method="POST",
                data=json.dumps({"email": EMAIL, "password": PW}).encode(),
                headers={"Content-Type": "application/json"}), timeout=15).read().decode())["token"]
    except Exception as ex:
        log.append("[warn] login failed (tolerated): %s" % ex)

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok or "x")
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})

    def mock_json(payload):
        return lambda route, request: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload))
    page.route("**/users/me", mock_json({"id": 1, "email": EMAIL, "displayName": "Tester",
                                          "balance": 0, "isAdmin": False, "planLevel": 0,
                                          "effectivePlanLevel": 0, "planExpiresAt": None}))
    page.route("**/auth/refresh", mock_json({"token": tok or "x"}))
    page.route(re.compile(r"http://[^/]+/canvases.*"), mock_json({"ok": True, "data": []}))
    page.route(re.compile(r"http://[^/]+/models/.*"), mock_json([]))
    page.route(re.compile(r"http://[^/]+/files/.*"), mock_json({"ok": True}))
    page.route(re.compile(r"http://[^/]+/providers/.*"), mock_json({"ok": True}))
    page.route(re.compile(r"http://[^/]+/generation/.*"), mock_json({"ok": True}))

    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.reload(wait_until="domcontentloaded")
    try:
        page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
    except Exception as ex:
        log.append("[warn] window.__canvas never appeared: %s" % ex)
    page.wait_for_timeout(1000)

    setup_js = (
        "const ui = window.__ui.getState();"
        "const cs = window.__canvas.getState();"
        "ui.setActive('canvas');"
        "cs.setCanvasMeta(1, 1, 'toolbar test');"
        "cs.loadGraph(["
        "{id:'n1', type:'pea', position:{x:320,y:300}, width:340, height:340, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 1</div>'}},"
        "{id:'n2', type:'pea', position:{x:680,y:300}, width:340, height:340, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 2</div>'}}"
        "], [], 1);"
    )
    page.evaluate(setup_js)
    page.wait_for_timeout(1200)
    page.wait_for_selector(".react-flow__node[data-id='n1']", timeout=10000)
    page.wait_for_selector(".react-flow__node[data-id='n2']", timeout=10000)

    # 注入高对比样式，让选择框在截图里清晰可见（仅用于验证）
    page.add_style_tag(content="""
        .react-flow__selection, .react-flow__nodesselection-rect {
            background: rgba(255,0,0,0.35) !important;
            border: 2px solid red !important;
        }
    """)

    # Box-select both nodes
    page.mouse.move(260, 250)
    page.mouse.down()
    page.mouse.move(940, 500, steps=30)
    page.wait_for_timeout(400)
    page.mouse.up()
    page.wait_for_timeout(700)

    sel = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after drag: %s" % sel)
    checks.append(("框选选中两个节点", isinstance(sel, list) and len(sel) == 2))

    # Toolbar assertions
    tb = page.locator(".multiselect-toolbar")
    try:
        tb.wait_for(state="visible", timeout=5000)
        checks.append(("多选工具条出现", True))
    except Exception:
        checks.append(("多选工具条出现", False))

    info = page.evaluate("""() => {
        const t = document.querySelector('.multiselect-toolbar');
        if (!t) return {found: false};
        const cs = window.getComputedStyle(t);
        const rect = t.getBoundingClientRect();
        const selBox = document.querySelector('.react-flow__nodesselection-rect') || document.querySelector('.react-flow__selection');
        const srect = selBox ? selBox.getBoundingClientRect() : null;
        return {
            found: true,
            portaledToBody: t.parentElement === document.body,
            parentTag: t.parentElement ? t.parentElement.tagName : null,
            position: cs.position,
            zIndex: cs.zIndex,
            toolbarBottom: rect.bottom,
            toolbarTop: rect.top,
            toolbarRight: rect.right,
            toolbarLeft: rect.left,
            selBoxTop: srect ? srect.top : null,
            selBoxBottom: srect ? srect.bottom : null,
            selBoxRight: srect ? srect.right : null,
            selBoxLeft: srect ? srect.left : null
        };
    }""")
    log.append("[toolbar] %s" % json.dumps(info, ensure_ascii=False))

    # 诊断选择框元素类型与样式
    diag = page.evaluate("""() => {
        const r = document.querySelector('.react-flow__nodesselection-rect') || document.querySelector('.react-flow__selection');
        if (!r) return {found: false};
        const cs = window.getComputedStyle(r);
        return {
            tag: r.tagName,
            className: r.className,
            width: r.getBoundingClientRect().width,
            height: r.getBoundingClientRect().height,
            background: cs.backgroundColor,
            border: cs.border,
            fill: cs.fill,
            stroke: cs.stroke,
            zIndex: cs.zIndex,
        };
    }""")
    log.append("[diag] selection rect: %s" % json.dumps(diag, ensure_ascii=False))

    if info.get("found"):
        checks.append(("工具条渲染在 document.body (portal)", info.get("portaledToBody") is True))
        checks.append(("工具条 position:fixed", info.get("position") == "fixed"))
        checks.append(("工具条 z-index:100", str(info.get("zIndex")) == "100"))
        # 必须在选择框上方：工具条底边 <= 选择框顶边（允许 2px 容差）
        if info.get("selBoxTop") is not None:
            above = info["toolbarBottom"] <= info["selBoxTop"] + 2
            checks.append(("工具条在选择框上方", above))
        else:
            checks.append(("工具条在选择框上方", False))

    shot(page, "after_select")

    # 特写：选择框右上角，检查顶边/右边边框是否连续、未被工具条阴影压断
    if info.get("selBoxTop") and info.get("selBoxRight"):
        corner_clip = {
            "x": max(0, int(info["selBoxRight"]) - 100),
            "y": max(0, int(info["selBoxTop"]) - 50),
            "width": 120,
            "height": 90,
        }
        corner_path = os.path.join(SHOTS, "tb_corner_%s.png" % STAMP)
        page.screenshot(path=corner_path, clip=corner_clip)
        log.append("[shot] corner -> %s" % corner_path)
        # 再截一张顶边全貌（从选框左到右），看顶边是否完整
        top_clip = {
            "x": max(0, int(info["selBoxLeft"]) - 20),
            "y": max(0, int(info["selBoxTop"]) - 30),
            "width": int(info["selBoxRight"] - info["selBoxLeft"]) + 60,
            "height": 60,
        }
        top_path = os.path.join(SHOTS, "tb_top_edge_%s.png" % STAMP)
        page.screenshot(path=top_path, clip=top_clip)
        log.append("[shot] top_edge -> %s" % top_path)

        # 高对比染色截图：确认右上角几何上连续无断裂
        red_corner_path = os.path.join(SHOTS, "tb_red_corner_%s.png" % STAMP)
        page.screenshot(path=red_corner_path, clip=corner_clip)
        log.append("[shot] red_corner -> %s" % red_corner_path)

    browser.close()

passed = sum(1 for _, ok in checks if ok)
total = len(checks)
print("\n".join(log))
print("\n" + "=" * 50)
print("多选工具条层级 E2E: %d/%d PASS" % (passed, total))
print("=" * 50)
for name, ok in checks:
    print("  %s  %s" % ("PASS" if ok else "FAIL", name))
if errors:
    print("\n--- ERRORS ---")
    print("\n".join(errors))
print("DONE")
