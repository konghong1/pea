"""Verify the persistent selection bounds box around selected nodes.

Checks:
- A .pea-selection-bounds element appears when one or more nodes are selected.
- The bounds box tightly wraps the selected nodes using their DOM bounding boxes.
- Nodes merely covered by the drag selection box but not actually selected are
  not included in the persistent bounds box.
- The bounds box follows the selection: clearing selection removes it;
  selecting a different set updates it.
"""
import os
import re
import json
import time
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "selbounds_%s@pea.ai" % STAMP
PW = "Password123"
errors = []
log = []


def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))


def shot(page, name):
    p = os.path.join(SHOTS, "selbounds_%s_%s.png" % (name, STAMP))
    page.screenshot(path=p)
    log.append("[shot] %s -> %s" % (name, p))


def apipost(method, path, token=None, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer %s" % token} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def get_bounds_rect(page):
    return page.evaluate("""() => {
        const el = document.querySelector('[data-testid="pea-selection-bounds"]');
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                 width: r.width, height: r.height, opacity: window.getComputedStyle(el).opacity };
    }""")


def get_node_rect(page, node_id):
    return page.evaluate("""(id) => {
        const el = document.querySelector('.react-flow__node[data-id="' + id + '"]');
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                 width: r.width, height: r.height };
    }""", node_id)


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
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
        tok = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    BASE + "/auth/login",
                    method="POST",
                    data=json.dumps({"email": EMAIL, "password": PW}).encode(),
                    headers={"Content-Type": "application/json"},
                ),
                timeout=15,
            ).read().decode()
        )["token"]
    except Exception as ex:
        log.append("[warn] login failed: %s" % ex)

    cvs = None
    if tok:
        try:
            cvs = json.loads(
                urllib.request.urlopen(
                    urllib.request.Request(
                        BASE + "/canvases",
                        method="POST",
                        data=json.dumps({"title": "selection bounds box", "type": "personal"}).encode(),
                        headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % tok},
                    ),
                    timeout=15,
                ).read().decode()
            )
        except Exception as ex:
            log.append("[warn] create canvas failed: %s" % ex)

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok or "x")
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})

    def mock_json(payload):
        return lambda route, request: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload)
        )

    page.route(
        "**/users/me",
        mock_json(
            {
                "id": 1,
                "email": EMAIL,
                "displayName": "Tester",
                "balance": 0,
                "isAdmin": False,
                "planLevel": 0,
                "effectivePlanLevel": 0,
                "planExpiresAt": None,
            }
        ),
    )
    page.route("**/auth/refresh", mock_json({"token": tok or "x"}))
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
    canvas_title = cvs["title"] if cvs else "selection bounds box"
    # Three nodes: n1/n2 close together, n3 far away. Drag-select should only get n1/n2.
    setup_js = (
        "const ui = window.__ui.getState();"
        "const cs = window.__canvas.getState();"
        "ui.setActive('canvas');"
        "cs.setCanvasMeta(%s, %s, %s);"
        "cs.loadGraph(["
        "{id:'n1', type:'pea', position:{x:320,y:300}, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 1</div>'}},"
        "{id:'n2', type:'pea', position:{x:720,y:300}, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 2</div>'}},"
        "{id:'n3', type:'pea', position:{x:320,y:900}, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 3</div>'}}"
        "], [], %s);"
        "cs.clearSelection();"
    ) % (
        json.dumps(canvas_id),
        json.dumps(canvas_ver),
        json.dumps(canvas_title),
        json.dumps(canvas_ver),
    )
    page.evaluate(setup_js)
    page.wait_for_timeout(1200)
    shot(page, "initial")

    # Sanity: no bounds box at start
    bounds_before = get_bounds_rect(page)
    log.append("[check] initial bounds box = %s" % bounds_before)
    if bounds_before is not None:
        errors.append("bounds box should not appear before selection")

    # ---- Test 1: single click select n1 ----
    n1_rect = get_node_rect(page, "n1")
    if n1_rect:
        page.mouse.click((n1_rect["left"] + n1_rect["right"]) / 2,
                         (n1_rect["top"] + n1_rect["bottom"]) / 2)
    page.wait_for_timeout(400)
    shot(page, "single_select_n1")
    sel_after_single = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after single click = %s" % sel_after_single)
    bounds_single = get_bounds_rect(page)
    log.append("[check] bounds box after single click = %s" % bounds_single)
    if bounds_single is None:
        errors.append("bounds box did not appear after single-selecting a node")
    elif n1_rect:
        # Allow 2px tolerance for sub-pixel / border width
        tol = 2
        if (abs(bounds_single["left"] - n1_rect["left"]) > tol or
            abs(bounds_single["top"] - n1_rect["top"]) > tol or
            abs(bounds_single["right"] - n1_rect["right"]) > tol or
            abs(bounds_single["bottom"] - n1_rect["bottom"]) > tol):
            errors.append("bounds box does not tightly wrap single selected node: bounds=%s node=%s" %
                          (bounds_single, n1_rect))

    # ---- Test 2: box select n1 and n2, n3 should NOT be selected ----
    page.mouse.click(200, 200)  # clear
    page.wait_for_timeout(300)
    page.mouse.move(260, 250)
    page.mouse.down()
    page.mouse.move(940, 500, steps=30)
    page.wait_for_timeout(300)
    shot(page, "during_box_select")
    page.mouse.up()
    page.wait_for_timeout(600)
    shot(page, "after_box_select")

    sel_after_box = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after box select = %s" % sel_after_box)
    if set(sel_after_box) != {"n1", "n2"}:
        errors.append("box select did not select exactly n1,n2 (got %s)" % sel_after_box)

    bounds_after_box = get_bounds_rect(page)
    n1 = get_node_rect(page, "n1")
    n2 = get_node_rect(page, "n2")
    n3 = get_node_rect(page, "n3")
    log.append("[check] bounds box after box select = %s" % bounds_after_box)
    log.append("[rects] n1=%s n2=%s n3=%s" % (n1, n2, n3))

    if bounds_after_box is None:
        errors.append("bounds box did not appear after box selection")
    elif n1 and n2:
        expected_left = min(n1["left"], n2["left"])
        expected_top = min(n1["top"], n2["top"])
        expected_right = max(n1["right"], n2["right"])
        expected_bottom = max(n1["bottom"], n2["bottom"])
        tol = 2
        if (abs(bounds_after_box["left"] - expected_left) > tol or
            abs(bounds_after_box["top"] - expected_top) > tol or
            abs(bounds_after_box["right"] - expected_right) > tol or
            abs(bounds_after_box["bottom"] - expected_bottom) > tol):
            errors.append(
                "bounds box does not tightly wrap n1+n2: bounds=%s expected=[%s,%s,%s,%s]" %
                (bounds_after_box, expected_left, expected_top, expected_right, expected_bottom)
            )
        # n3 must be outside the bounds box
        if n3 and not (
            n3["right"] < bounds_after_box["left"] or
            n3["left"] > bounds_after_box["right"] or
            n3["bottom"] < bounds_after_box["top"] or
            n3["top"] > bounds_after_box["bottom"]
        ):
            errors.append("bounds box incorrectly includes unselected n3")

    # ---- Test 3: clear selection removes bounds box ----
    page.mouse.click(200, 200)
    page.wait_for_timeout(500)
    shot(page, "cleared")
    bounds_cleared = get_bounds_rect(page)
    log.append("[check] bounds box after clear = %s" % bounds_cleared)
    if bounds_cleared is not None:
        errors.append("bounds box remained after clearing selection")

    print("\n".join(log))
    print("\n===== ERRORS =====")
    print("\n".join(errors) if errors else "NO ERRORS")
    browser.close()
