"""Comprehensive crop-fix verification across multiple zoom levels.

Tests that crop image visual size matches imageWrap visual size at zoom levels
0.5, 1.0, 1.5, 2.0, and verifies canvas lock during crop.
"""
from playwright.sync_api import sync_playwright
import os, time, sys

VIEW_W, VIEW_H = 1440, 900

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.on('pageerror', lambda err: print(f'[pageerror] {err}'))

        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(800)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'fix2_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'[login note] {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # Add image node + upload
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

        # Read & expose rf viewport transform
        def get_viewport_matrix():
            return page.evaluate(r'''() => {
                const fv = document.querySelector('.react-flow__viewport');
                if (!fv) return null;
                const cs = getComputedStyle(fv).transform;
                if (!cs || cs === 'none') return { scale: 1, x: 0, y: 0 };
                const m = cs.match(/matrix\(([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)/);
                if (!m) return null;
                return { scale: parseFloat(m[1]), x: parseFloat(m[5]), y: parseFloat(m[6]) };
            }''')

        def set_viewport(scale, x, y):
            """Manipulate viewport via dispatchEvent on rf__set-viewport event / public api.
            Since we don't have access to useReactFlow, use the simpler 'wheel zoom' approach:
            press Ctrl and scroll to adjust zoom, then probe again."""
            # Easier: directly modify the transform via __rfViewportTransform or zoom keys.
            # ReactFlow listens to keyboard '=', '+', '-', '0' for defaultKeyCodes.
            # Use the public CanvasEditor's wheel-zoom via mouse.
            pass  # we'll use wheel events to set zoom

        # Probe at default zoom
        def get_layout_scale():
            """Compute the 'flow-coord to visual-px' multiplier by comparing
            .pea-node visual size with --pea-node-width inline style."""
            return page.evaluate(r'''() => {
                const node = document.querySelector('.react-flow__node.pea');
                if (!node) return null;
                const r = node.getBoundingClientRect();
                const styleW = parseFloat(node.style.getPropertyValue('--pea-node-width')) || 340;
                return { visualW: Math.round(r.width), flowW: styleW, ratio: r.width / styleW };
            }''')

        def run_at_zoom(target_scale):
            """Open crop at given canvas zoom and measure."""
            # Adjust zoom by Ctrl+wheel until target reached
            cur = get_viewport_matrix()
            cur_scale = cur['scale'] if cur else 1
            # Move to bottom-left to avoid crop overlay if open
            page.mouse.move(20, VIEW_H - 20)
            page.keyboard.down('Control')
            for _ in range(60):
                cur = get_viewport_matrix()
                cur_scale = cur['scale'] if cur else 1
                if abs(cur_scale - target_scale) < 0.02:
                    break
                if cur_scale < target_scale:
                    page.mouse.wheel(0, -100)
                else:
                    page.mouse.wheel(0, 100)
                page.wait_for_timeout(80)
            page.keyboard.up('Control')
            page.wait_for_timeout(400)
            cur = get_viewport_matrix()
            return cur['scale']

        checks = []
        for target_zoom in [0.5, 1.0, 1.5, 2.0]:
            print(f'\n── TARGET zoom = {target_zoom} ──')
            actual = run_at_zoom(target_zoom)
            print(f'  achieved zoom = {actual:.3f}')
            # Now click crop
            page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
            page.wait_for_timeout(1200)

            m = page.evaluate(r'''() => {
                function rectOf(sel) {
                    const el = document.querySelector(sel);
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return { w: Math.round(r.width), h: Math.round(r.height) };
                }
                return {
                    imgWrap:     rectOf('.pea-node-result-image-wrap'),
                    cropOverlay: rectOf('.pea-crop-overlay'),
                    cropCard:    rectOf('.pea-crop-stage'),
                    cropImgStage:rectOf('.pea-crop-image-stage'),
                    stageInline: document.querySelector('.pea-crop-image-stage')?.style?.cssText ?? null,
                    canvasLocked: !!document.querySelector('.pea-canvas-locked'),
                };
            }''')
            print(f'  measurements: {m}')
            wrap = m['imgWrap']
            stage = m['cropImgStage']
            if not wrap or not stage:
                checks.append({'name': f'[zoom={actual:.2f}] dimensions measurable', 'pass': False, 'detail': 'selectors missing'})
            else:
                ratio_h = stage['w'] / wrap['w']
                ratio_v = stage['h'] / wrap['h']
                match = 0.95 <= ratio_h <= 1.05 and 0.95 <= ratio_v <= 1.05
                checks.append({
                    'name': f'[zoom={actual:.2f}] cropImgStage visual == imgWrap visual (within 5%)',
                    'pass': match,
                    'detail': f"wrap=({wrap['w']}x{wrap['h']}) stage=({stage['w']}x{stage['h']}) ratio=({ratio_h:.2f},{ratio_v:.2f})",
                })
            checks.append({
                'name': f'[zoom={actual:.2f}] canvas has .pea-canvas-locked during crop',
                'pass': m['canvasLocked'],
                'detail': f"class present: {m['canvasLocked']}",
            })
            page.screenshot(path=f'shots/crop_fix_zoom_{actual:.2f}.png', full_page=False)
            # Close
            page.keyboard.press('Escape')
            page.wait_for_timeout(700)

        print('\n=== VERIFY RESULTS ===')
        all_pass = True
        for c in checks:
            ok = c['pass']
            all_pass = all_pass and ok
            mark = '✓' if ok else '✗'
            print(f"  [{mark}] {c['name']}: {c.get('detail','')}")
        print(f'\nOverall: {"ALL PASS ✓" if all_pass else "SOME FAILED ✗"}')

        browser.close()
        return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main() or 0)
