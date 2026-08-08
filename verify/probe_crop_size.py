"""Probe ImageCropOverlay's actual display dimensions to find why crop image is too large.

Measures:
  - node pixel size on canvas (visible frame)
  - .pea-node-result-image-wrap actual pixel size (what containerRef points to)
  - .pea-crop-image-stage actual pixel size (what fitDisplay computed)
  - viewport size (window.innerWidth/innerHeight)
  - the image natural pixel size
  - tries wheel zoom to verify whether canvas is locked in crop mode
"""
from playwright.sync_api import sync_playwright
import os, time, sys

VIEW_W, VIEW_H = 1440, 900

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(800)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'probe_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'[login note] {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # Add image node + upload test image
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text='图片').first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2000)
        node.click()
        page.wait_for_timeout(400)

        # Record viewport before crop
        viewport_before = page.evaluate('''() => ({
            innerW: window.innerWidth,
            innerH: window.innerHeight,
            reactFlowZoom: window.__canvas?.getState()?.viewport?.zoom ?? null,
        })''')
        print(f'[before crop] viewport={viewport_before}')

        # Click crop
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1500)

        # Capture all the measurements
        info = page.evaluate('''() => {
            function rectOf(sel) {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) };
            }
            const node = document.querySelector('.react-flow__node');
            const nodeWrap = document.querySelector('.pea-node-result-image-wrap');
            const cropStage = document.querySelector('.pea-crop-image-stage');
            const cropOverlay = document.querySelector('.pea-crop-overlay');
            const cropCard = document.querySelector('.pea-crop-stage');
            const img = document.querySelector('.pea-crop-image');
            const nodeBody = document.querySelector('.pea-node-body-card');
            const nodeRect = node ? node.getBoundingClientRect() : null;
            return {
                viewport: { innerW: window.innerWidth, innerH: window.innerHeight },
                node:      rectOf('.react-flow__node'),
                bodyCard:  rectOf('.pea-node-body-card'),
                imgWrap:   rectOf('.pea-node-result-image-wrap'),
                cropOverlay: rectOf('.pea-crop-overlay'),
                cropCard:  rectOf('.pea-crop-stage'),
                cropImgStage: rectOf('.pea-crop-image-stage'),
                cropImg:   rectOf('.pea-crop-image'),
                imgNat: img ? { w: img.naturalWidth, h: img.naturalHeight } : null,
                zoom: window.__canvas?.getState()?.viewport?.zoom ?? null,
                cropActive: !!document.querySelector('.pea-canvas-locked'),
                lockClassExists: !!document.querySelector('.pea-canvas-locked'),
            };
        }''')
        print('=== CROP DIMENSIONS PROBE ===')
        for k, v in info.items():
            print(f'  {k:18s} = {v}')

        # Test wheel event to check if canvas is locked
        before_wheel = page.evaluate('''() => window.__canvas?.getState()?.viewport?.zoom''')
        # Try wheel inside the canvas (NOT on the crop overlay)
        flow_box = page.locator('.react-flow').first.bounding_box()
        # Wheel far from the crop overlay — at the very bottom-left
        page.mouse.move(flow_box['x'] + 30, flow_box['y'] + flow_box['height'] - 30)
        page.mouse.wheel(0, -300)  # ctrl+wheel would need keyboard; just plain wheel for pan
        page.wait_for_timeout(400)
        after_wheel = page.evaluate('''() => {
            const vp = window.__canvas?.getState()?.viewport;
            return vp ? { x: vp.x, y: vp.y, zoom: vp.zoom } : null;
        }''')
        print(f'\n[wheel probe] before zoom={before_wheel}, after=({after_wheel})')

        # Try ctrl+wheel (zoom in/out) - this should be blocked in crop mode
        page.keyboard.down('Control')
        page.mouse.wheel(0, -300)
        page.keyboard.up('Control')
        page.wait_for_timeout(400)
        after_ctrl = page.evaluate('''() => window.__canvas?.getState()?.viewport?.zoom''')
        print(f'\n[ctrl+wheel] zoom now={after_ctrl} (should match before if locked)')

        page.screenshot(path='shots/crop_probe.png', full_page=False)
        browser.close()
        return 0

if __name__ == '__main__':
    sys.exit(main() or 0)
