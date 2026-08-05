"""真实环境调试：文本节点双击编辑 Modal 的工具栏格式化是否生效。

流程：注册新用户 → 新建项目 → 添加文本节点 → 双击 → 在 Modal 编辑区输入 → 点 H1 → 诊断。

跑法：python verify/tne_modal_debug.py
"""
import sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
errors = []
def shot(page, name):
    p = SHOTS / f"tne_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p.name}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"CONSOLE[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))

        # 1) 注册登录
        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tnedebug_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "TNE")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        # 新建项目
        page.locator("button", has_text="新建项目").first.click()
        page.wait_for_timeout(2000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        shot(page, "01_canvas")

        # 2) 添加文本节点
        page.locator('.pea-toolbar .pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        controls = page.locator(".pea-canvas-controls")
        controls.locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(700)
        shot(page, "02_node_added")

        # 3) 双击文本节点 -> 打开 Modal
        node = page.locator(".react-flow__node").first
        node.dblclick()
        page.wait_for_timeout(1200)
        modal = page.locator(".text-node-editor-modal")
        print("[info] Modal 可见:", modal.is_visible())
        editor = page.locator(".tne-editor-content")
        print("[info] 编辑区可见:", editor.is_visible())
        shot(page, "03_modal_open")

        # 4) 在编辑区输入文字
        editor.click()
        page.wait_for_timeout(200)
        page.keyboard.type("这是一段用于测试标题格式化的文本。", delay=20)
        page.wait_for_timeout(300)
        before_html = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML")
        print("[info] 输入后编辑区 innerHTML:", repr(before_html[:80]))

        # 5) 诊断编辑区焦点 + 当前选区
        diag1 = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            const sel = window.getSelection();
            return {
                activeElementIsEditor: document.activeElement === el,
                selectionRangeCount: sel ? sel.rangeCount : -1,
                editorFocused: el === document.activeElement,
            };
        }""")
        print("[diag] 点击输入后焦点/选区:", json.dumps(diag1, ensure_ascii=False))

        # 5.5) 补充诊断：在编辑区已聚焦时，用 evaluate 同步执行 execCommand（验证 Modal 环境下是否可用）
        sync_res = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            el.focus();
            // 确保选区在编辑区内（全选）
            const sel = window.getSelection();
            const r = document.createRange();
            r.selectNodeContents(el);
            sel.removeAllRanges();
            sel.addRange(r);
            let ok = false;
            try { ok = document.execCommand('formatBlock', false, '<h1>'); } catch(e) { ok = 'ERR:'+e.message; }
            return { ok, html: el.innerHTML.slice(0,80) };
        }""")
        print("[diag] 同步 evaluate execCommand(formatBlock<h1>):", json.dumps(sync_res, ensure_ascii=False))
        # 重置回纯文本，方便后续点击测试
        page.evaluate("() => { const el=document.querySelector('.tne-editor-content'); el.innerHTML='这是一段用于测试标题格式化的文本。'; }")
        page.wait_for_timeout(200)

        # 5.6) 决定性诊断：模拟真实 exec 的"el.focus() + 不设选区 + execCommand"
        focus_only = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            el.focus();
            const ok = document.execCommand('formatBlock', false, '<h1>');
            return { ok, html: el.innerHTML.slice(0,60) };
        }""")
        print("[diag] focus-only execCommand:", json.dumps(focus_only, ensure_ascii=False))
        page.evaluate("() => { const el=document.querySelector('.tne-editor-content'); el.innerHTML='这是一段用于测试标题格式化的文本。'; }")
        page.wait_for_timeout(150)

        # 5.7) 决定性诊断：用 dispatchEvent 模拟按钮点击的完整事件序列，观察焦点/内容
        phase_diag = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            const btn = document.querySelector('.tne-toolbar .tne-tool-btn[title*="一级标题"]');
            el.focus();
            const r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
            const s = getSelection(); s.removeAllRanges(); s.addRange(r);
            const before = document.activeElement === el;
            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
            const afterMd = document.activeElement === el;
            btn.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
            btn.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            const afterClick = document.activeElement === el;
            return { before, afterMd, afterClick, html: el.innerHTML.slice(0,40) };
        }""")
        print("[diag] 事件序列焦点/内容:", json.dumps(phase_diag, ensure_ascii=False))
        page.evaluate("() => { const el=document.querySelector('.tne-editor-content'); el.innerHTML='这是一段用于测试标题格式化的文本。'; }")
        page.wait_for_timeout(150)

        # 5.8) 事件流追踪 + 探针：确认按钮 data-cmd 属性 + window capture 监听器是否拦截
        probe = page.evaluate("""() => {
            const btn = document.querySelector('.tne-toolbar .tne-tool-btn[title*="一级标题"]');
            window.__trace = [];
            const el = document.querySelector('.tne-editor-content');
            const modal = document.querySelector('.ant-modal-content') || document.querySelector('.text-node-editor-modal');
            const log = (who, ev, extra) => window.__trace.push(`${who}:${ev}${extra?(' '+extra):''}`);
            // 探针：注入一个 window capture mousedown 监听器，验证 capture 机制是否先于 modal
            window.addEventListener('mousedown', (e) => {
                const t = e.target;
                log('PROBE-win-cap', 'mousedown', t.className || t.tagName);
            }, true);
            el.addEventListener('focus', () => log('editor','focus'));
            el.addEventListener('blur', () => log('editor','blur'));
            if (modal) modal.addEventListener('mousedown', () => log('modal','mousedown'), true);
            return {
                btnDataCmd: btn ? btn.getAttribute('data-cmd') : null,
                btnDataValue: btn ? btn.getAttribute('data-value') : null,
                btnOuter: btn ? btn.outerHTML.slice(0,80) : null,
            };
        }""")
        print("[probe] 按钮属性:", json.dumps(probe, ensure_ascii=False))
        # 6) 点击 H1 按钮
        h1 = page.locator('.tne-toolbar .tne-tool-btn[title*="一级标题"]').first
        print("[info] H1 按钮可见:", h1.is_visible())
        h1.click()
        page.wait_for_timeout(500)
        trace = page.evaluate("() => window.__trace")
        print("[trace] 真实点击事件流:", json.dumps(trace, ensure_ascii=False))

        after_html = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML")
        print("[info] 点击 H1 后编辑区 innerHTML:", repr(after_html[:120]))
        has_h1 = "<h1" in after_html.lower()
        print(">>> 是否生成 <h1>:", has_h1)
        shot(page, "04_after_h1")

        # 7) 再次诊断：点击 H1 后焦点是否还在编辑区
        diag2 = page.evaluate("""() => {
            const el = document.querySelector('.tne-editor-content');
            return { activeElementClass: document.activeElement ? document.activeElement.className : null };
        }""")
        print("[diag] 点击 H1 后 activeElement:", json.dumps(diag2, ensure_ascii=False))

        # 8) 测试粗体（先选中部分文字）
        editor.click()
        page.keyboard.press("Control+A")
        page.wait_for_timeout(100)
        bold = page.locator('.tne-toolbar .tne-tool-btn[title*="粗体"]').first
        bold.click()
        page.wait_for_timeout(400)
        after_bold = page.evaluate("() => document.querySelector('.tne-editor-content').innerHTML")
        print("[info] 全选+粗体后 innerHTML:", repr(after_bold[:120]))
        has_b = "<b" in after_bold.lower() or "<strong" in after_bold.lower()
        print(">>> 是否生成粗体:", has_b)

        browser.close()
        print("\n=== 结论 ===")
        print(f"  H1 生效: {has_h1}")
        print(f"  粗体生效: {has_b}")

if __name__ == "__main__":
    main()
