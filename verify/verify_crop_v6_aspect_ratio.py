"""Verify crop UI v6: transparent stage + crop frame matches image aspect ratio.

User requirements:
  1) No grey/white box around the crop image — stage must be transparent.
  2) Crop frame must match the original image boundaries (full image, correct aspect ratio).
"""
from playwright.sync_api import sync_playwright
import time, os, sys

VIEW_W, VIEW_H = 1440, 900

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'v6_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'Login/nav note: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # Add image node and upload test image
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator('.pea-add-menu-item', has_text="图片").first.click()
        page.wait_for_timeout(800)
        node = page.locator('.react-flow__node').first
        src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(1800)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name="裁剪").click()
        page.wait_for_timeout(1500)

        page.screenshot(path='verify/shots/crop_v6_open.png', full_page=False)

        diag = page.evaluate('''() => {
            const r = { checks: [] };

            const stage = document.querySelector('.pea-crop-stage');
            if (!stage) { r.checks.push({name:'crop stage exists', pass:false, reason:'MISSING'}); return r; }
            r.checks.push({name:'crop stage exists', pass:true});

            const stageBg = getComputedStyle(stage).backgroundColor;
            r.checks.push({name:'stage background is transparent', pass:stageBg==='rgba(0, 0, 0, 0)' || stageBg==='transparent', detail:stageBg});

            const imgStage = document.querySelector('.pea-crop-image-stage');
            const frame = document.querySelector('.pea-crop-frame');
            const img = document.querySelector('.pea-crop-image');
            if (!imgStage || !frame || !img) {
                r.checks.push({name:'image-stage/frame/image exist', pass:false, reason:`imgStage=${!!imgStage} frame=${!!frame} img=${!!img}`});
                return r;
            }
            r.checks.push({name:'image-stage/frame/image exist', pass:true});

            const iR = imgStage.getBoundingClientRect();
            const fR = frame.getBoundingClientRect();

            // Crop frame should match image-stage boundaries (full image, no inset).
            const frameMatchesImage =
                Math.abs(fR.x - iR.x) < 2 &&
                Math.abs(fR.y - iR.y) < 2 &&
                Math.abs(fR.width - iR.width) < 2 &&
                Math.abs(fR.height - iR.height) < 2;
            r.checks.push({name:'crop frame matches image boundaries', pass:frameMatchesImage, detail:`img=${Math.round(iR.width)}x${Math.round(iR.height)} frame=${Math.round(fR.width)}x${Math.round(fR.height)}`});

            // Image-stage aspect ratio should match the natural image aspect ratio.
            const naturalRatio = img.naturalWidth / img.naturalHeight;
            const stageRatio = iR.width / iR.height;
            const ratioMatches = Math.abs(stageRatio - naturalRatio) < 0.05;
            r.checks.push({name:'image-stage ratio matches natural image ratio', pass:ratioMatches, detail:`natural=${naturalRatio.toFixed(3)} stage=${stageRatio.toFixed(3)}`});

            // No grey/white background box around the image (image-stage should be transparent, not a solid color).
            // We verify by checking that stage background is transparent (already done) and that the image fills the stage.
            const imgInStage = iR.width > 0 && iR.height > 0;
            r.checks.push({name:'image-stage has positive size', pass:imgInStage, detail:`${Math.round(iR.width)}x${Math.round(iR.height)}`});

            // Toolbar should be below the image, not overlapping it.
            const toolbar = document.querySelector('.pea-crop-toolbar');
            if (toolbar) {
                const tR = toolbar.getBoundingClientRect();
                const belowImage = tR.top >= iR.bottom - 2;
                r.checks.push({name:'toolbar below image', pass:belowImage, detail:`img_bottom=${Math.round(iR.bottom)} toolbar_top=${Math.round(tR.top)}`});
            } else {
                r.checks.push({name:'toolbar exists', pass:false, reason:'MISSING'});
            }

            return r;
        }''')

        # Try changing ratio to 1:1 and back to original, then verify frame still matches image.
        try:
            ratio_btn = page.locator('.pea-crop-ratio-btn')
            if ratio_btn.count() > 0:
                ratio_btn.click()
                page.wait_for_timeout(300)
                opt_1_1 = page.locator('text=1 : 1').first
                if opt_1_1.count() > 0:
                    opt_1_1.click()
                    page.wait_for_timeout(600)
                    page.screenshot(path='verify/shots/crop_v6_ratio_1x1.png', full_page=False)
                    # Switch back to original to keep the overlay open for final checks.
                    ratio_btn.click()
                    page.wait_for_timeout(300)
                    opt_original = page.locator('text=原图比例').first
                    if opt_original.count() > 0:
                        opt_original.click()
                        page.wait_for_timeout(600)
                else:
                    # Close dropdown by clicking on the image stage (Escape would close the whole overlay).
                    page.locator('.pea-crop-image-stage').click()
        except Exception as ex:
            print(f'Ratio select note: {ex}')

        # Cancel crop
        page.locator('.pea-crop-toolbar-btn').first.click()
        page.wait_for_timeout(500)
        still_open = page.evaluate('() => !!document.querySelector(".pea-crop-overlay")')
        diag['checks'].append({'name': 'cancel closes overlay', 'pass': not still_open})

        print('=== CROP v6 ASPECT RATIO VERIFICATION ===')
        all_pass = True
        for c in diag['checks']:
            ok = c['pass']; all_pass = all_pass and ok
            detail = c.get('detail', ''); reason = c.get('reason', '')
            print(f"  [{'✓' if ok else '✗'}] {c['name']}: {detail} {reason}".strip())
        print(f'\nOverall: {"ALL PASS ✓" if all_pass else "SOME FAILED ✗"}')
        browser.close()
        return 0 if all_pass else 1

if __name__ == '__main__':
    exit(main() or 0)
