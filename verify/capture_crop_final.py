"""Side-by-side comparison: probe the current state of crop in same layout."""
from playwright.sync_api import sync_playwright
import os, time

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
            page.fill('input[placeholder="you@pea.ai"]', f'cmp_{ts}@pea.dev')
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
        src = os.path.join(os.path.dirname(__file__), 'test_crop_portrait.png')
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
        page.screenshot(path='shots/crop_FINAL_default.png')
        print('captured: shots/crop_FINAL_default.png')

        # Set 16:9
        ratio_btn = page.locator('.pea-crop-ratio-btn')
        if ratio_btn.count() > 0:
            box = ratio_btn.bounding_box()
            page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            page.wait_for_timeout(500)
            opt = page.locator('.ant-dropdown-menu-item', has_text='16 : 9')
            if opt.count() > 0:
                opt.first.click()
                page.wait_for_timeout(700)
        page.screenshot(path='shots/crop_FINAL_16_9.png')
        print('captured: shots/crop_FINAL_16_9.png')

        # Set 1:1
        ratio_btn = page.locator('.pea-crop-ratio-btn')
        if ratio_btn.count() > 0:
            box = ratio_btn.bounding_box()
            page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            page.wait_for_timeout(500)
            opt = page.locator('.ant-dropdown-menu-item', has_text='1 : 1')
            if opt.count() > 0:
                opt.first.click()
                page.wait_for_timeout(700)
        page.screenshot(path='shots/crop_FINAL_1_1.png')
        print('captured: shots/crop_FINAL_1_1.png')

        b.close()

if __name__ == '__main__':
    main()
