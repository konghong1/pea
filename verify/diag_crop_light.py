"""Diagnose crop white bug under LIGHT theme."""
import os, time, json
from playwright.sync_api import sync_playwright

JS = r"""
() => {
  const sel = ['.pea-crop-overlay','.pea-crop-image-stage',
    '.pea-crop-img-clip','.pea-crop-image','.pea-node-result-image-wrap'];
  const out = {};
  for (const s of sel) {
    const el = document.querySelector(s);
    if (!el) { out[s] = 'MISSING'; continue; }
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    out[s] = { bg: cs.backgroundColor, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)} };
  }
  // also check html theme class and body surface
  return {
    ...out,
    htmlClass: document.documentElement.className,
    bodySurface: document.body.dataset.surface || '(none)',
    canvasBg: getComputedStyle(document.querySelector('.react-flow__pane')||document.body).backgroundColor,
  };
}
"""

def main():
    here = os.path.dirname(__file__)
    shot_dir = os.path.join(here, 'shots')
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
            page.fill('input[placeholder="you@pea.ai"]', f'light_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'nav: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # Force LIGHT theme before entering canvas
        page.evaluate("""() => {
          document.documentElement.classList.remove('dark');
          document.documentElement.classList.add('light');
          console.log('forced light theme:', document.documentElement.className);
        }""")
        page.wait_for_timeout(500)

        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text="图片").first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = None
        for f in os.listdir(here):
            if f.startswith('test_crop') and f.endswith('.png'):
                src = os.path.join(here, f); break
        if not src:
            for f in os.listdir(here):
                if f.endswith('.png'): src = os.path.join(here, f); break
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2500)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1800)

        path = os.path.join(shot_dir, 'crop_diag_light.png')
        page.screenshot(path=path)
        data = page.evaluate(JS)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print(f'screenshot: {path}')
        b.close()

if __name__ == '__main__':
    main()
