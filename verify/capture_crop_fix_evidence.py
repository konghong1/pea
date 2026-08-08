"""Take a side-by-side screenshot for visual evidence of the fix."""
from playwright.sync_api import sync_playwright
import os, time

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
            page.fill('input[placeholder="you@pea.ai"]', f'viz_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'[note] {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text='图片').first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(2500)
        node.click()
        page.wait_for_timeout(400)
        # Screenshot 1: BEFORE crop, just the node
        page.screenshot(path='shots/crop_fix_evidence_BEFORE.png', full_page=False)

        # Now open crop
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1500)
        # Screenshot 2: WITH crop
        page.screenshot(path='shots/crop_fix_evidence_DURING.png', full_page=False)

        # Print final dimensions for the report
        info = page.evaluate(r'''() => {
            function rectOf(sel){const el=document.querySelector(sel);if(!el)return null;const r=el.getBoundingClientRect();return{w:Math.round(r.width),h:Math.round(r.height)};}
            return {imgWrap:rectOf('.pea-node-result-image-wrap'),cropImgStage:rectOf('.pea-crop-image-stage'),locked:!!document.querySelector('.pea-canvas-locked')};
        }''')
        print(f'wrap={info["imgWrap"]}  stage={info["cropImgStage"]}  locked={info["locked"]}')

        browser.close()

if __name__ == '__main__':
    main()
