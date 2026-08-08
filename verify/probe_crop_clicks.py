"""Diagnose click-outside-cancel and verify two-images fix path."""
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
            page.fill('input[placeholder="you@pea.ai"]', f'cropdiag_{ts}@pea.dev')
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
        src = os.path.join(os.path.dirname(__file__), 'test_crop_portrait.png')
        if not os.path.exists(src):
            src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(1800)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1500)

        # ── Test 1: click on dark mask area (within image but outside crop frame) ──
        print("=== Test 1: click on dark mask area (within stage, outside crop frame) ===")
        before = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        # click 30px above the crop frame, inside the image-stage
        info = page.evaluate(r'''() => {
            const stage = document.querySelector('.pea-crop-image-stage');
            const frame = document.querySelector('.pea-crop-frame');
            if (!stage || !frame) return null;
            const s = stage.getBoundingClientRect();
            const f = frame.getBoundingClientRect();
            return { stage: { x: s.x, y: s.y, w: s.width, h: s.height },
                     frame: { x: f.x, y: f.y, w: f.width, h: f.height } };
        }''')
        # Click above the frame but inside the stage
        cx = info['stage']['x'] + info['stage']['w'] / 2
        cy = info['frame']['y'] - 20  # 20px above frame
        page.mouse.click(cx, cy)
        page.wait_for_timeout(800)
        after = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        print(f"  click above frame @({cx:.0f},{cy:.0f}): {before['open']} → {after['open']}")

        # Test 2: click to the side of crop frame (still within stage)
        print("\n=== Test 2: click to the right of crop frame (within stage) ===")
        before = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        cx = info['frame']['x'] + info['frame']['w'] + 20  # 20px right of frame
        cy = info['stage']['y'] + info['stage']['h'] / 2
        page.mouse.click(cx, cy)
        page.wait_for_timeout(800)
        after = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        print(f"  click right of frame @({cx:.0f},{cy:.0f}): {before['open']} → {after['open']}")

        # Test 3: click outside stage but inside wrap (gap on right, where stage < wrap)
        print("\n=== Test 3: click outside stage but inside wrap (right gap) ===")
        before = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        wrap_box = page.evaluate(r'''() => {
            const w = document.querySelector('.pea-node-result-image-wrap');
            const r = w.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')
        # click 15px inside wrap right edge if stage is narrower (else use stage's edge)
        cx = wrap_box['x'] + wrap_box['w'] - 5  # 5px inside right
        cy = wrap_box['y'] + wrap_box['h'] / 2
        page.mouse.click(cx, cy)
        page.wait_for_timeout(800)
        after = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        print(f"  click wrap right @({cx:.0f},{cy:.0f}): {before['open']} → {after['open']}")

        # Test 4: click in negative space — node area (above stage)
        print("\n=== Test 4: click in node area, ABOVE stage (which overflows wrap top) ===")
        before = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        stage_box = page.evaluate(r'''() => {
            const s = document.querySelector('.pea-crop-stage');
            const r = s.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')
        node_box = page.evaluate(r'''() => {
            const n = document.querySelector('.pea-node-body-card');
            const r = n.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')
        # Click between node top and stage top, in the node's domain
        if node_box['y'] < stage_box['y']:
            cy = (node_box['y'] + stage_box['y']) / 2
        else:
            cy = node_box['y'] + 5
        cx = node_box['x'] + node_box['w'] / 2
        page.mouse.click(cx, cy)
        page.wait_for_timeout(800)
        after = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        print(f"  click in node but above stage @({cx:.0f},{cy:.0f}): {before['open']} → {after['open']}")

        # Test 5: click on ANOTHER node (does it deselect and cancel crop?)
        print("\n=== Test 5: click on empty pane (far away) ===")
        before = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        page.mouse.click(50, 400)  # far left, on sidebar — but actually this is sidebar
        page.wait_for_timeout(800)
        after = page.evaluate('''() => ({ open: !!document.querySelector('.pea-crop-overlay') })''')
        print(f"  click sidebar @50,400: {before['open']} → {after['open']}")

        if after['open']:
            page.keyboard.press('Escape')
            page.wait_for_timeout(400)

        b.close()

if __name__ == '__main__':
    main()
