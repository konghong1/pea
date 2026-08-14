"""Real-browser verify: enter crop mode, capture static + dragging frame,
dump crop-handle computed positions to confirm handles sit OUTSIDE the frame."""
import os, time, json
from playwright.sync_api import sync_playwright

def main():
    here = os.path.dirname(__file__)
    shot = os.path.join(here, 'shots')
    os.makedirs(shot, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel='chrome')
        page = b.new_page(viewport={'width': 1440, 'height': 900})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks","1"); }')
        page.goto('http://localhost:5173', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'shot_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print('nav:', e)
        page.wait_for_selector('.react-flow__viewport', timeout=15000)
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text="图片").first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(here, 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2500)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1800)

        page.screenshot(path=os.path.join(shot, 'crop_static.png'))

        js = r"""
        () => {
          const out = {};
          const sel = ['.pea-crop-frame',
            '.pea-crop-handle.nw','.pea-crop-handle.ne','.pea-crop-handle.sw','.pea-crop-handle.se',
            '.pea-crop-handle.edge.n','.pea-crop-handle.edge.s','.pea-crop-handle.edge.w','.pea-crop-handle.edge.e'];
          sel.forEach(s => {
            const el = document.querySelector(s);
            if (!el) { out[s] = 'MISSING'; return; }
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            out[s] = { w: Math.round(r.width), h: Math.round(r.height),
              top: Math.round(r.top), left: Math.round(r.left), bottom: Math.round(r.bottom), right: Math.round(r.right),
              bw: cs.borderTopWidth+'/'+cs.borderLeftWidth+'/'+cs.borderBottomWidth+'/'+cs.borderRightWidth,
              bc: cs.borderTopColor };
          });
          return out;
        }
        """
        print('=== HANDLE POSITIONS (5173) ===')
        print(json.dumps(page.evaluate(js), indent=2, ensure_ascii=False))

        # dragging state: grab frame center, move, screenshot mid-drag
        fb = page.locator('.pea-crop-frame').first.bounding_box()
        if fb:
            cx = fb['x'] + fb['width']/2
            cy = fb['y'] + fb['height']/2
            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx + 45, cy + 35, steps=10)
            page.wait_for_timeout(350)
            page.screenshot(path=os.path.join(shot, 'crop_dragging.png'))
            page.mouse.up()
        b.close()

if __name__ == '__main__':
    main()
