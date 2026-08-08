"""Probe crop UI: find two-images and click-outside sources."""
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

        # Add image node + upload
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

        # ── PROBE 1: Check visibility of original <img> and any overlapping images ──
        info = page.evaluate(r'''() => {
            const origImg = document.querySelector('.pea-node-result-preview');
            const cropOverlay = document.querySelector('.pea-crop-overlay');
            const cropImg = document.querySelector('.pea-crop-image');
            const cropStage = document.querySelector('.pea-crop-stage');
            const cropImgStage = document.querySelector('.pea-crop-image-stage');
            const nodeCard = document.querySelector('.pea-node-body-card');
            function info(el) {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visibility: cs.visibility,
                    display: cs.display,
                    opacity: cs.opacity,
                    zIndex: cs.zIndex,
                    inlineStyle: el.style?.cssText ?? null,
                    visible: r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.1,
                };
            }
            return {
                origImg: info(origImg),
                cropOverlay: info(cropOverlay),
                cropImg: info(cropImg),
                cropStage: info(cropStage),
                cropImgStage: info(cropImgStage),
                nodeCard: info(nodeCard),
            };
        }''')
        print('\n=== PROBE 1: DOM state during crop ===')
        for k, v in info.items():
            print(f'  {k}: {v}')

        page.screenshot(path='shots/probe_two_images.png', full_page=False)
        print('\n  screenshot: shots/probe_two_images.png')

        # ── PROBE 2: What happens when we click outside the crop frame? ──
        # Get crop frame bounding box
        frame_box = page.evaluate(r'''() => {
            const f = document.querySelector('.pea-crop-frame');
            const r = f.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')
        stage_box = page.evaluate(r'''() => {
            const s = document.querySelector('.pea-crop-stage');
            const r = s.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')
        imgstage_box = page.evaluate(r'''() => {
            const s = document.querySelector('.pea-crop-image-stage');
            const r = s.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')

        # Find the gap (if any) between stage and frame — that's where "outside the crop frame" is
        print(f'\nstage card:  {stage_box}')
        print(f'image area:  {imgstage_box}')
        print(f'crop frame:  {frame_box}')

        # Test 1: click outside crop frame but inside stage (on the dark mask)
        # click in image-stage area but outside the frame
        click1_x = imgstage_box['x'] + 10  # top-left corner
        click1_y = imgstage_box['y'] + 10
        page.mouse.click(click1_x, click1_y)
        page.wait_for_timeout(700)
        still_open1 = page.evaluate('''() => !!document.querySelector('.pea-crop-overlay')''')
        print(f'\n  click outside frame INSIDE stage (dark mask) @({click1_x:.0f},{click1_y:.0f}): crop still open? {still_open1}')

        # Test 2: click outside stage but inside overlay
        # If stage is centered and smaller than container, there's a gap. Compute it.
        overlay_box = page.evaluate(r'''() => {
            const s = document.querySelector('.pea-crop-overlay');
            const r = s.getBoundingClientRect();
            return { x: r.x, y: r.y, w: r.width, h: r.height };
        }''')
        print(f'\n  overlay: {overlay_box}')
        # gap on right?
        if stage_box['x'] + stage_box['w'] + 30 < overlay_box['x'] + overlay_box['w']:
            gap_right_x = stage_box['x'] + stage_box['w'] + 15
            gap_right_y = overlay_box['y'] + overlay_box['h'] / 2
        else:
            gap_right_x = overlay_box['x'] + overlay_box['w'] - 15  # use overlay right edge
            gap_right_y = overlay_box['y'] + overlay_box['h'] / 2
        page.mouse.click(gap_right_x, gap_right_y)
        page.wait_for_timeout(700)
        still_open2 = page.evaluate('''() => !!document.querySelector('.pea-crop-overlay')''')
        print(f'  click outside stage (overlay gap) @({gap_right_x:.0f},{gap_right_y:.0f}): crop still open? {still_open2}')

        # If still open, try escape
        if still_open2:
            page.keyboard.press('Escape')
            page.wait_for_timeout(400)

        b.close()

if __name__ == '__main__':
    main()
