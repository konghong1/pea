"""Verify both bug fixes after rebuild:

  FIX #1: crop image visual size == containerRef visual size (do NOT 2x inflated)
          by writing cropImgStage's inline width/height as flow coordinate
          (= visual px ÷ zoom), so ReactFlow's transform: scale(zoom) cancels.

  FIX #2: while crop overlay is open, canvas pan/zoom is locked
          (no wheel zoom should change ReactFlow viewport).
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
            page.fill('input[placeholder="you@pea.ai"]', f'fix_{ts}@pea.dev')
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

        # Capture viewport zoom + flow viewport transform for reference
        canvas_state = page.evaluate('''() => {
            const v = window.__canvas?.getState?.()?.viewport;
            const t = window.__rfViewportTransform; // expose if available
            const flowView = document.querySelector('.react-flow__viewport');
            const ft = flowView ? getComputedStyle(flowView).transform : null;
            return { vp: v, flowTransform: ft };
        }''')
        print(f'[before crop] canvas state: {canvas_state}')

        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1500)

        # ── FIX #1: cropImgStage visual size must equal imageWrap visual size ──
        m1 = page.evaluate('''() => {
            function rectOf(sel) {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { w: Math.round(r.width), h: Math.round(r.height) };
            }
            const wrap = document.querySelector('.pea-node-result-image-wrap');
            const stage = document.querySelector('.pea-crop-image-stage');
            const overlay = document.querySelector('.pea-crop-overlay');
            const flowView = document.querySelector('.react-flow__viewport');
            const cs = getComputedStyle(flowView).transform;
            // parse "matrix(a, b, c, d, e, f)" or "matrix3d(...)"
            let zoom = 1;
            if (cs && cs !== 'none') {
                const m = cs.match(/matrix\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)/);
                if (m) zoom = parseFloat(m[1]);
                else {
                    const m3 = cs.match(/matrix3d\(([\d.\-\s,]+)\)/);
                    if (m3) zoom = parseFloat(m3[1].split(',')[0]);
                }
            }
            const wrapInline = wrap ? wrap.getBoundingClientRect() : null;
            const stageInline = stage ? stage.style.cssText : null;
            return {
                imgWrap:   rectOf('.pea-node-result-image-wrap'),
                cropOverlay: rectOf('.pea-crop-overlay'),
                cropCard:  rectOf('.pea-crop-stage'),
                cropImgStage: rectOf('.pea-crop-image-stage'),
                stageInlineStyle: stageInline,
                zoom: zoom,
                canvasLocked: !!document.querySelector('.pea-canvas-locked'),
            };
        }''')
        print('\n[FIX#1] crop dimensions:')
        for k, v in m1.items():
            print(f'  {k:18s} = {v}')

        ratio_v_visual = m1['cropImgStage']['h'] / max(1, m1['imgWrap']['h']) if m1['cropImgStage'] and m1['imgWrap'] else 0
        ratio_h_visual = m1['cropImgStage']['w'] / max(1, m1['imgWrap']['w']) if m1['cropImgStage'] and m1['imgWrap'] else 0
        visual_match = 0.95 <= ratio_h_visual <= 1.05 and 0.95 <= ratio_v_visual <= 1.05
        print(f'  → ratio (cropImgStage visual / imgWrap visual) = {ratio_h_visual:.2f}x{w_v_str(ratio_v_visual)}; match? {visual_match}')
        checks = []
        checks.append({
            'name': '[FIX#1] crop image visual size == imgWrap visual size (within 5%)',
            'pass': visual_match,
            'detail': f"wrap=({m1['imgWrap']['w']}x{m1['imgWrap']['h']}) stage=({m1['cropImgStage']['w']}x{m1['cropImgStage']['h']}) ratio=({ratio_h_visual:.2f},{ratio_v_visual:.2f})",
        })
        checks.append({
            'name': '[FIX#1] canvas has .pea-canvas-locked while crop open',
            'pass': m1['canvasLocked'],
            'detail': f"class present: {m1['canvasLocked']}",
        })

        # ── FIX #2: try to zoom canvas via wheel (any mouse position outside crop overlay) ──
        # We detect viewport change via the matrix transform on .react-flow__viewport.
        # This avoids depending on window.__canvas store, which doesn't expose reactflow viewport.
        def get_viewport_matrix():
            return page.evaluate('''() => {
                const fv = document.querySelector('.react-flow__viewport');
                if (!fv) return null;
                const cs = getComputedStyle(fv).transform;
                if (!cs || cs === 'none') return { scale: 1, x: 0, y: 0 };
                const m = cs.match(/matrix\\(([-\\d.]+),\\s*([-\\d.]+),\\s*([-\\d.]+),\\s*([-\\d.]+),\\s*([-\\d.]+),\\s*([-\\d.]+)\\)/);
                if (!m) return null;
                return { scale: parseFloat(m[1]), x: parseFloat(m[5]), y: parseFloat(m[6]) };
            }''')
        vp_before = get_viewport_matrix()
        # Far corner outside crop overlay & imgWrap — bottom-left
        page.mouse.move(20, VIEW_H - 20)
        # Plain wheel for pan (ReactFlow panOnScroll), Ctrl+wheel for zoom
        page.mouse.wheel(0, -300)
        page.wait_for_timeout(400)
        vp_after_pan = get_viewport_matrix()
        page.keyboard.down('Control')
        page.mouse.wheel(0, -300)
        page.wait_for_timeout(400)
        page.keyboard.up('Control')
        vp_after_ctrl = get_viewport_matrix()
        print(f'\n[FIX#2] viewport matrix:')
        print(f'  before={vp_before}')
        print(f'  after_plain_wheel={vp_after_pan}')
        print(f'  after_ctrl_wheel={vp_after_ctrl}')
        ctrl_zoom_changed = vp_after_ctrl and vp_before and abs(vp_after_ctrl['scale'] - vp_before['scale']) > 0.01
        plain_pan_changed = vp_after_pan and vp_before and (
            abs(vp_after_pan['x'] - vp_before['x']) > 1 or
            abs(vp_after_pan['y'] - vp_before['y']) > 1 or
            abs(vp_after_pan['scale'] - vp_before['scale']) > 0.01
        )
        checks.append({
            'name': '[FIX#2] Ctrl+wheel zoom is LOCKED in crop mode (matrix unchanged)',
            'pass': not ctrl_zoom_changed,
            'detail': f"before.scale={vp_before['scale'] if vp_before else None} after_ctrl.scale={vp_after_ctrl['scale'] if vp_after_ctrl else None}",
        })
        checks.append({
            'name': '[FIX#2] plain wheel pan is LOCKED in crop mode (matrix unchanged)',
            'pass': not plain_pan_changed,
            'detail': f"before=({vp_before['x']},{vp_before['y']}) after=({vp_after_pan['x']},{vp_after_pan['y']})",
        })

        page.screenshot(path='shots/crop_fix_v1.png', full_page=False)

        # ── Close crop and verify lock is released ──
        page.keyboard.press('Escape')
        page.wait_for_timeout(800)
        lock_after_close = page.evaluate('''() => !!document.querySelector('.pea-canvas-locked')''')
        checks.append({
            'name': '[FIX#2] canvas lock RELEASED on crop close',
            'pass': not lock_after_close,
            'detail': f"still locked: {lock_after_close}",
        })

        # And after close, ctrl+wheel SHOULD change scale now (lock released)
        vp_after_close = get_viewport_matrix()
        page.mouse.move(20, VIEW_H - 20)
        page.keyboard.down('Control')
        page.mouse.wheel(0, -200)
        page.keyboard.up('Control')
        page.wait_for_timeout(400)
        vp_after_close_ctrl = get_viewport_matrix()
        ok_unlocked = vp_after_close and vp_after_close_ctrl and abs(vp_after_close_ctrl['scale'] - vp_after_close['scale']) > 0.01
        checks.append({
            'name': '[FIX#2] ctrl+wheel works again after crop closes (scale changes)',
            'pass': ok_unlocked,
            'detail': f"scale before close={vp_after_close['scale']} after close+ctrl+wheel={vp_after_close_ctrl['scale']}",
        })

        print('\n=== FIX VERIFICATION RESULTS ===')
        all_pass = True
        for c in checks:
            ok = c['pass']
            all_pass = all_pass and ok
            mark = '✓' if ok else '✗'
            print(f'  [{mark}] {c["name"]}: {c.get("detail","")}')
        print(f'\nOverall: {"ALL PASS ✓" if all_pass else "SOME FAILED ✗"}')

        browser.close()
        return 0 if all_pass else 1


def w_v_str(r):
    return f'x{r:.2f}'

if __name__ == '__main__':
    sys.exit(main() or 0)
