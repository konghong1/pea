"""Reproduce multi-select / group issues on dev server."""
import os, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5176"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"grp_{STAMP}@pea.ai"
PW = "Password123"
errors = []
log = []

def shot(page, name):
    p = os.path.join(SHOTS, f"grp_{name}_{STAMP}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")

def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def apipost(method, path, token=None, body=None):
    req = urllib.request.Request(API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
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
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    st, _ = apipost("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    log.append(f"[auth] register -> {st}")
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    log.append(f"[auth] login OK")
    st, body = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase -> {st}")
    cvs = api("POST", "/canvases", token=tok, body={"title": "group repro", "type": "personal"})
    log.append(f"[canvas] created {cvs['id']}")

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.evaluate(f"""
        localStorage.setItem('pea_token', {json.dumps(tok)});
        localStorage.setItem('pea_user', JSON.stringify({{id:1, email:{json.dumps(EMAIL)}}}));
    """)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    # enter canvas
    page.evaluate(f"""
        const ui = window.__ui.getState();
        const cs = window.__canvas.getState();
        ui.setActive('canvas');
        cs.setCanvasMeta({cvs['id']}, {cvs['version']}, {json.dumps(cvs['title'])});
        cs.loadGraph([
            {{id:'n1', type:'pea', position:{{x:300,y:300}}, data:{{kind:'text', label:'Text', html:'这是一个关于…的文本节点'}}}},
            {{id:'n2', type:'pea', position:{{x:700,y:280}}, data:{{kind:'image', label:'Image', resultUrl:'https://placehold.co/300x400/png?text=Image'}}}}
        ], [], {cvs['version']});
    """)
    page.wait_for_timeout(1000)
    shot(page, "loaded")

    # select both via shift click
    node1 = page.locator('.react-flow__node[data-id="n1"]')
    node2 = page.locator('.react-flow__node[data-id="n2"]')
    box1 = node1.bounding_box()
    box2 = node2.bounding_box()
    log.append(f"node1 box {box1}")
    log.append(f"node2 box {box2}")
    page.mouse.click(box1['x'] + box1['width']/2, box1['y'] + box1['height']/2)
    page.wait_for_timeout(300)
    sel1 = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append(f"[state] selectedIds after first click: {sel1}")
    page.keyboard.down('Shift')
    page.mouse.click(box2['x'] + box2['width']/2, box2['y'] + box2['height']/2)
    page.keyboard.up('Shift')
    page.wait_for_timeout(800)
    sel = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append(f"[state] selectedIds after shift-click: {sel}")
    flags = page.evaluate("""() => window.__canvas.getState().nodes.map(n => ({id:n.id, selected:n.selected}))""")
    log.append(f"[state] node flags: {flags}")
    toolbar = page.locator('.multiselect-toolbar')
    log.append(f"[dom] multiselect-toolbar count: {toolbar.count()}")
    shot(page, "multiselect")

    # click group button
    group_btn = page.locator('.multiselect-toolbar').locator('button[title="打组"]')
    if group_btn.count():
        group_btn.click()
        page.wait_for_timeout(800)
        shot(page, "after_group")
    else:
        log.append("group button not found")

    # click outside (pane)
    page.mouse.click(200, 700)
    page.wait_for_timeout(500)
    shot(page, "click_outside")

    print("\n".join(log))
    print("ERRORS:", errors)
    browser.close()
