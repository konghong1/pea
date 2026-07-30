"""Reproduce group error by directly manipulating store."""
import os, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5176"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"grpd_{STAMP}@pea.ai"
PW = "Password123"
errors = []
log = []

def shot(page, name):
    p = os.path.join(SHOTS, f"grpd_{name}_{STAMP}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")

def api(method, path, token=None, body=None):
    req = urllib.request.Request(API + path, method=method,
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
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    cvs = api("POST", "/canvases", token=tok, body={"title": "group repro direct", "type": "personal"})

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.evaluate(f"""
        localStorage.setItem('pea_token', {json.dumps(tok)});
        localStorage.setItem('pea_user', JSON.stringify({{id:1, email:{json.dumps(EMAIL)}}}));
    """)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    page.evaluate(f"""
        const ui = window.__ui.getState();
        const cs = window.__canvas.getState();
        ui.setActive('canvas');
        cs.setCanvasMeta({cvs['id']}, {cvs['version']}, {json.dumps(cvs['title'])});
        cs.loadGraph([
            {{id:'n1', type:'pea', position:{{x:300,y:300}}, data:{{kind:'text', label:'Text', html:'文本节点'}}}},
            {{id:'n2', type:'pea', position:{{x:700,y:300}}, data:{{kind:'image', label:'Image', resultUrl:'https://placehold.co/300x400/png?text=Image'}}}}
        ], [], {cvs['version']});
        cs.setSelection(['n1','n2']);
    """)
    page.wait_for_timeout(1000)
    sel = page.evaluate("() => window.__canvas.getState().selectedIds")
    log.append(f"[state] selectedIds = {sel}")
    shot(page, "before_group")

    # click group button (title '打包')
    group_btn = page.locator('.multiselect-toolbar').locator('button[title="打组"]')
    log.append(f"[dom] group button count = {group_btn.count()}")
    if group_btn.count():
        group_btn.click()
        page.wait_for_timeout(1000)
        shot(page, "after_group")
        nodes = page.evaluate("""() => window.__canvas.getState().nodes.map(n => ({id:n.id, type:n.type, parentNode:n.parentNode, extent:n.extent, selected:n.selected}))""")
        log.append(f"[state] nodes after group: {json.dumps(nodes, ensure_ascii=False)}")
        sel2 = page.evaluate("() => window.__canvas.getState().selectedIds")
        log.append(f"[state] selectedIds after group = {sel2}")

    page.mouse.click(200, 700)
    page.wait_for_timeout(500)
    shot(page, "click_outside")

    print("\n".join(log))
    print("ERRORS:", errors)
    browser.close()
