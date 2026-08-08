"""Re-probe with inline JS to dump fitDisplay's inputs at the moment of call."""
from playwright.sync_api import sync_playwright
import os, time, sys

VIEW_W, VIEW_H = 1440, 900

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')

        # Capture all console logs
        page.on('console', lambda msg: print(f'[console.{msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: print(f'[pageerror] {err}'))

        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(800)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'probe2_{ts}@pea.dev')
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

        # Inject a probe that wraps rect/innerWidth when fitDisplay runs.
        # We instrument by overriding getBoundingClientRect temporarily.
        page.evaluate(r'''() => {
            const origGetBCR = Element.prototype.getBoundingClientRect;
            window.__rectCalls = [];
            Element.prototype.getBoundingClientRect = function() {
                if (this.classList?.contains('pea-node-result-image-wrap')) {
                    const r = origGetBCR.call(this);
                    const dump = { tag: this.tagName, cls: this.className, w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y),
                                   caller: (new Error()).stack?.split('\n').slice(1,4).join('|') ?? '' };
                    window.__rectCalls.push(dump);
                }
                return origGetBCR.call(this);
            };
        }''')

        # Click crop and then immediately dump
        page.locator('.pea-node-result-toolbar').get_by_role('button', name='裁剪').click()
        page.wait_for_timeout(1800)

        rect_calls = page.evaluate('''() => window.__rectCalls''')
        print(f'\n[rect calls for .pea-node-result-image-wrap]  ({len(rect_calls)} captured)')
        for i, r in enumerate(rect_calls):
            print(f'  #{i+1} {r}')

        # After crop mount: also re-measure current viewport and crops
        info = page.evaluate('''() => {
            function rectOf(sel) {
                const el = document.querySelector(sel);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) };
            }
            return {
                viewport: { innerW: window.innerWidth, innerH: window.innerHeight },
                imgWrap:   rectOf('.pea-node-result-image-wrap'),
                cropOverlay: rectOf('.pea-crop-overlay'),
                cropCard:  rectOf('.pea-crop-stage'),
                cropImgStage: rectOf('.pea-crop-image-stage'),
                cropImgStyle: document.querySelector('.pea-crop-image-stage')?.style?.cssText ?? null,
                // Look at parents of .pea-crop-image-stage to see how it grew
                parentChain: (() => {
                    const el = document.querySelector('.pea-crop-image-stage');
                    if (!el) return [];
                    const out = [];
                    let cur = el;
                    while (cur && cur !== document.body) {
                        const r = cur.getBoundingClientRect();
                        out.push({
                            cls: cur.className,
                            tag: cur.tagName,
                            w: Math.round(r.width), h: Math.round(r.height),
                            style: cur.style.cssText.slice(0,200),
                            display: getComputedStyle(cur).display,
                        });
                        cur = cur.parentElement;
                    }
                    return out;
                })(),
            };
        }''')
        print('\n[final state]')
        for k, v in info.items():
            print(f'  {k:18s} = {v}')

        page.screenshot(path='shots/crop_probe2.png', full_page=False)
        browser.close()
        return 0

if __name__ == '__main__':
    sys.exit(main() or 0)
