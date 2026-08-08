"""Sanity check: at canvas zoom=1.0 (default fitView), crop should fit naturally."""
from playwright.sync_api import sync_playwright
import os, time, sys, re

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
            page.fill('input[placeholder="you@pea.ai"]', f'crop_z1_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'[login note] {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)
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

        # Just observe default zoom (do NOT try to manipulate it; canvas may auto-fit).
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text='图片').first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2500)  # let fitView settle
        node.click()
        page.wait_for_timeout(400)

        # Read zoom BEFORE opening crop
        z_before = page.evaluate(r'''() => {
            const cs = getComputedStyle(document.querySelector('.react-flow__viewport')).transform;
            const m = cs.match(/matrix\(([-\d.]+),/);
            return parseFloat(m[1]);
        }''')
        print(f'  canvas zoom before crop: {z_before:.3f}')

        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1200)

        info = page.evaluate(r'''() => {
            function rectOf(sel) {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { w: Math.round(r.width), h: Math.round(r.height) };
            }
            const fv = document.querySelector('.react-flow__viewport');
            const cs = getComputedStyle(fv).transform;
            const m = cs.match(/matrix\(([-\d.]+),/);
            const stage = document.querySelector('.pea-crop-image-stage');
            return {
                scale: parseFloat(m[1]),
                imgWrap: rectOf('.pea-node-result-image-wrap'),
                cropImgStage: rectOf('.pea-crop-image-stage'),
                stageInline: stage?.style?.cssText ?? null,
                canvasLocked: !!document.querySelector('.pea-canvas-locked'),
            };
        }''')
        print(f'\n  info: {info}')

        wrap = info['imgWrap']
        stage = info['cropImgStage']
        scale = info['scale']
        ok_size = abs(stage['w'] - wrap['w']) <= 4 and abs(stage['h'] - wrap['h']) <= 4
        inline_w = int(re.search(r'width:\s*(\d+)', info['stageInline']).group(1))
        inline_h = int(re.search(r'height:\s*(\d+)', info['stageInline']).group(1))
        # Inline should = visual / scale (flow coordinate) — this is the key invariant
        expected_inline_w = round(stage['w'] / scale)
        expected_inline_h = round(stage['h'] / scale)
        ok_inline = abs(inline_w - expected_inline_w) <= 1 and abs(inline_h - expected_inline_h) <= 1
        ok_locked = info['canvasLocked']

        checks = [
            {'name': f'[zoom={scale:.2f}] visual stage == visual wrap', 'pass': ok_size,
             'detail': f"wrap=({wrap['w']}x{wrap['h']}) stage=({stage['w']}x{stage['h']})"},
            {'name': f'[zoom={scale:.2f}] inline = visual / zoom (flow coord cancels ReactFlow transform)',
             'pass': ok_inline,
             'detail': f"expected=({expected_inline_w}x{expected_inline_h}) got=({inline_w}x{inline_h})"},
            {'name': f'[zoom={scale:.2f}] canvas locked during crop', 'pass': ok_locked, 'detail': f"locked: {ok_locked}"},
        ]


        page.screenshot(path='shots/crop_fix_zoom_1.00.png', full_page=False)
        page.keyboard.press('Escape')

        all_pass = all(c['pass'] for c in checks)
        for c in checks:
            mark = '✓' if c['pass'] else '✗'
            print(f"  [{mark}] {c['name']}: {c.get('detail','')}")
        print(f'Result: {"PASS" if all_pass else "FAIL"}')

        browser.close()
        return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main() or 0)
