import os, json, re, time, urllib.request
from playwright.sync_api import sync_playwright
BASE = "http://localhost:5180"
EMAIL = "probe3_%s@pea.ai" % time.strftime("%H%M%S")
try:
    urllib.request.urlopen(urllib.request.Request(BASE+"/auth/register", method="POST",
        data=json.dumps({"email":EMAIL,"password":"P12345678"}).encode(),
        headers={"Content-Type":"application/json"}), timeout=10)
except Exception:
    pass
tok = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+"/auth/login", method="POST",
    data=json.dumps({"email":EMAIL,"password":"P12345678"}).encode(),
    headers={"Content-Type":"application/json"}), timeout=10).read().decode())["token"]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = b.new_context(viewport={"width":1440,"height":900}).new_page()
    page.goto(BASE+"/login", wait_until="domcontentloaded")
    page.evaluate("localStorage.setItem('pea_token', JSON.stringify(%s))" % json.dumps(tok))
    page.evaluate("localStorage.setItem('pea_user', JSON.stringify({id:1,email:%s}))" % json.dumps(EMAIL))
    page.evaluate("localStorage.setItem('pea_ui_route', JSON.stringify({active:'canvas',canvasId:null}))")
    def mj(payload):
        return lambda route, request: route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
    page.route("**/users/me", mj({"id":1,"email":EMAIL,"displayName":"T","balance":0,"isAdmin":False,"planLevel":0,"effectivePlanLevel":0,"planExpiresAt":None}))
    page.route("**/auth/refresh", mj({"token":tok}))
    page.route(re.compile(r"http://[^/]+/canvases.*"), mj({"ok":True,"data":[]}))
    page.route(re.compile(r"http://[^/]+/models/.*"), mj([]))
    page.route(re.compile(r"http://[^/]+/files/.*"), mj({"ok":True}))
    page.goto(BASE+"/", wait_until="domcontentloaded")
    page.wait_for_function("() => window.__canvas && window.__peaSetZoom", timeout=15000)
    page.evaluate("""() => {
      window.__canvas.getState().loadGraph([
        { id: 'n1', type: 'pea', position: { x: 80, y: 160 }, data: { kind: 'image', aspectRatio: '1:1', label: 'A' } },
        { id: 'n2', type: 'pea', position: { x: 460, y: 160 }, data: { kind: 'text', aspectRatio: '1:1', label: 'B' } },
        { id: 'n3', type: 'pea', position: { x: 820, y: 160 }, data: { kind: 'image', aspectRatio: '1:1', label: 'C', resultUrl: 'https://placehold.co/300x300/png' } },
      ], [], 1);
      window.__canvas.getState().select('n2');
    }""")
    page.wait_for_timeout(800)
    print("DOM:", page.evaluate("""() => Array.from(document.querySelectorAll('.react-flow__node')).map(n => ({
      id: n.getAttribute('data-id'), html: n.innerHTML.substring(0,250)
    }))"""))
    for nid in ('n1','n2','n3'):
        print(nid, page.evaluate("(id) => { const n=document.querySelector('.react-flow__node[data-id=\"'+id+'\"]'); if(!n)return 'no'; return { chrome: !!n.querySelector('.pea-node-chrome'), badge: !!n.querySelector('.pea-node-badge'), card: !!n.querySelector('.pea-node-body-card'), fixed: !!n.querySelector('.pea-node-chrome-fixed') }; }", nid))
    b.close()