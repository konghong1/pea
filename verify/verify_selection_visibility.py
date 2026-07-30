"""Verify that the selection box is translucent and nodes remain visible inside."""
import os, re, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "selvis_%s@pea.ai" % STAMP
PW = "Password123"
errors = []
log = []

def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))

def shot(page, name):
    p = os.path.join(SHOTS, "selvis_%s_%s.png" % (name, STAMP))
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
                    data=json.dumps({"title": "selection visibility", "type": "personal"}).encode(),
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

    canvas_id = cvs["id"] if cvs else 1
    canvas_ver = cvs["version"] if cvs else 1
    canvas_title = cvs["title"] if cvs else "selection visibility"
    setup_js = (
        "const ui = window.__ui.getState();"
        "const cs = window.__canvas.getState();"
        "ui.setActive('canvas');"
        "cs.setCanvasMeta(%s, %s, %s);"
        "cs.loadGraph(["
        "{id:'n1', type:'pea', position:{x:320,y:300}, width:340, height:340, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 1</div>'}},"
        "{id:'n2', type:'pea', position:{x:680,y:300}, width:340, height:340, data:{kind:'text', label:'Text', html:'<div style=\\'padding:12px;color:#fff\\'>文本节点 2</div>'}}"
        "], [], %s);"
    ) % (json.dumps(canvas_id), json.dumps(canvas_ver), json.dumps(canvas_title), json.dumps(canvas_ver))
    page.evaluate(setup_js)
    page.wait_for_timeout(1200)

    # Ensure nodes rendered before drag-select
    page.wait_for_selector(".react-flow__node[data-id='n1']", timeout=10000)
    page.wait_for_selector(".react-flow__node[data-id='n2']", timeout=10000)
    shot(page, "before_select")

    def inspect():
        return page.evaluate("""() => {
            const el = document.querySelector('.react-flow__selection') || document.querySelector('.react-flow__nodesselection-rect');
            const nodes = Array.from(document.querySelectorAll('.react-flow__node')).map(n => {
                const cs = window.getComputedStyle(n);
                return {id: n.getAttribute('data-id'), opacity: cs.opacity, display: cs.display, visibility: cs.visibility, zIndex: cs.zIndex, rect: n.getBoundingClientRect().width+'x'+n.getBoundingClientRect().height};
            });
            const nodesContainer = document.querySelector('.react-flow__nodes');
            const nsContainer = document.querySelector('.react-flow__nodesselection');
            const containerInfo = {
                nodes: nodesContainer ? {className: nodesContainer.className, zIndex: window.getComputedStyle(nodesContainer).zIndex, pos: window.getComputedStyle(nodesContainer).position} : null,
                nodesselection: nsContainer ? {className: nsContainer.className, zIndex: window.getComputedStyle(nsContainer).zIndex, pos: window.getComputedStyle(nsContainer).position} : null
            };
            if (!el) return {found: false, nodes: nodes, containers: containerInfo};
            const cs = window.getComputedStyle(el);
            return {
                found: true,
                classes: el.className,
                background: cs.backgroundColor,
                border: cs.border,
                opacity: cs.opacity,
                zIndex: cs.zIndex,
                position: cs.position,
                width: el.getBoundingClientRect().width,
                height: el.getBoundingClientRect().height,
                parent: el.parentElement ? el.parentElement.className : null,
                parentPos: el.parentElement ? window.getComputedStyle(el.parentElement).position : null,
                parentZ: el.parentElement ? window.getComputedStyle(el.parentElement).zIndex : null,
                index: el.parentElement ? Array.from(el.parentElement.children).indexOf(el) : -1,
                nodes: nodes,
                containers: containerInfo,
                viewportChildren: Array.from(document.querySelector('.react-flow__viewport')?.children || []).map(c => ({
                    className: c.className,
                    zIndex: window.getComputedStyle(c).zIndex,
                    position: window.getComputedStyle(c).position
                })),
                rendererChildren: Array.from(document.querySelector('.react-flow__renderer')?.children || []).map(c => ({
                    className: c.className,
                    zIndex: window.getComputedStyle(c).zIndex,
                    position: window.getComputedStyle(c).position
                })),
                rectParentChain: (() => {
                    const el = document.querySelector('.react-flow__nodesselection-rect');
                    const chain = [];
                    let p = el;
                    while (p) {
                        chain.push({tag: p.tagName, class: p.className, zIndex: window.getComputedStyle(p).zIndex, pos: window.getComputedStyle(p).position});
                        p = p.parentElement;
                        if (chain.length > 8) break;
                    }
                    return chain;
                })(),
                viewportInfo: (() => {
                    const v = document.querySelector('.react-flow__viewport');
                    if (!v) return null;
                    const p = v.parentElement;
                    return {
                        className: v.className,
                        zIndex: window.getComputedStyle(v).zIndex,
                        pos: window.getComputedStyle(v).position,
                        parentClass: p ? p.className : null,
                        parentZ: p ? window.getComputedStyle(p).zIndex : null,
                        parentPos: p ? window.getComputedStyle(p).position : null
                    };
                })(),
                nodeRects: Array.from(document.querySelectorAll('.react-flow__node')).map(n => {
                    const r = n.getBoundingClientRect();
                    const body = n.querySelector('.pea-node-body-card');
                    const bodyCs = body ? window.getComputedStyle(body) : null;
                    return {
                        id: n.getAttribute('data-id'), x: r.x, y: r.y, w: r.width, h: r.height,
                        className: n.className,
                        bodyClass: body ? body.className : null,
                        bodyBg: bodyCs ? bodyCs.backgroundColor : null,
                        bodyOpacity: bodyCs ? bodyCs.opacity : null,
                        bodyDisplay: bodyCs ? bodyCs.display : null,
                        htmlSnippet: n.innerHTML.slice(0, 300)
                    };
                })
            };
        }""")

    # Drag-select from blank area covering both nodes
    # Coordinates are screen-space; ReactFlow panOnDrag=false so left-drag = selection box
    page.mouse.move(260, 250)
    page.mouse.down()
    page.mouse.move(940, 500, steps=30)
    page.wait_for_timeout(500)
    log.append("[style] during drag: %s" % json.dumps(inspect(), ensure_ascii=False))
    shot(page, "during_drag_select")
    page.mouse.up()
    page.wait_for_timeout(600)

    sel = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append("[state] selectedIds after drag-select: %s" % sel)
    log.append("[style] after drag: %s" % json.dumps(inspect(), ensure_ascii=False))

    # Check which element is on top at center of each node
    top_js = """() => {
        const n1 = document.querySelector('.react-flow__node[data-id="n1"]');
        const n2 = document.querySelector('.react-flow__node[data-id="n2"]');
        const rect = document.querySelector('.react-flow__nodesselection-rect');
        function top(el) {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const x = r.left + r.width/2, y = r.top + r.height/2;
            const hit = document.elementFromPoint(x, y);
            if (!hit) return null;
            return {
                tag: hit.tagName,
                class: hit.className,
                dataId: hit.getAttribute('data-id'),
                outer: hit.outerHTML.slice(0, 200)
            };
        }
        return {n1: top(n1), n2: top(n2), rect: top(rect)};
    }"""
    log.append("[hit] top element: %s" % json.dumps(page.evaluate(top_js), ensure_ascii=False))

    shot(page, "after_drag_select")

    print("\n".join(log))
    if errors:
        print("--- ERRORS ---")
        print("\n".join(errors))
    print("DONE")
