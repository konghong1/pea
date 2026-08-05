"""独立验证：注入与 Modal 工具栏完全相同的 DOM+CSS，验证 pointer-events:none 修复是否让按钮收到真实点击。
不需要后端 —— 直接在 localhost:5173 的 SPA 页面上注入测试。"""
import json
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(500)

        # 注入与 TextNodeEditorModal 完全相同的工具栏 DOM + CSS
        page.evaluate("""() => {
            // 注入 CSS（从 index.css 复制的关键规则）
            const style = document.createElement('style');
            style.textContent = `
                .test-modal { position:fixed; inset:20px; background:#1a1a22; border-radius:20px; padding:16px; z-index:9999; }
                .tne-toolbar { display:flex; align-items:center; gap:2px; padding:10px 20px; background:rgba(0,0,0,.15); border-bottom:1px solid rgba(128,128,140,.14); flex-wrap:wrap; }
                .tne-toolbar-group { display:flex; align-items:center; gap:1px; pointer-events: none; }
                .tne-tool-btn { display:inline-flex; align-items:center; justify-content:center; min-width:30px; height:30px; padding:0 7px; border:none; border-radius:8px; background:transparent; color:#9ca3af; font-size:12px; cursor:pointer; transition:all .15s ease; line-height:1; pointer-events: auto; }
                .tne-tool-btn:hover { background:rgba(255,255,255,.08); color:#e8e8ee; }
                .tne-editor-content { min-height:200px; padding:16px; outline:none; font-size:14px; color:#e8e8ee; caret-color:#1fa2dc; }
            `;
            document.head.appendChild(style);

            // 注入工具栏（与 Modal JSX 完全相同的结构）
            const container = document.createElement('div');
            container.className = 'test-modal';
            container.innerHTML = `
                <div class="tne-toolbar">
                    <div class="tne-toolbar-group">
                        <button type="button" class="tne-tool-btn" title="一级标题" data-cmd="formatBlock" data-value="H1"><span style="font-size:16px;font-weight:700">H1</span></button>
                        <button type="button" class="tne-tool-btn" title="粗体" data-cmd="bold"><b>B</b></button>
                    </div>
                </div>
                <div class="tne-editor-content" contenteditable>这是一段用于测试的文本。</div>
            `;
            document.body.appendChild(container);

            // 探针：记录事件
            window.__probe = { execLog:[], mdTarget:null, btnFired:false };
            const editor = container.querySelector('.tne-editor-content');
            
            // 覆盖 execCommand
            const orig = document.execCommand.bind(document);
            document.execCommand = function(c,u,v){ window.__probe.execLog.push({c,v}); return orig(c,u,v); };

            // 按钮上的 onMouseDown（模拟 React 的）
            const h1 = container.querySelector('.tne-tool-btn[title="一级标题"]');
            h1.addEventListener('mousedown', (e) => {
                e.preventDefault();
                window.__probe.btnFired = true;
                editor.focus();
                document.execCommand('formatBlock', false, '<h1>');
            });

            // doc capture 记录 target
            document.addEventListener('mousedown', (e) => {
                window.__probe.mdTarget = (e.target.className&&e.target.className.toString().slice(0,40))+'|'+e.target.tagName+'|inBtn='+(!!e.target.closest&&!!e.target.closest('.tne-tool-btn'));
            }, true);
        }""")

        # 真实点击 H1 按钮
        h1 = page.locator('.tne-tool-btn[title="一级标题"]')
        rect = page.evaluate("() => document.querySelector('.tne-tool-btn[title=\"一级标题\"]').getBoundingClientRect()")
        cx = rect['x'] + rect['width']/2
        cy = rect['y'] + rect['height']/2

        # 先聚焦编辑区并选中文本
        page.evaluate("() => { const ed=document.querySelector('.tne-editor-content'); ed.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(ed); s.removeAllRanges(); s.addRange(r); }")

        # 真实点击
        page.mouse.click(cx, cy)
        page.wait_for_timeout(300)

        res = page.evaluate("""() => ({
            mdTarget: window.__probe.mdTarget,
            btnFired: window.__probe.btnFired,
            execLog: window.__probe.execLog,
            innerHTML: document.querySelector('.tne-editor-content').innerHTML.slice(0,80),
            activeIsEditor: document.activeElement === document.querySelector('.tne-editor-content'),
        })""")

        print("[STANDALONE] mousedown target:", res['mdTarget'])
        print("[STANDALONE] btn mousedown fired:", res['btnFired'])
        print("[STANDALONE] execLog:", json.dumps(res['execLog'], ensure_ascii=False))
        print("[STANDALONE] innerHTML:", repr(res['innerHTML']))
        print("[STANDALONE] <h1> applied:", '<h1>' in res['innerHTML'])
        print("[STANDALONE] focus kept:", res['activeIsEditor'])

        browser.close()

if __name__ == "__main__":
    main()
