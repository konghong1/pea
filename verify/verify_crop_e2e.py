"""End-to-end interactive test: confirm button works, ratio dropdown works."""
from playwright.sync_api import sync_playwright
import os, time, re

def main():
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
            page.fill('input[placeholder="you@pea.ai"]', f'v3e2e_{ts}@pea.dev')
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

        # ── T1: ratio dropdown opens and shows options ──
        ratio_btn = page.locator('.pea-crop-ratio-btn')
        if ratio_btn.count() > 0:
            box = ratio_btn.bounding_box()
            page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            page.wait_for_timeout(500)
            opened = page.evaluate('''() => !!document.querySelector('.ant-dropdown-menu')''')
            checks.append({'name': 'ratio dropdown opens on click', 'pass': opened, 'detail': f'menu open: {opened}'})

            if opened:
                # try to click 16:9
                opt = page.locator('.ant-dropdown-menu-item', has_text='16 : 9')
                if opt.count() > 0:
                    opt.first.click()
                    page.wait_for_timeout(700)
                    # Confirm ratio applied by reading the button label
                    label = page.evaluate('''() => document.querySelector(".pea-crop-ratio-label")?.textContent?.trim()''')
                    checks.append({'name': '16:9 selection applies', 'pass': '16 : 9' in label, 'detail': f'label after click: {label}'})

        page.screenshot(path='shots/crop_v3e2e_after_ratio.png')

        # ── T2: × button closes crop ──
        x_btn = page.locator('.pea-crop-toolbar-btn').first
        x_box = x_btn.bounding_box()
        page.mouse.click(x_box['x'] + x_box['width']/2, x_box['y'] + x_box['height']/2)
        page.wait_for_timeout(700)
        closed = not page.evaluate('''() => !!document.querySelector('.pea-crop-overlay')''')
        checks.append({'name': '× button closes crop', 'pass': closed, 'detail': f'closed: {closed}'})

        # ── T3: confirm button actually performs crop ──
        # Re-open
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1500)

        # Get initial node count
        before_count = page.evaluate('''() => document.querySelectorAll('.react-flow__node').length''')

        # Click confirm
        confirm_btn = page.locator('.pea-crop-confirm')
        c_box = confirm_btn.bounding_box()
        page.mouse.click(c_box['x'] + c_box['width']/2, c_box['y'] + c_box['height']/2)
        page.wait_for_timeout(2500)

        after_count = page.evaluate('''() => document.querySelectorAll('.react-flow__node').length''')
        checks.append({'name': 'confirm creates new node', 'pass': after_count > before_count,
                       'detail': f'nodes: {before_count} → {after_count}'})

        # print summary
        print('\n=== INTERACTIVE E2E RESULTS ===')
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
