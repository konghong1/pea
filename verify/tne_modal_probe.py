"""精准探针：点击 H1 时到底发生了什么。
- 覆盖 document.execCommand 记录调用
- document 捕获阶段 mousedown 记录 e.target / defaultPrevented / 是否落在 .tne-tool-btn 内
- 直接在 H1 按钮上挂 mousedown 记录是否触发
- 监听编辑区 focus/blur
"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))

        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tneprobe_{ts}@pea.dev")
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
        # 全选
        page.evaluate("""() => { const el=document.querySelector('.tne-editor-content'); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(el); s.removeAllRanges(); s.addRange(r); }""")
        page.wait_for_timeout(150)

        # 注入探针
        page.evaluate("""() => {
            window.__execLog = [];
            const orig = document.execCommand.bind(document);
            document.execCommand = function(cmd, ui, val){ window.__execLog.push({cmd, val, ret: (()=>{try{return orig(cmd, ui, val)}catch(e){return 'ERR:'+e.message}})()}); return window.__execLog[window.__execLog.length-1].ret; };
            window.__mdDoc = [];
            document.addEventListener('mousedown', (e) => {
                const t = e.target;
                const inBtn = !!(t.closest && t.closest('.tne-tool-btn'));
                window.__mdDoc.push({ cls: t.className && t.className.toString().slice(0,40), tag: t.tagName, defaultPrevented: e.defaultPrevented, inBtn });
            }, true);
            const h1 = document.querySelector('.tne-tool-btn[title*="一级标题"]');
            window.__btnFired = false;
            if (h1) h1.addEventListener('mousedown', () => { window.__btnFired = true; }, true);
            window.__focusLog = [];
            const ed = document.querySelector('.tne-editor-content');
            ed.addEventListener('focus', () => window.__focusLog.push('focus'));
            ed.addEventListener('blur', () => window.__focusLog.push('blur'));
            window.__h1Rect = h1 ? h1.getBoundingClientRect() : null;
            window.__h1Efp = h1 ? (()=>{ const r=h1.getBoundingClientRect(); const cx=r.x+r.width/2, cy=r.y+r.height/2; const top=document.elementFromPoint(cx,cy); return { cx, cy, topCls: top?top.className&&top.className.toString().slice(0,40):null, topTag: top?top.tagName:null, topInBtn: !!(top&&top.closest&&top.closest('.tne-tool-btn')) }; })() : null;
        }""")
        probe_before = page.evaluate("() => ({ h1Rect: window.__h1Rect, h1Efp: window.__h1Efp })")
        print("[probe] H1 rect:", json.dumps(probe_before.get('h1Rect'), ensure_ascii=False))
        print("[probe] H1 elementFromPoint:", json.dumps(probe_before.get('h1Efp'), ensure_ascii=False))

        # 真实点击 H1
        h1 = page.locator('.tne-tool-btn[title*="一级标题"]').first
        try:
            h1.click(timeout=5000)
        except Exception as e:
            print("[click] error:", str(e)[:150])
        page.wait_for_timeout(400)

        res = page.evaluate("""() => ({
            execLog: window.__execLog,
            mdDoc: window.__mdDoc,
            btnFired: window.__btnFired,
            focusLog: window.__focusLog,
            innerHTML: document.querySelector('.tne-editor-content').innerHTML.slice(0,80),
            activeIsEditor: document.activeElement === document.querySelector('.tne-editor-content'),
        })""")
        print("[RESULT] execLog:", json.dumps(res['execLog'], ensure_ascii=False))
        print("[RESULT] doc mousedown trace:", json.dumps(res['mdDoc'], ensure_ascii=False))
        print("[RESULT] H1 btn mousedown fired:", res['btnFired'])
        print("[RESULT] focus/blur log:", res['focusLog'])
        print("[RESULT] innerHTML:", repr(res['innerHTML']))
        print("[RESULT] activeIsEditor:", res['activeIsEditor'])
        browser.close()

if __name__ == "__main__":
    main()
