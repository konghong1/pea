"""实验：验证 Modal（portal）内按钮的 React onMouseDown 是否触发，以及原生监听是否可达。"""
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

        page.goto("http://localhost:5173", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tneport_{ts}@pea.dev")
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
        page.wait_for_timeout(300)
        page.locator(".pea-canvas-controls").locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(700)
        page.locator(".react-flow__node").first.dblclick()
        page.wait_for_timeout(1200)

        editor = page.locator(".tne-editor-content")
        editor.click()
        page.wait_for_timeout(200)
        page.keyboard.type("这是一段用于测试标题格式化的文本。", delay=20)
        page.wait_for_timeout(300)

        # 实验：原生 mousedown dispatch 是否会触发 React onMouseDown（exec -> <h1>）
        res = page.evaluate("""() => {
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            const editor = document.querySelector('.tne-editor-content');
            editor.focus();
            const sel = getSelection(); const r = document.createRange();
            r.selectNodeContents(editor); sel.removeAllRanges(); sel.addRange(r);
            const before = editor.innerHTML;

            // 标记：给按钮直接挂一个原生 mousedown 监听，确认原生事件可达
            window.__nativeFired = false;
            const nativeFn = () => { window.__nativeFired = true; };
            btn.addEventListener('mousedown', nativeFn, true);

            // 派发原生 mousedown（bubbles+cancelable），模拟真实点击
            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));

            const after = editor.innerHTML;
            const out = {
                before: before.slice(0,40),
                after: after.slice(0,40),
                changed: before !== after,
                hasH1: /<h1/i.test(after),
                nativeFired: window.__nativeFired,
                activeIsEditor: document.activeElement === editor
            };
            btn.removeEventListener('mousedown', nativeFn, true);
            return out;
        }""")
        print("[experiment] 原生 dispatch mousedown:", json.dumps(res, ensure_ascii=False))

        # 若 React onMouseDown 未触发（changed=false），则尝试：用真实 Playwright 点击，再测
        # 额外：检查 portal 根 & React root 关系
        dom = page.evaluate("""() => {
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            const root = document.getElementById('root') || document.querySelector('#root');
            let cur = btn, depth=0, outsideRoot=false;
            while (cur && cur !== document.body) {
                if (cur === root) { outsideRoot = false; break; }
                cur = cur.parentElement; depth++;
                if (depth > 50) break;
            }
            return {
                btnInsideRootOrBodyPath: depth,
                rootExists: !!root,
                bodyDirectChildOfRoot: root ? (root.parentElement === document.body) : null,
                // 按钮是否在某 modal portal 容器内
                modalAncestor: !!btn.closest('.ant-modal') || !!btn.closest('.text-node-editor-modal')
            };
        }""")
        print("[dom] portal/root 关系:", json.dumps(dom, ensure_ascii=False))

        browser.close()

if __name__ == "__main__":
    main()
