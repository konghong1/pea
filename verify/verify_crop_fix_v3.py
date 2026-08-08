"""Comprehensive crop verification v2 (2026-08-08):
1. Crop image visual == node image (no "two-images" perception)
2. Mask is OPAQUE (no underlying image showing through)
3. Stage fits wrap (no overflow)
4. Toolbar absolute overlay at bottom (no flex pushing)
5. Click outside frame does NOT cancel crop
6. Original <img> is hidden (visibility:hidden)
"""
from playwright.sync_api import sync_playwright
import os, time

VIEW_W, VIEW_H = 1440, 900

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel='chrome')
        page = b.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'cropv2_{ts}@pea.dev')
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
        # Use a wider image to have more aspect-ratio mismatch (more obvious two-images perception)
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

        checks = []

        # ── TEST 1: NO DOUBLE IMAGE — original <img> should be hidden ──
        info = page.evaluate(r'''() => {
            const orig = document.querySelector('.pea-node-result-preview');
            const stage = document.querySelector('.pea-crop-stage');
            const imgStage = document.querySelector('.pea-crop-image-stage');
            const cropImg = document.querySelector('.pea-crop-image');
            const mask = document.querySelector('.pea-crop-mask');
            const frame = document.querySelector('.pea-crop-frame');
            const toolbar = document.querySelector('.pea-crop-toolbar');
            const wrap = document.querySelector('.pea-node-result-image-wrap');
            function box(el) {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { x: Math.round(r.x), y: Math.round(r.y),
                         w: Math.round(r.width), h: Math.round(r.height),
                         right: Math.round(r.right), bottom: Math.round(r.bottom) };
            }
            function cs(el, props) {
                if (!el) return null;
                const s = getComputedStyle(el);
                const out = {};
                for (const p of props) out[p] = s[p];
                return out;
            }
            return {
                orig: { box: box(orig), cs: cs(orig, ['visibility', 'display', 'opacity']) },
                stage: { box: box(stage), cs: cs(stage, ['visibility', 'display', 'overflow']) },
                imgStage: { box: box(imgStage), cs: cs(imgStage, ['visibility', 'display', 'overflow', 'position']) },
                cropImg: { box: box(cropImg) },
                mask: { box: box(mask), cs: cs(mask, ['backgroundColor']) },
                frame: { box: box(frame) },
                toolbar: { box: box(toolbar), cs: cs(toolbar, ['position', 'bottom']) },
                wrap: { box: box(wrap) },
            };
        }''')

        print('\n=== State during crop ===')
        for k, v in info.items():
            print(f'  {k}: {v}')

        orig_hidden = info['orig']['cs']['visibility'] == 'hidden'
        checks.append({
            'name': '[1] original <img> is visibility:hidden',
            'pass': orig_hidden,
            'detail': f"visibility={info['orig']['cs']['visibility']}",
        })

        # ── TEST 2: STAGE FITS WITHIN WRAP (no overflow) ──
        stage_in_wrap = (
            info['stage']['box']['x'] >= info['wrap']['box']['x'] - 2 and
            info['stage']['box']['y'] >= info['wrap']['box']['y'] - 2 and
            info['stage']['box']['right'] <= info['wrap']['box']['right'] + 2 and
            info['stage']['box']['bottom'] <= info['wrap']['box']['bottom'] + 2
        )
        checks.append({
            'name': '[2] crop stage fits within wrap (no overflow)',
            'pass': stage_in_wrap,
            'detail': f"wrap={info['wrap']['box']} stage={info['stage']['box']}",
        })

        # ── TEST 3: IMAGE-STAGE FITS WITHIN STAGE (no overflow) ──
        imageStage_in_stage = (
            info['imgStage']['box']['x'] >= info['stage']['box']['x'] - 2 and
            info['imgStage']['box']['y'] >= info['stage']['box']['y'] - 2 and
            info['imgStage']['box']['right'] <= info['stage']['box']['right'] + 2 and
            info['imgStage']['box']['bottom'] <= info['stage']['box']['bottom'] + 2
        )
        checks.append({
            'name': '[3] image stage fits within stage',
            'pass': imageStage_in_stage,
            'detail': f"stage={info['stage']['box']} imgStage={info['imgStage']['box']}",
        })

        # ── TEST 4: MASK IS OPAQUE (background alpha ≥ 0.9) ──
        mask_bg = info['mask']['cs']['backgroundColor']
        # Parse "rgba(0, 0, 0, 0.96)" → check alpha >= 0.9
        import re
        m = re.match(r'rgba?\(([^)]+)\)', mask_bg)
        if m:
            parts = [p.strip() for p in m.group(1).split(',')]
            alpha = float(parts[3]) if len(parts) >= 4 else 1.0
        else:
            alpha = 1.0
        checks.append({
            'name': '[4] mask is OPAQUE (alpha ≥ 0.9, fixes two-images illusion)',
            'pass': alpha >= 0.9,
            'detail': f"background={mask_bg}, parsed alpha={alpha}",
        })

        # ── TEST 5: TOOLBAR IS ABSOLUTE OVERLAY (doesn't push stage) ──
        toolbar_pos = info['toolbar']['cs']['position']
        toolbar_abs = toolbar_pos == 'absolute'
        # Toolbar at bottom of image stage
        toolbar_at_bottom = (
            info['toolbar']['box']['bottom'] >= info['imgStage']['box']['bottom'] - 30
        )
        checks.append({
            'name': '[5] toolbar is absolute overlay at bottom (not pushing stage)',
            'pass': toolbar_abs and toolbar_at_bottom,
            'detail': f"position={toolbar_pos}, toolbar.bottom={info['toolbar']['box']['bottom']} imgStage.bottom={info['imgStage']['box']['bottom']}",
        })

        page.screenshot(path='shots/crop_v3_default.png', full_page=False)
        print('\n  screenshot: shots/crop_v3_default.png')

        # ── TEST 6: Click outside frame, crop stays open ──
        # Click in mask area (above frame)
        cy = info['frame']['box']['y'] - 20
        cx = info['imgStage']['box']['x'] + info['imgStage']['box']['w'] / 2
        before_open = page.evaluate('''() => !!document.querySelector('.pea-crop-overlay')''')
        page.mouse.click(cx, cy)
        page.wait_for_timeout(600)
        after_open = page.evaluate('''() => !!document.querySelector('.pea-crop-overlay')''')
        checks.append({
            'name': '[6] click on mask (outside frame) does NOT close crop',
            'pass': before_open and after_open,
            'detail': f"before={before_open}, click=({cx:.0f},{cy:.0f}), after={after_open}",
        })

        # ── TEST 7: Click on toolbar X still closes ──
        # Find × button
        x_btn_box = page.evaluate(r'''() => {
            const btns = document.querySelectorAll('.pea-crop-toolbar-btn');
            for (const b of btns) {
                if (b.title === '取消' || b.getAttribute('aria-label') === '取消裁剪') {
                    const r = b.getBoundingClientRect();
                    return { x: r.x, y: r.y, w: r.width, h: r.height };
                }
            }
            return null;
        }''')
        if x_btn_box:
            page.mouse.click(x_btn_box['x'] + x_btn_box['w']/2, x_btn_box['y'] + x_btn_box['h']/2)
            page.wait_for_timeout(600)
            after_x = page.evaluate('''() => !!document.querySelector('.pea-crop-overlay')''')
            checks.append({
                'name': '[7] click on × close button DOES close crop',
                'pass': not after_x,
                'detail': f"click=({x_btn_box['x']:.0f},{x_btn_box['y']:.0f}), after={after_x}",
            })

        # Print results
        print('\n=== RESULTS ===')
        n_pass = sum(1 for c in checks if c['pass'])
        for c in checks:
            mark = '✓' if c['pass'] else '✗'
            print(f"  [{mark}] {c['name']}: {c.get('detail','')}")
        print(f"\n  {n_pass}/{len(checks)} PASS")

        b.close()
        return 0 if n_pass == len(checks) else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
