"""复现：从项目列表点项目卡片能否进入画布。带实时日志。"""
import os
import sys
import uuid
import time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("REPRO_BASE", "http://localhost:5174")
LOG = os.path.join(os.path.dirname(__file__), "repro.log")
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"rep_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []

logf = open(LOG, "w", encoding="utf-8")


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    logf.write(msg + "\n")
    logf.flush()


def shot(page, name):
    p = os.path.join(SHOTS, f"rep_{name}.png")
    page.screenshot(path=p)
    log("[shot]", name, "->", p)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.set_default_timeout(8000)
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    log("== step1 register ==")
    t0 = time.time()
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    try:
        page.get_by_role("button", name="没有账号？去注册").first.click(timeout=5000)
    except Exception as e:
        log("register-link click failed:", e)
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "ReproBot")
    try:
        page.locator("form button[type=submit]").click(timeout=5000)
        log("clicked submit")
    except Exception as e:
        log("submit button failed:", e)
    page.wait_for_timeout(1500)
    log("after register active =", page.evaluate("() => window.__ui ? window.__ui.getState().active : 'no __ui'"))
    log("step1 took", round(time.time() - t0, 1), "s")

    log("== step2 create canvas via API ==")
    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', ...(token?{Authorization:`Bearer ${token}`}:{})},
            body: JSON.stringify({title:'Repro Canvas', scope:'personal'})
        });
        const j = await r.json();
        return j.id;
    }""")
    log("created canvas id:", cid)

    log("== step3 back to workspace (reload to refresh list) ==")
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1500)
    shot(page, "01_list")
    cards = page.query_selector_all(".projects-card[data-canvas-id]")
    log("project cards count:", len(cards))

    log("== step4 click first card ==")
    if cards:
        card = cards[0]
        cid_attr = card.get_attribute("data-canvas-id")
        log("clicking card data-canvas-id:", cid_attr)
        card.click()
    else:
        log("NO CARD FOUND")
    page.wait_for_timeout(3500)
    shot(page, "02_after_click")

    log("== step5 check canvas ==")
    rf = page.query_selector(".react-flow")
    log("react-flow present:", rf is not None)
    log("active after click:", page.evaluate("() => window.__ui ? window.__ui.getState().active : 'no __ui'"))
    log("canvasId:", page.evaluate("() => window.__canvas ? window.__canvas.getState().canvasId : 'no __canvas'"))

    log("=== CONSOLE ERRORS ===")
    for e in errors:
        log(e)
    log(f"total errors: {len(errors)}")
    browser.close()
    log("DONE")
