import os, re, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "style_%s@pea.ai" % STAMP
PW = "Password123"

def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))

def mock_json(payload):
    return lambda route, request: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(payload))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    try:
        urllib.request.urlopen(urllib.request.Request(BASE + "/auth/register", method="POST",
            data=json.dumps({"email": EMAIL, "password": PW}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15)
    except Exception:
        pass
    tok = json.loads(urllib.request.urlopen(
        urllib.request.Request(BASE + "/auth/login", method="POST",
            data=json.dumps({"email": EMAIL, "password": PW}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read().decode())["token"]
    cvs = json.loads(urllib.request.urlopen(
        urllib.request.Request(BASE + "/canvases", method="POST",
            data=json.dumps({"title": "style check", "type": "personal"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % tok}), timeout=15).read().decode())

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok)
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})
    page.route("**/users/me", lambda route, request: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"id": 1, "email": EMAIL, "displayName": "Tester",
                         "balance": 0, "isAdmin": False, "planLevel": 0,
                         "effectivePlanLevel": 0, "planExpiresAt": None})))
    page.route("**/auth/refresh", lambda route, request: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"token": tok})))
    page.route(re.compile(r"http://[^/]+/canvases.*"), mock_json({"ok": True, "data": []}))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
    page.wait_for_timeout(800)

    setup = (
        "const ui = window.__ui.getState(); const cs = window.__canvas.getState();"
        "ui.setActive('canvas'); cs.setCanvasMeta(%s, %s, 'style');"
        "cs.loadGraph(["
        "{id:'n1', type:'pea', position:{x:400,y:300}, data:{kind:'text', label:'Text', html:'A'}},"
        "{id:'n2', type:'pea', position:{x:400,y:600}, data:{kind:'text', label:'Text', html:'B'}}"
        "], [], %s); cs.setSelection(['n1','n2']);"
    ) % (cvs["id"], cvs["version"], cvs["version"])
    page.evaluate(setup)
    page.wait_for_timeout(1200)

    result = page.evaluate("""() => {
        const el = document.querySelector('.react-flow__nodesselection-rect');
        if (!el) return {found: false};
        const style = window.getComputedStyle(el);
        return {
            found: true,
            display: style.display,
            visibility: style.visibility,
            opacity: style.opacity,
            rect: el.getBoundingClientRect(),
            classes: el.className,
            parentClasses: el.parentElement ? el.parentElement.className : null
        };
    }""")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
