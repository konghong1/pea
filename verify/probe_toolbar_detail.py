"""Probe toolbar component measurements."""
from playwright.sync_api import sync_playwright
import os, time

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel='chrome')
        page = b.new_page(viewport={'width': 1440, 'height': 900})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'cropprobe_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'nav: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text="图片").first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        if not os.path.exists(src):
            for f in os.listdir(os.path.dirname(__file__)):
                if f.startswith('test_crop') and f.endswith('.png'):
                    src = os.path.join(os.path.dirname(__file__), f)
                    break
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2000)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1500)

        # Probe each toolbar element
        info = page.evaluate(r'''() => {
            const tb = document.querySelector('.pea-crop-toolbar');
            const btns = tb ? Array.from(tb.querySelectorAll('button')) : [];
            const seps = tb ? Array.from(tb.querySelectorAll('.pea-crop-toolbar-sep, .pea-crop-toolbar-sep')) : [];
            const dd = tb ? tb.querySelector('.ant-dropdown-trigger') : null;
            const ddWrap = tb ? tb.querySelector('div[role=button]') : null;
            const span = tb ? Array.from(tb.querySelectorAll('span')) : [];
            return {
                toolbar: (() => {
                    if (!tb) return null;
                    const r = tb.getBoundingClientRect();
                    const cs = getComputedStyle(tb);
                    return {
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                        right: Math.round(r.right), bottom: Math.round(r.bottom),
                        padding: cs.padding,
                        gap: cs.gap,
                        flexDirection: cs.flexDirection,
                        position: cs.position,
                        children: tb.children.length,
                    };
                })(),
                buttons: btns.map(b => {
                    const r = b.getBoundingClientRect();
                    const cs = getComputedStyle(b);
                    return {
                        tag: b.tagName, cls: b.className, txt: b.textContent.trim().slice(0,30),
                        ariaLabel: b.getAttribute('aria-label'),
                        title: b.title,
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                        cssHeight: cs.height, cssWidth: cs.width, cssPadding: cs.padding,
                    };
                }),
                separators: seps.length,
                customInputs: tb ? tb.querySelectorAll('.pea-crop-custom-ratio').length : 0,
            };
        }''')

        print('=== Toolbar Detail ===')
        print(f'  toolbar: {info["toolbar"]}')
        print(f'  buttons ({len(info["buttons"])}):')
        for b in info['buttons']:
            print(f'    {b}')
        print(f'  separators: {info["separators"]}')
        print(f'  customInputs: {info["customInputs"]}')

        b.close()

if __name__ == '__main__':
    main()
