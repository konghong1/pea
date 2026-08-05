"""聚焦验证：TextNodeEditorModal 工具栏按钮（H1/粗体）在真实点击下是否生效。
流程：注册 -> 项目 -> 文本节点 -> 双击打开 Modal -> 输入 -> 点 H1（modal 作用域内）
-> 诊断 elementFromPoint 命中 -> 验证 <h1> + 编辑区仍聚焦。
"""
import sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

def shot(page, name):
    p = SHOTS / f"fix_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p.name}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))

        # 1) 注册登录
        page.goto("http://localhost:5173", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tnefix_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "TNE")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)

        # 2) 新建项目 + 文本节点
        page.locator("button", has_text="新建项目").first.click()
        page.wait_for_timeout(2000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.locator('.pea-toolbar .pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.locator(".pea-canvas-controls").locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(700)
        shot(page, "01_canvas")

        # 3) 双击文本节点 -> 打开 Modal
        page.locator(".react-flow__node").first.dblclick()
        page.wait_for_timeout(1200)
        modal = page.locator(".text-node-editor-modal")
        print("[info] Modal 可见:", modal.is_visible())
        editor = page.locator(".tne-editor-content")
        editor.click()
        page.wait_for_timeout(200)
        page.keyboard.type("这是一段用于测试标题格式化的文本。", delay=20)
        page.wait_for_timeout(300)
        shot(page, "02_modal_input")

        # 4) 诊断：modal 内 H1 按钮的命中测试
        geo = page.evaluate("""() => {
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            if (!btn) return {found:false};
            const r = btn.getBoundingClientRect();
            const cx = r.left + r.width/2, cy = r.top + r.height/2;
            const top = document.elementFromPoint(cx, cy);
            const chain = [];
            let e = top;
            for (let i=0;i<5 && e;i++){ chain.push((e.className||e.tagName)+''); e=e.parentElement; }
            const cs = getComputedStyle(btn);
            return {
                found:true,
                rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                topClass: top ? (top.className||top.tagName)+'' : null,
                topIsBtnOrChild: !!(top && (top===btn || btn.contains(top))),
                btnPointerEvents: cs.pointerEvents,
                topPointerEvents: top ? getComputedStyle(top).pointerEvents : null,
                chain
            };
        }""")
        print("[geo] H1 按钮命中测试:", json.dumps(geo, ensure_ascii=False))

        # 5) 真实点击 H1（modal 作用域内）
        h1 = page.locator('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]').first
        print("[info] H1 按钮可见:", h1.is_visible())
        try:
            h1.click(timeout=5000)
        except Exception as e:
            print("[warn] H1 点击异常:", str(e)[:120])
        page.wait_for_timeout(400)
        after_html = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML")
        print("[info] 点击 H1 后 innerHTML:", repr(after_html[:120]))
        has_h1 = "<h1" in after_html.lower()
        print(">>> H1 生效:", has_h1)
        # 焦点是否仍在编辑区（判断是否还闪/失焦）
        focus_diag = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            return { activeIsEditor: document.activeElement === el };
        }""")
        print("[focus] 点击 H1 后编辑区仍聚焦:", json.dumps(focus_diag, ensure_ascii=False))
        shot(page, "03_after_h1")

        # 6) 全选 + 粗体
        editor.click()
        page.keyboard.press("Control+A")
        page.wait_for_timeout(150)
        bold = page.locator('.text-node-editor-modal .tne-tool-btn[title*="粗体"]').first
        bold.click(timeout=5000)
        page.wait_for_timeout(400)
        after_bold = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML")
        print("[info] 全选+粗体后 innerHTML:", repr(after_bold[:120]))
        has_b = ("<b" in after_bold.lower()) or ("<strong" in after_bold.lower())
        print(">>> 粗体生效:", has_b)
        shot(page, "04_after_bold")

        # 7) 字符数（验证非 0）
        wc = page.evaluate("() => { const s=[...document.querySelectorAll('.text-node-editor-modal span')].map(x=>x.textContent).join('|'); return s; }")
        print("[info] Modal 内 span 文本(含字符数):", repr(wc[:200]))

        browser.close()
        print("\n=== 结论 ===")
        print("  H1 生效:", has_h1)
        print("  粗体生效:", has_b)

if __name__ == "__main__":
    main()
