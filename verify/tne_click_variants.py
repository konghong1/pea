"""变体点击测试：到底哪种真实点击能让 H1 按钮收到 mousedown。
每次点击前：重新聚焦编辑区 + 全选 + 清空 execLog + 重新测量按钮 rect。
"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

def setup(page):
    page.goto("http://localhost:5173", wait_until="networkidle")
    page.wait_for_timeout(500)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    ts = int(time.time())
    page.fill('input[placeholder="you@pea.ai"]', f"tnecv_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "TNE")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    page.locator("button", has_text="新建项目").first.click()
    page.wait_for_timeout(2000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    page.locator('.pea-toolbar .pea-tlb-btn[aria-label="添加节点"]').first.click()
    page.wait_for_timeout(800)
    page.locator(".pea-add-menu-item", has_text="文本").first.click()
    page.wait_for_timeout(800)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.locator(".pea-canvas-controls").locator("button[title='适配视图 (F)']").click()
    page.wait_for_timeout(700)
    node = page.locator(".react-flow__node").first
    node.dblclick()
    page.wait_for_timeout(1800)
    editor = page.locator(".tne-editor-content")
    editor.click()
    page.wait_for_timeout(150)
    page.keyboard.type("测试标题格式化的文本", delay=15)
    page.wait_for_timeout(200)

def prep(page):
    page.evaluate("""() => {
        const ed = document.querySelector('.tne-editor-content');
        ed.focus();
        const s = window.getSelection(); const r = document.createRange();
        r.selectNodeContents(ed); s.removeAllRanges(); s.addRange(r);
        window.__execLog = [];
        const orig = document.execCommand.bind(document);
        document.execCommand = function(c,u,v){ window.__execLog.push({c,v,ret:(()=>{try{return orig(c,u,v)}catch(e){return 'ERR'}})()}); return window.__execLog[window.__execLog.length-1].ret; };
    }""")

def trace(page):
    return page.evaluate("""() => ({
        execLog: window.__execLog,
        target: window.__lastTarget || null,
        innerHTML: document.querySelector('.tne-editor-content').innerHTML.slice(0,60),
        activeIsEditor: document.activeElement === document.querySelector('.tne-editor-content'),
    })""")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))

        # 全局捕获：记录最近一次 mousedown 的 target
        setup(page)
        page.evaluate("""() => {
            document.addEventListener('mousedown', (e) => { window.__lastTarget = (e.target.className&&e.target.className.toString().slice(0,40)) + '|' + e.target.tagName + '|inBtn=' + (!!e.target.closest && !!e.target.closest('.tne-tool-btn')); }, true);
        }""")

        # 变体1：locator.click（Playwright 标准）
        prep(page)
        try:
            page.locator('.tne-tool-btn[title*="一级标题"]').first.click(timeout=5000)
        except Exception as e:
            print("[v1 locator.click] ERR", str(e)[:120])
        r1 = trace(page)
        print("[v1] execLog:", json.dumps(r1['execLog'], ensure_ascii=False), "| target:", r1['target'], "| h1?", "<h1>" in r1['innerHTML'], "| focus:", r1['activeIsEditor'])

        # 变体2：page.mouse.click 用最新测量的中心
        prep(page)
        rect = page.evaluate("""() => { const b=document.querySelector('.tne-tool-btn[title*=\"一级标题\"]').getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}; }""")
        try:
            page.mouse.click(rect['x'], rect['y'])
        except Exception as e:
            print("[v2 mouse.click] ERR", str(e)[:120])
        r2 = trace(page)
        print("[v2] execLog:", json.dumps(r2['execLog'], ensure_ascii=False), "| target:", r2['target'], "| h1?", "<h1>" in r2['innerHTML'], "| focus:", r2['activeIsEditor'], "| rect:", rect)

        # 变体3：page.mouse.move + down + up
        prep(page)
        rect3 = page.evaluate("""() => { const b=document.querySelector('.tne-tool-btn[title*=\"一级标题\"]').getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2}; }""")
        page.mouse.move(rect3['x'], rect3['y'])
        page.wait_for_timeout(50)
        page.mouse.down()
        page.mouse.up()
        page.wait_for_timeout(300)
        r3 = trace(page)
        print("[v3] execLog:", json.dumps(r3['execLog'], ensure_ascii=False), "| target:", r3['target'], "| h1?", "<h1>" in r3['innerHTML'], "| focus:", r3['activeIsEditor'])

        # 变体4：force click
        prep(page)
        try:
            page.locator('.tne-tool-btn[title*="一级标题"]').first.click(force=True, timeout=5000)
        except Exception as e:
            print("[v4 force] ERR", str(e)[:120])
        r4 = trace(page)
        print("[v4] execLog:", json.dumps(r4['execLog'], ensure_ascii=False), "| target:", r4['target'], "| h1?", "<h1>" in r4['innerHTML'], "| focus:", r4['activeIsEditor'])

        # 额外：在点击前 dump 按钮及其祖先的 transform/filter/willChange/position/pointerEvents
        style = page.evaluate("""() => {
            const b = document.querySelector('.tne-tool-btn[title*=\"一级标题\"]');
            const chain = [];
            let el = b;
            for (let i=0; i<6 && el; i++) { const cs = getComputedStyle(el); chain.push({ cls: el.className&&el.className.toString().slice(0,30), tag: el.tagName, transform: cs.transform, filter: cs.filter, willChange: cs.willChange, position: cs.position, pe: cs.pointerEvents, z: cs.zIndex }); el = el.parentElement; }
            return chain;
        }""")
        print("[style chain] ", json.dumps(style, ensure_ascii=False))

        browser.close()

if __name__ == "__main__":
    main()
