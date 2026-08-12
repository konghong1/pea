import urllib.request, json, time, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "verify_%s@pea.ai" % STAMP
PW = "Password123"

def post(path, data, headers=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=25).read().decode())

try:
    post("/api/auth/register", {"email": EMAIL, "password": PW})
except Exception as e:
    print("register skip:", e)
login = post("/api/auth/login", {"email": EMAIL, "password": PW})
tok = login["token"]
cvs = post("/api/canvases", {"title": "verify canvas", "type": "personal"},
           {"Authorization": "Bearer " + tok})
cid = cvs.get("id") or cvs.get("canvasId")
print("token ok, canvasId=", cid)

# 这些键的应用端是直接 localStorage.getItem(...) 读原始字符串，不做 JSON.parse。
# 其他键（pea_user 等）应用端做 JSON.parse，必须 JSON.stringify 写入。
_RAW_KEYS = {"pea_token", "pea_theme", "pea_creator_design", "pea_active_canvas_id", "pea_canvas_id"}

def ls(page, k, v):
    if k in _RAW_KEYS:
        page.evaluate("localStorage.setItem(%s, %s);" % (json.dumps(k), json.dumps(v)))
    else:
        page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(k), json.dumps(v)))

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls(page, "pea_token", tok)
    ls(page, "pea_user", {"id": 1, "email": EMAIL})
    ls(page, "pea_theme", "dark")
    ls(page, "pea_creator_design", "runway")
    ls(page, "pea_ui_route", {"active": "canvas", "canvasId": cid})
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_timeout(3000)

    try:
        page.evaluate("""() => {
          const s = window.__canvas && window.__canvas.getState();
          if (!s || !s.addNode) return 'no-addNode';
          const mk = (kind,label,x,y)=>s.addNode({kind,label,title:label}, {x,y});
          mk('text','故事脚本',-260,-120);
          mk('image','角色设定',120,-120);
          mk('generate','AI 生成',120,160);
          return 'ok';
        }""")
    except Exception as e:
        print("inject err:", e)
    page.wait_for_timeout(1500)
    page.screenshot(path="D:/workspace/pea/verify/shot_runway.png")
    print("saved runway")

    try:
        page.click(".pea-canvas-header-trigger", timeout=4000)
        page.wait_for_timeout(600)
        page.screenshot(path="D:/workspace/pea/verify/shot_runway_menu.png")
        print("saved runway menu")
        page.keyboard.press("Escape")
    except Exception as e:
        print("menu err:", e)

    ls(page, "pea_creator_design", "figma")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.screenshot(path="D:/workspace/pea/verify/shot_figma.png")
    print("saved figma")

    ls(page, "pea_ui_route", {"active": "admin", "canvasId": None})
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path="D:/workspace/pea/verify/shot_admin.png")
    print("saved admin")

    ls(page, "pea_theme", "light")
    ls(page, "pea_ui_route", {"active": "workspace", "canvasId": None})
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path="D:/workspace/pea/verify/shot_precision_light.png")
    print("saved precision-light")

    b.close()
print("DONE")
