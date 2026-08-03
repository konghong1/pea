import time
from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
EMAIL = "test@example.com"
PASSWORD = "password123"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(f"{WEB}/login")
        page.fill("input#email, input[type='email'], .ant-form-item-control-input input:first-of-type", EMAIL)
        page.fill("input#password, input[type='password']", PASSWORD)
        page.click("button:has-text('登 录')")
        page.wait_for_load_state("networkidle")
        page.click("text=未命名画布")
        page.wait_for_selector(".react-flow__pane", timeout=30000)
        time.sleep(1)

        ids = page.evaluate("""() => {
            const s = window.__canvas.getState();
            const id1 = s.addNode({ kind: 'image', label: '图片' }, { x: 400, y: 300 });
            const id2 = s.addNode({ kind: 'text', label: '文本' }, { x: 800, y: 300 });
            return [id1, id2];
        }""")
        time.sleep(1)
        info = page.evaluate("""(id) => {
            const el = document.querySelector('.react-flow__node[data-id="' + id + '"]');
            if (!el) return null;
            const inner = el.querySelector('.pea-node');
            const handle = el.querySelector('.pea-handle-right');
            return {
                wrapperClass: el.className,
                innerClass: inner ? inner.className : null,
                handleClass: handle ? handle.className : null,
                handleStyle: handle ? handle.getAttribute('style') : null,
                handleOpacity: handle ? getComputedStyle(handle).opacity : null,
                handleVisibility: handle ? getComputedStyle(handle).visibility : null,
                handleDisplay: handle ? getComputedStyle(handle).display : null,
            };
        }""", ids[0])
        print(info)
        browser.close()

if __name__ == "__main__":
    main()
