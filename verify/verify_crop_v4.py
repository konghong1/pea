"""Verify crop UI after fix v4: overflow visible + no CSS/TSX positioning conflict."""
from playwright.sync_api import sync_playwright
import time, json

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'v4_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'Login/nav error: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text="图片").first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        node.locator("input[type='file']").set_input_files('verify/test_crop_source.png')
        page.wait_for_timeout(1500)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name="裁剪").click()
        page.wait_for_timeout(1500)

        # Screenshot
        page.screenshot(path='verify/shots/crop_fixed_v4.png', full_page=False)

        # Diagnostics via JS (written to avoid bash ${} conflicts)
        diag = page.evaluate('''() => {
            const result = { checks: [] };
            const overlay = document.querySelector('.pea-crop-overlay-inline');
            const frame = document.querySelector('.pea-crop-frame');
            const toolbar = document.querySelector('.pea-crop-toolbar-inline');
            const masks = document.querySelectorAll('.pea-crop-mask');
            const handles = document.querySelectorAll('.pea-crop-handle');

            if (!overlay) { result.checks.push({name:'overlay', pass:false, reason:'MISSING'}); return result; }
            result.checks.push({name:'overlay exists', pass:true});

            var oRect = overlay.getBoundingClientRect();
            result.overlaySize = Math.round(oRect.width) + 'x' + Math.round(oRect.height);

            if (frame) {
                var fRect = frame.getBoundingClientRect();
                var expectedX = oRect.x + (oRect.width - fRect.width) / 2;
                var expectedY = oRect.y + (oRect.height - fRect.height) / 2;
                var dx = Math.abs(fRect.x - expectedX);
                var dy = Math.abs(fRect.y - expectedY);
                var centered = dx < 10 && dy < 10;
                result.checks.push({name:'crop frame centered', pass:centered, detail:'offset=(' + Math.round(dx) + ',' + Math.round(dy) + ')px'});
                result.checks.push({name:'crop frame size', pass: fRect.width > 100 && fRect.height > 100, detail:'' + Math.round(fRect.width) + 'x' + Math.round(fRect.height)});
            } else {
                result.checks.push({name:'frame', pass:false, reason:'MISSING'});
            }

            if (toolbar) {
                var tRect = toolbar.getBoundingClientRect();
                var visible = tRect.width > 50 && tRect.height > 30;
                result.checks.push({name:'toolbar visible', pass:visible, detail:'' + Math.round(tRect.width) + 'x' + Math.round(tRect.height) + ' @ (' + Math.round(tRect.x) + ',' + Math.round(tRect.y) + ')'});

                var belowOverlay = tRect.y >= (oRect.y + oRect.height - 20);
                result.checks.push({name:'toolbar below overlay', pass:belowOverlay, detail:'overlay_bottom=' + Math.round(oRect.y+oRect.height) + ' toolbar_top=' + Math.round(tRect.y)});
            } else {
                result.checks.push({name:'toolbar', pass:false, reason:'MISSING'});
            }

            result.checks.push({name:'masks x4', pass:masks.length === 4, detail:'' + masks.length});
            result.checks.push({name:'handles x4', pass:handles.length === 4, detail:'' + handles.length});

            var nodeEl = overlay.closest('.pea-node');
            if (nodeEl) {
                var bc = nodeEl.querySelector('.pea-node-body-card');
                if (bc) {
                    var ov = getComputedStyle(bc).overflow;
                    result.checks.push({name:'bodyCard overflow=visible', pass:ov==='visible', detail:ov});
                }
            }

            return result;
        }''')

        print('=== VERIFICATION RESULTS ===')
        all_pass = True
        for c in diag['checks']:
            status = 'PASS' if c['pass'] else 'FAIL'
            detail = c.get('detail', '')
            reason = c.get('reason', '')
            line = f"  [{'✓' if c['pass'] else '✗'}] {c['name']}: {detail} {reason}".strip()
            print(line)
            if not c['pass']:
                all_pass = False

        print(f'\nOverlay size: {diag.get("overlaySize", "?")}')
        print(f'\nOverall: {"ALL PASS ✓" if all_pass else "SOME FAILED ✗"}')
        browser.close()
        return 0 if all_pass else 1

if __name__ == '__main__':
    exit(main() or 0)
