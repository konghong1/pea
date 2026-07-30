import os, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
API  = "http://localhost:4100"
EMAIL = "probe_%s@pea.ai" % int(time.time())
PW = "Password123"

def apipost(method, path, token=None, body=None):
    req = urllib.request.Request(API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer %s" % token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    ctx = browser.new_context(viewport={"width":1440,"height":900})
    page = ctx.new_page()
    logs = []
    page.on("console", lambda m: logs.append("%s: %s" % (m.type, m.text)))
    page.on("pageerror", lambda e: logs.append("PAGEERROR: %s\n%s" % (e, getattr(e,"stack","") or "")))

    st,_ = apipost("POST","/auth/register", body={"email":EMAIL,"password":PW})
    tok = json.loads(urllib.request.urlopen(urllib.request.Request(API+"/auth/login", method="POST",
        data=json.dumps({"email":EMAIL,"password":PW}).encode(), headers={"Content-Type":"application/json"}), timeout=15).read().decode())["token"]

    # Step 1: login page
    page.goto(BASE+"/login", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    s1 = page.evaluate("() => ({rootKids: document.getElementById('root')?.childElementCount, bodyLen: document.body.innerText.length})")
    print("LOGIN PAGE:", json.dumps(s1))

    # Step 2: set auth + route, go to canvas
    page.evaluate("localStorage.setItem('pea_token', %s);" % json.dumps(tok))
    page.evaluate("localStorage.setItem('pea_user', %s);" % json.dumps({"id":1,"email":EMAIL}))
    page.evaluate("localStorage.setItem('pea_ui_route', %s);" % json.dumps({"active":"canvas","canvasId":None}))
    page.goto(BASE+"/", wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    s2 = page.evaluate("""() => ({
        hasCanvas: typeof window.__canvas !== 'undefined',
        reactFlow: !!document.querySelector('.react-flow'),
        rootKids: document.getElementById('root')?.childElementCount,
        bodyLen: document.body.innerText.length,
        snippet: document.body.innerText.slice(0,300)
    })""")
    print("CANVAS PAGE:", json.dumps(s2, ensure_ascii=False))

    print("\n--- LOGS ---")
    for l in logs[:30]:
        print(l)
    browser.close()
