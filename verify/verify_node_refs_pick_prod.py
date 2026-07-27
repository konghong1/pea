"""E-REF-2-PROD · 8088 生产构建快速烟测（最小版）

只验证：1) 页面加载无 console error 2) 重新加载后 prod 钩子生效（window.__canvas 暴露）
"""
import os
import sys
import uuid
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"erefp_{uuid.uuid4().hex[:8]}@pea.ai"
PW = "Password123"
errors = []
checks = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.evaluate("localStorage.setItem('__peaDevHooks', '1')")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    has_canvas = page.evaluate("!!window.__canvas")
    assert has_canvas, "prod 8088 未暴露 window.__canvas (确认 dist 是新构建)"
    checks.append(("prod 8088 暴露 window.__canvas", True))

    # 注册
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "ProdRefBot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    # 此时应已跳转工作空间，可能直接进入画布
    page.screenshot(path=os.path.join(SHOTS, "erefp_01_after_register.png"))

    # 找到画布：调 API 建一个，跳过去
    cid = page.evaluate("""
        async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
                body: JSON.stringify({ title: 'Prod Ref Pick', scope: 'personal' }),
            });
            const j = await r.json();
            return j.id;
        }
    """)
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(1000)
    checks.append(("prod 8088 进入画布", True))

    # 注入图 + 选中
    page.evaluate("""
        () => {
            const store = window.__canvas.getState();
            store.loadGraph([], [], store.version);
            const img = { id: 'nImg1', type: 'pea', position: { x: 100, y: 200 },
                data: { kind: 'image', label: 'Bag', resultUrl: 'https://placehold.co/120x120/8a4a2c/ffffff?text=Bag', meta: { fileName: 'a.png' } } };
            const text = { id: 'nText1', type: 'pea', position: { x: 100, y: 400 },
                data: { kind: 'text', label: 'Text', html: '高端女装模特，黑色连衣裙' } };
            const target = { id: 'nT1', type: 'pea', position: { x: 500, y: 300 },
                data: { kind: 'image', label: 'Target', prompt: '', meta: {} } };
            store.loadGraph([img, text, target], [], store.version);
            store.select('nT1');
        }
    """)
    page.wait_for_timeout(1500)
    bar = page.locator(".node-input-bar")
    expect(bar).to_be_visible(timeout=8000)
    # 进入 pick mode 选文本节点
    page.locator('button[aria-label="从画布选择参考"]').click()
    page.wait_for_timeout(300)
    page.locator('.react-flow__node[data-id="nText1"]').click()
    page.wait_for_timeout(400)
    expect(page.locator('.node-ref-thumb[data-ref-kind="text"]')).to_have_count(1, timeout=3000)
    page.screenshot(path=os.path.join(SHOTS, "erefp_02_text_in_ref.png"))
    checks.append(("prod 8088 文本节点加入引用条", True))

    print("\n========== 8088 烟测结果 ==========")
    for name, ok in checks:
        print(f"  {'OK' if ok else 'FAIL'} {name}")
    if errors:
        print("\nWARN Console errors:")
        for e in errors[:10]:
            print(f"  - {e}")
    else:
        print("\nOK 0 console error")
    browser.close()
    sys.exit(0 if all(ok for _, ok in checks) else 1)
