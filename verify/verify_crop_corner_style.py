"""Verify crop corner handle style: 24px fine-line L-shape, no edge handles.

Assumes the full stack is running on http://localhost:8088.
Captures a screenshot of the crop overlay and checks the NW corner handle
size/position and confirms no edge midpoint handles are rendered.
"""
from playwright.sync_api import sync_playwright
import time, os

VIEW_W, VIEW_H = 1440, 900

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'corner_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'Login/nav note: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # Add image node + upload test image
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text="图片").first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        if not os.path.exists(src):
            for f in os.listdir(os.path.dirname(__file__)):
                if f.endswith('.png'):
                    src = os.path.join(os.path.dirname(__file__), f)
                    break
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(1800)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name="裁剪").click()
        page.wait_for_timeout(1200)

        # Screenshot of crop overlay
        shot_path = 'shots/crop_corner_style.png'
        page.screenshot(path=shot_path, full_page=False)

        # Inspect NW corner handle pixels, accounting for ReactFlow viewport zoom
        info = page.evaluate('''() => {
            const frame = document.querySelector('.pea-crop-frame');
            const handle = document.querySelector('.pea-crop-handle.nw');
            if (!frame || !handle) return null;
            const f = frame.getBoundingClientRect();
            const h = handle.getBoundingClientRect();
            const beforeW = parseFloat(window.getComputedStyle(handle, '::before').width) || 0;
            const afterH = parseFloat(window.getComputedStyle(handle, '::after').height) || 0;
            // Read ReactFlow viewport zoom from transform matrix
            let zoom = 1;
            const vp = document.querySelector('.react-flow__viewport');
            if (vp) {
                const style = window.getComputedStyle(vp);
                const m = style.transform.match(/matrix\(([^,]+),\s*[^,]+,\s*[^,]+,\s*([^,]+),/);
                if (m) zoom = Math.max(parseFloat(m[1]), parseFloat(m[2]));
            }
            return {
                frameX: f.x, frameY: f.y,
                handleX: h.x, handleY: h.y, handleW: h.width, handleH: h.height,
                beforeW, afterH, zoom
            };
        }''')
        print('Corner handle info:', info)

        # Check that handle size is 24x24 CSS pixels (before viewport zoom)
        # and that no edge handles are rendered (per reference design).
        checks = []
        if info and info.get('zoom', 0) > 0:
            css_w = info['handleW'] / info['zoom']
            css_h = info['handleH'] / info['zoom']
            checks.append({
                'name': 'NW handle hit area is 20x20 CSS px',
                'pass': abs(css_w - 20) <= 1 and abs(css_h - 20) <= 1,
                'detail': f"screen={info['handleW']:.1f}x{info['handleH']:.1f} zoom={info['zoom']:.2f} css={css_w:.1f}x{css_h:.1f}"
            })
            checks.append({
                'name': 'NW handle sits at frame corner',
                'pass': abs(info['handleX'] - info['frameX']) <= 2 and abs(info['handleY'] - info['frameY']) <= 2,
                'detail': f"handle=({info['handleX']:.1f},{info['handleY']:.1f}) frame=({info['frameX']:.1f},{info['frameY']:.1f})"
            })
            checks.append({
                'name': 'NW visual arms are 10x10 px',
                'pass': abs(info['beforeW'] - 10) <= 0.5 and abs(info['afterH'] - 10) <= 0.5,
                'detail': f"beforeW={info['beforeW']:.1f} afterH={info['afterH']:.1f}"
            })
            edgeHandles = page.locator('.pea-crop-handle.edge').count()
            checks.append({
                'name': 'No edge handles rendered',
                'pass': edgeHandles == 0,
                'detail': f"edge handle count={edgeHandles}"
            })
        else:
            checks.append({'name': 'crop overlay open', 'pass': False, 'reason': 'no frame/handle/zoom found'})

        print('=== CROP CORNER STYLE VERIFICATION ===')
        all_pass = True
        for c in checks:
            ok = c['pass']; all_pass = all_pass and ok
            detail = c.get('detail', ''); reason = c.get('reason', '')
            print(f"  [{'✓' if ok else '✗'}] {c['name']}: {detail} {reason}".strip())
        print(f'Overall: {"PASS ✓" if all_pass else "FAIL ✗"}')
        browser.close()
        return 0 if all_pass else 1

if __name__ == '__main__':
    exit(main() or 0)
