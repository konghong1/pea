"""综合排查：文本节点的两个编辑面 —— 边框框(NodeChatPrompt) + 全屏 Modal。
流程：注册 → 新建项目 → 添加文本节点 →
  A) 单选文本节点 → 检查 .node-input-bar(边框框) 是否出现、按钮/输入是否可用、有无 JS 报错
  B) 双击文本节点 → Modal → 等动画稳定后点 H1 → 检查 exec 是否生效、焦点是否丢失、有无报错
"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
def shot(page, name):
    try:
        page.screenshot(path=str(SHOTS / f"comp_{name}.png"), full_page=False)
        print(f"[shot] comp_{name}.png")
    except Exception as e:
        print("[shot] fail", e)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errs = []
        page.on("console", lambda m: print(f"CONSOLE[{m.type}] {m.text[:200]}"))
        page.on("pageerror", lambda e: (errs.append(str(e)), print(f"PAGEERROR {e}")))

        # 1) 注册登录
        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tnecomp_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "TNE")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.locator("button", has_text="新建项目").first.click()
        page.wait_for_timeout(2000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        # 2) 添加文本节点
        page.locator('.pea-toolbar .pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        page.locator(".pea-canvas-controls").locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(700)
        shot(page, "01_node_added")

        # ════════════ A) 边框框 NodeChatPrompt ════════════
        print("\n===== A) 边框框 (NodeChatPrompt input bar) =====")
        node = page.locator(".react-flow__node").first
        node.click()  # 单选
        page.wait_for_timeout(1500)
        a1 = page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('.pea-node-editor-anchor'));
            const bars = Array.from(document.querySelectorAll('.node-input-bar'));
            const info = bars.map(b => ({
                kind: b.getAttribute('data-kind'),
                parentClass: b.parentElement ? b.parentElement.className : null,
                htmlHead: b.outerHTML.slice(0, 300),
                buttons: b.querySelectorAll('button').length,
                inputs: b.querySelectorAll('textarea,input,[contenteditable="true"]').length,
            }));
            return { anchorCount: anchors.length, barCount: bars.length, bars: info };
        }""")
        print("[A] anchors/bars:", json.dumps(a1, ensure_ascii=False)[:1500])
        shot(page, "02_borderbox")

        # 尝试在边框框里输入 + 点击一个按钮
        a2 = page.evaluate("""() => {
            const bar = document.querySelector('.node-input-bar');
            if (!bar) return { ok: false, reason: 'no bar' };
            // 找输入区
            const input = bar.querySelector('textarea,input,[contenteditable="true"]') || bar.querySelector('.node-prompt-input, .np-input, [role=textbox]');
            const btn = bar.querySelector('button');
            return {
                ok: true,
                hasInput: !!input,
                inputClass: input ? input.className : null,
                inputTag: input ? input.tagName : null,
                firstBtnText: btn ? (btn.innerText||btn.getAttribute('title')||'').slice(0,20) : null,
                barHtml: bar.innerHTML.slice(0, 600),
            };
        }""")
        print("[A] bar internals:", json.dumps(a2, ensure_ascii=False)[:1500])

        # ════════════ B) 全屏 Modal ════════════
        print("\n===== B) 全屏编辑 Modal =====")
        node.dblclick()
        page.wait_for_timeout(1800)  # 等 Modal 入场动画稳定（关键！）
        modal = page.locator(".text-node-editor-modal")
        print("[B] Modal 可见:", modal.is_visible())
        editor = page.locator(".tne-editor-content")
        editor.click()
        page.wait_for_timeout(200)
        page.keyboard.type("这是一段用于测试标题格式化的文本。", delay=15)
        page.wait_for_timeout(300)
        before = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML.slice(0,60)")
        print("[B] 输入后 innerHTML:", repr(before))

        # H1 按钮：数量 + 真实 locator 点击（Playwright 自带 actionability + 自动等待动画）
        b1 = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('.tne-tool-btn'));
            const groups = document.querySelectorAll('.tne-toolbar-group').length;
            const modals = document.querySelectorAll('.ant-modal:not(.ant-modal-confirm)').length;
            return { btnCount: btns.length, groupCount: groups, modalCount: modals,
                     firstBtnTitle: btns[0] ? btns[0].getAttribute('title') : null };
        }""")
        print("[B] 工具栏统计:", json.dumps(b1, ensure_ascii=False))

        h1 = page.locator('.tne-tool-btn[title*="一级标题"]').first
        print("[B] H1 可见:", h1.is_visible())
        # 全选编辑区文字，确保有选区
        page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            const sel = window.getSelection(); const r = document.createRange();
            r.selectNodeContents(el); sel.removeAllRanges(); sel.addRange(r);
        }""")
        page.wait_for_timeout(150)
        try:
            h1.click(timeout=5000)  # 真实点击，等动画稳定后
        except Exception as e:
            print("[B] H1 click error:", str(e)[:120])
        page.wait_for_timeout(400)
        after = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML.slice(0,80)")
        focus = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            return { activeIsEditor: document.activeElement === el };
        }""")
        print("[B] H1 点击后 innerHTML:", repr(after))
        print("[B] 点击后焦点在编辑区:", focus.get("activeIsEditor"))
        print("[B] H1 是否生效(含<h1>):", "<h1>" in after)
        shot(page, "03_modal_h1")

        print("\n===== PAGE ERRORS =====")
        print("\n".join(errs) if errs else "(无 JS 报错)")

        browser.close()

if __name__ == "__main__":
    main()
