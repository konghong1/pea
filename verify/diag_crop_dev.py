"""Reproduce crop flow on the user's DEV server (5173) and dump the real
crop <img> render state + screenshot, to verify whether the white bug exists."""
import os, time, json
from playwright.sync_api import sync_playwright

JS = r"""
() => {
  const sel = ['.pea-crop-overlay','.pea-crop-img-clip','.pea-crop-image','.pea-node-result-image-wrap'];
  const out = {};
  for (const s of sel) {
    const el = document.querySelector(s);
    if (!el) { out[s] = 'MISSING'; continue; }
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    out[s] = {
      tag: el.tagName, bg: cs.backgroundColor, z: cs.zIndex,
      rect: {w:Math.round(r.width), h:Math.round(r.height)},
    };
  }
  const img = document.querySelector('.pea-crop-image');
  if (img) {
    out['__crop_img_state'] = {
      complete: img.complete,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      currentSrc: (img.currentSrc||'').slice(0,60),
      srcAttr: (img.getAttribute('src')||'').slice(0,60),
    };
  }
  const orig = document.querySelector('.pea-node-media-preview');
  if (orig) out['__orig_img_state'] = { complete: orig.complete, naturalWidth: orig.naturalWidth };
  return out;
}
"""

def main():
    here = os.path.dirname(__file__)
    shot_dir = os.path.join(here, 'shots')
    os.makedirs(shot_dir, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel='chrome')
        page = b.new_page(viewport={'width': 1440, 'height': 900})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:5173', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'diag_{ts}@pea.dev')
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
        src = os.path.join(here, 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2500)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1800)
        page.screenshot(path=os.path.join(shot_dir, 'crop_diag_dev.png'))
        data = page.evaluate(JS)
        print('=== DOM DIAG (5173) ===')
        print(json.dumps(data, indent=2, ensure_ascii=False))
        b.close()

if __name__ == '__main__':
    main()
