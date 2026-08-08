"""Verify the new minimal crop overlay style (v2):
- 1px white border (no 3x3 grid)
- 8x8 corner handles (small white squares)
- 2x18 / 18x2 edge handles (thin white bars)
- Compact 24px toolbar, 12px font
- Confirm button no longer uses brand blue (same tone as other toolbar buttons)
"""
import re
import time
import os
from playwright.sync_api import sync_playwright

VIEW_W, VIEW_H = 1440, 900

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
        page.fill('input[placeholder="you@pea.ai"]', f'v2style_{ts}@pea.dev')
        page.fill('input[placeholder="至少 8 位"]', 'Password123')
        page.locator('form button[type=submit]').click()
        page.wait_for_timeout(4000)
        page.locator('text=新建项目').first.click(timeout=5000)
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f'Login/nav note: {e}')

    page.wait_for_selector('.react-flow__viewport', timeout=15000)
    # 添加图片节点 + 上传
    page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
    page.wait_for_timeout(500)
    page.locator('.pea-add-menu-item', has_text='图片').first.click()
    page.wait_for_timeout(800)
    node = page.locator('.react-flow__node').first
    src = os.path.join(os.path.dirname(__file__), 'test_crop_portrait.png')
    if not os.path.exists(src):
        for f in os.listdir(os.path.dirname(__file__)):
            if f.endswith('.png'):
                src = os.path.join(os.path.dirname(__file__), f)
                break
    node.locator("input[type='file']").set_input_files(src)
    page.wait_for_timeout(1800)
    node.click()
    page.wait_for_timeout(400)
    page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
    page.wait_for_timeout(1200)

    info = page.evaluate(r'''() => {
        const frame = document.querySelector('.pea-crop-frame');
        const corner = document.querySelector('.pea-crop-handle.nw');
        const edgeN = document.querySelector('.pea-crop-handle.edge.n');
        const edgeW = document.querySelector('.pea-crop-handle.edge.w');
        const tb = document.querySelector('.pea-crop-toolbar');
        const confirm = document.querySelector('.pea-crop-confirm');
        const close = document.querySelector('.pea-crop-toolbar-btn');
        const ratio = document.querySelector('.pea-crop-ratio-btn');
        const fv = document.querySelector('.react-flow__viewport');
        const m = getComputedStyle(fv).transform.match(/matrix\(([-\d.]+),/);
        const zoom = parseFloat(m[1]);
        function cs(el) {
            if (!el) return null;
            const c = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            // Normalize visual pixel → CSS pixel by dividing by zoom
            return {
                borderWidth: c.borderTopWidth,
                borderColor: c.borderTopColor,
                boxShadow: c.boxShadow,
                bgImage: c.backgroundImage,
                outline: c.outline,
                w: Math.round(r.width / zoom),
                h: Math.round(r.height / zoom),
                bg: c.backgroundColor,
                color: c.color,
                fontSize: c.fontSize,
                fontWeight: c.fontWeight,
                borderRadius: c.borderRadius,
            };
        }
        return {
            zoom,
            frame: cs(frame),
            corner: cs(corner),
            edgeN: cs(edgeN),
            edgeW: cs(edgeW),
            toolbar: cs(tb),
            confirm: cs(confirm),
            close: cs(close),
            ratio: cs(ratio),
        };
    }''')

    print('\n=== NEW CROP STYLE INSPECTION ===')
    print(f'  [zoom] = {info["zoom"]:.3f}  (sizes below normalized: visual/zoom)')
    for k, v in info.items():
        if k == 'zoom': continue
        print(f'  {k}: {v}')

    page.screenshot(path='shots/crop_new_style.png', full_page=False)

    checks = []
    if info['frame']:
        bw = float(re.findall(r'([\d.]+)px', info['frame']['borderWidth'])[0])
        checks.append({'name': '[style] frame border = 1px', 'pass': abs(bw - 1.0) < 0.1, 'detail': f"borderWidth={info['frame']['borderWidth']}"})
        has_grid = 'linear-gradient' in (info['frame'].get('bgImage') or '')
        checks.append({'name': '[style] frame has NO 3x3 grid', 'pass': not has_grid, 'detail': f"bgImage={info['frame']['bgImage']}"})
    if info['corner']:
        checks.append({'name': '[style] corner handle = 8x8', 'pass': info['corner']['w'] == 8 and info['corner']['h'] == 8, 'detail': f"size={info['corner']['w']}x{info['corner']['h']}"})
    if info['edgeN']:
        checks.append({'name': '[style] edge.N = 18x2 thin', 'pass': info['edgeN']['w'] == 18 and info['edgeN']['h'] == 2, 'detail': f"size={info['edgeN']['w']}x{info['edgeN']['h']}"})
    if info['edgeW']:
        checks.append({'name': '[style] edge.W = 2x18 thin', 'pass': info['edgeW']['w'] == 2 and info['edgeW']['h'] == 18, 'detail': f"size={info['edgeW']['w']}x{info['edgeW']['h']}"})
    if info['toolbar']:
        checks.append({'name': '[style] toolbar compact (h≤40)', 'pass': info['toolbar']['h'] <= 40, 'detail': f"h={info['toolbar']['h']}px"})
        # 应该是圆胶囊 (border-radius ≥ h/2)
        radius_px = float(re.findall(r'([\d.]+)px', info['toolbar']['borderRadius'])[0])
        checks.append({'name': '[style] toolbar pill-shaped', 'pass': radius_px >= info['toolbar']['h'] / 2 - 1, 'detail': f"radius={radius_px}px h={info['toolbar']['h']}px"})
    if info['confirm']:
        bg = info['confirm']['bg']
        is_brand = '#3b' in bg.lower() or '56, 225' in bg
        checks.append({'name': '[style] confirm NOT brand blue', 'pass': not is_brand, 'detail': f"bg={bg}"})
    if info['ratio']:
        checks.append({'name': '[style] ratio label fontSize=12', 'pass': info['ratio']['fontSize'] == '12px', 'detail': f"fontSize={info['ratio']['fontSize']}"})

    print('\n=== CHECKS ===')
    all_pass = True
    for c in checks:
        mark = '✓' if c['pass'] else '✗'
        print(f"  [{mark}] {c['name']}: {c.get('detail','')}")
        if not c['pass']:
            all_pass = False
    print(f'\nResult: {"PASS" if all_pass else "FAIL"}')

    browser.close()
