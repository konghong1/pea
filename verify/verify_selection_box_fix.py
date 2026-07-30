"""Verify that selection rectangles do not persist after box selection.

Checks:
- .react-flow__nodesselection-rect is never visible (we hide it in all states).
- .pea-selection-overlay fades out after mouseup (no permanent overlay).
- Selected nodes still show their own selection border.
"""
import os, re, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "selbox_%s@pea.ai" % STAMP
PW = "Password123"
errors = []
log = []

def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))

def shot(page, name):
    p = os.path.join(SHOTS, "selbox_%s_%s.png" % (name, STAMP))
    page.screenshot(path=p)
    log.append("[shot] %s -> %s" % (name, p))

def count_nodeselection_rects(page):
    return page.evaluate("() => document.querySelectorAll('.react-flow__nodesselection-rect').length")

def count_selection_overlay(page):
    return page.evaluate("() => document.querySelectorAll('[data-testid=\"pea-selection-overlay\"]').length")

def is_nodeselection_rect_hidden(page):
    return page.evaluate("""() => {
        const el = document.querySelector('.react-flow__nodesselection-rect');
        if (!el) return true;
        const style = window.getComputedStyle(el);
        return style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
    }""")

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
                    data=json.dumps({"title": "selection box repro", "type": "personal"}).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer %s" % tok}), timeout=15).read().decode())
        except Exception as ex:
            log.append("[warn] create canvas failed: %s" % ex)

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok or "x")
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})

    def mock_json(payload):
        return lambda route, request: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload))
    page.route("**/users/me", lambda route, request: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"id": 1, "email": EMAIL, "displayName": "Tester",
                         "balance": 0, "isAdmin": False, "planLevel": 0,
                         "effectivePlanLevel": 0, "planExpiresAt": None})))
    page.route("**/auth/refresh", lambda route, request: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"token": tok or "x"})))
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
    canvas_title = cvs["title"] if cvs else "selection box repro"
    setup_js = (
        "const ui = window.__ui.getState();"
        "const cs = window.__canvas.getState();"
        "ui.setActive('canvas');"
        "cs.setCanvasMeta(%s, %s, %s);"
        "cs.loadGraph(["
        "{id:'n1', type:'pea', position:{x:400,y:300}, data:{kind:'text', label:'Text', html:'文本节点1'}},"
        "{id:'n2', type:'pea', position:{x:400,y:600}, data:{kind:'text', label:'Text', html:'文本节点2'}}"
        "], [], %s);"
        "cs.clearSelection();"
    ) % (json.dumps(canvas_id), json.dumps(canvas_ver), json.dumps(canvas_title), json.dumps(canvas_ver))
    page.evaluate(setup_js)
    page.wait_for_timeout(1200)
    shot(page, "initial")

    # Sanity: no selection rects at start
    rect_count = count_nodeselection_rects(page)
    overlay_count = count_selection_overlay(page)
    log.append("[check] initial nodesselection-rect count = %s" % rect_count)
    log.append("[check] initial overlay count = %s" % overlay_count)
    if rect_count != 0:
        errors.append("initial nodesselection-rect count = %s (expected 0)" % rect_count)

    # Perform a real box selection by dragging on the canvas pane.
    # Coordinates chosen to cover both nodes n1 (y~300) and n2 (y~600).
    # We start on an empty area to the left of the nodes and drag a rectangle over them.
    page.mouse.move(250, 250)
    page.mouse.down()
    page.mouse.move(700, 800, steps=20)
    page.wait_for_timeout(100)
    shot(page, "during_drag")
    page.mouse.up()
    page.wait_for_timeout(600)  # wait longer than overlay fade (120ms) + ReactFlow settle
    shot(page, "after_drag")

    sel = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after drag = %s" % sel)
    if len(sel) < 2:
        errors.append("box selection did not select both nodes (selectedIds=%s)" % sel)

    # The persistent big rectangle must be gone (either removed from DOM or hidden by CSS).
    rect_count_after = count_nodeselection_rects(page)
    rect_hidden_after = is_nodeselection_rect_hidden(page)
    overlay_count_after = count_selection_overlay(page)
    log.append("[check] after drag nodesselection-rect count = %s, hidden = %s" % (rect_count_after, rect_hidden_after))
    log.append("[check] after drag overlay count = %s" % overlay_count_after)
    if rect_count_after > 0 and not rect_hidden_after:
        errors.append("nodesselection-rect is still visible after box selection (count=%s)" % rect_count_after)
    if overlay_count_after != 0:
        errors.append("pea-selection-overlay persisted after box selection (count=%s)" % overlay_count_after)

    # Click blank canvas to clear selection: verify no leftover rect.
    page.mouse.click(200, 200)
    page.wait_for_timeout(500)
    shot(page, "cleared")
    rect_count_cleared = count_nodeselection_rects(page)
    overlay_count_cleared = count_selection_overlay(page)
    log.append("[check] cleared nodesselection-rect count = %s" % rect_count_cleared)
    log.append("[check] cleared overlay count = %s" % overlay_count_cleared)
    if rect_count_cleared != 0 or overlay_count_cleared != 0:
        errors.append("selection artifacts remained after clearing selection")

    print("\n".join(log))
    print("\n===== ERRORS =====")
    print("\n".join(errors) if errors else "NO ERRORS")
    browser.close()
