"""Verify crop UI refactor (v5): full-screen modal portal to body.

User's three hard requirements:
  1) 点击裁剪时只展示图片 —— 全屏遮罩盖住画布，节点边框/连接点/徽章不可见
  2) 裁剪功能条在图片「正下方」独立展示，不压在裁剪框内
  3) 裁剪框与图片边缘之间半透明遮罩，四角可拖拽改变长宽

Asserts the new DOM: .pea-crop-overlay (fixed, fullscreen) > .pea-crop-backdrop
+ .pea-crop-stage > (.pea-crop-image-stage > img+4 masks+.pea-crop-frame+4 handles)
+ .pea-crop-toolbar (below image).
"""
from playwright.sync_api import sync_playwright
import time, os

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
            page.fill('input[placeholder="you@pea.ai"]', f'v5_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'Login/nav note: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # 添加图片节点 + 上传测试图
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

        page.screenshot(path='verify/shots/crop_v5_open.png', full_page=False)

        # ── Bug-fix #1 验证：选择 16:9 后裁剪框应占满底图宽度（>90%）──
        try:
            ratio_btn = page.locator('.pea-crop-ratio-btn')
            if ratio_btn.count() > 0:
                ratio_btn.click()
                page.wait_for_timeout(300)
                # 从 dropdown 中选 16:9（或直接点 "16 : 9"）
                opt_16_9 = page.locator('text=16 : 9').first
                if opt_16_9.count() > 0:
                    opt_16_9.click()
                    page.wait_for_timeout(600)
                    page.screenshot(path='verify/shots/crop_v5_ratio_16x9.png', full_page=False)
                else:
                    page.keyboard.press('Escape')  # 关闭 dropdown
        except Exception as ex:
            print(f'  [note] ratio select skipped: {ex}')

        # ── DOM 级断言 ──
        diag = page.evaluate('''({VW, VH}) => {
            const r = { checks: [] };
            const ov = document.querySelector('.pea-crop-overlay');
            if (!ov) { r.checks.push({name:'crop overlay exists', pass:false, reason:'MISSING'}); return r; }
            r.checks.push({name:'crop overlay exists', pass:true});

            const ovs = getComputedStyle(ov);
            r.checks.push({name:'overlay position=fixed', pass:ovs.position==='fixed', detail:ovs.position});
            const oRect = ov.getBoundingClientRect();
            const covers = oRect.x <= 1 && oRect.y <= 1 && oRect.width >= VW - 5 && oRect.height >= VH - 5;
            r.checks.push({name:'overlay covers viewport', pass:covers, detail:Math.round(oRect.width)+'x'+Math.round(oRect.height)+' vs '+VW+'x'+VH});

            // 节点边框被遮住：backdrop 全屏 + 节点处于 is-cropping
            const bd = document.querySelector('.pea-crop-backdrop');
            if (bd) {
                const bRect = bd.getBoundingClientRect();
                const bcovers = bRect.width >= VW - 5 && bRect.height >= VH - 5;
                r.checks.push({name:'backdrop covers viewport', pass:bcovers, detail:''+Math.round(bRect.width)+'x'+Math.round(bRect.height)});
            } else { r.checks.push({name:'backdrop', pass:false, reason:'MISSING'}); }

            const croppingNode = document.querySelector('.pea-node.is-cropping');
            r.checks.push({name:'node has is-cropping class', pass:!!croppingNode});
            if (croppingNode) {
                const ea = croppingNode.querySelector('.pea-node-editor-anchor');
                if (ea) r.checks.push({name:'node editor hidden (display:none)', pass:getComputedStyle(ea).display==='none', detail:getComputedStyle(ea).display});
            }

            const stage = document.querySelector('.pea-crop-stage');
            const imgStage = document.querySelector('.pea-crop-image-stage');
            const frame = document.querySelector('.pea-crop-frame');
            const toolbar = document.querySelector('.pea-crop-toolbar');
            const masks = document.querySelectorAll('.pea-crop-mask');
            const handles = document.querySelectorAll('.pea-crop-handle');

            r.checks.push({name:'image-stage exists', pass:!!imgStage});
            if (imgStage && frame) {
                const iR = imgStage.getBoundingClientRect();
                const fR = frame.getBoundingClientRect();

                // Bug-fix #1: 比例模式下裁剪框应占满底图宽或高（>88%）
                const wRatio = fR.width / iR.width;
                const hRatio = fR.height / iR.height;
                const fillsWidth = wRatio > 0.88;
                r.checks.push({name:'[FIX#1] crop frame fills image width (>88%)', pass:fillsWidth, detail:''+(wRatio*100).toFixed(0)+'% of img width ('+Math.round(fR.width)+'/'+Math.round(iR.width)+')'});

                const fcx = fR.x + fR.width/2, fcy = fR.y + fR.height/2;
                const icx = iR.x + iR.width/2, icy = iR.y + iR.height/2;
                const centered = Math.abs(fcx-icx) < 6 && Math.abs(fcy-icy) < 6;
                r.checks.push({name:'crop frame centered in image', pass:centered, detail:'d=('+Math.round(fcx-icx)+','+Math.round(fcy-icy)+')'});
            }

            // Bug-fix #2: handle 的 z-index 应高于 frame（确保拖拽事件不被拦截）
            if (frame) {
                const fz = getComputedStyle(frame).zIndex;
                r.checks.push({name:'[FIX#2] frame has z-index', pass:fz !== 'auto' && parseInt(fz) >= 1, detail:'frame z-index='+fz});
            }
            const handleEl = document.querySelector('.pea-crop-handle');
            if (handleEl) {
                const hz = getComputedStyle(handleEl).zIndex;
                r.checks.push({name:'[FIX#2] handle has higher z-index', pass:hz !== 'auto' && parseInt(hz) >= 2, detail:'handle z-index='+hz});
            }

            if (toolbar && imgStage) {
                const tR = toolbar.getBoundingClientRect();
                const iR = imgStage.getBoundingClientRect();
                r.checks.push({name:'toolbar visible', pass:tR.width>50 && tR.height>24, detail:''+Math.round(tR.width)+'x'+Math.round(tR.height)});
                // 关键：工具栏在图片「下方」，且不在裁剪框内部
                const belowImage = tR.top >= iR.bottom - 4;
                r.checks.push({name:'toolbar BELOW image (not inside crop box)', pass:belowImage, detail:'img_bottom='+Math.round(iR.bottom)+' toolbar_top='+Math.round(tR.top)});
                if (frame) {
                    const fR = frame.getBoundingClientRect();
                    const insideFrame = tR.x >= fR.x-2 && tR.x+tR.width <= fR.x+fR.width+2 && tR.y >= fR.y-2 && tR.y+tR.height <= fR.y+fR.height+2;
                    r.checks.push({name:'toolbar NOT inside crop frame', pass:!insideFrame});
                }
            } else { r.checks.push({name:'toolbar', pass:false, reason:'MISSING'}); }

            r.checks.push({name:'4 masks', pass:masks.length===4, detail:''+masks.length});
            // 4 角把手 + 4 边中把手 = 8 个
            r.checks.push({name:'8 handles (4 corners + 4 edges)', pass:handles.length===8, detail:''+handles.length});

            // Bug-fix #3: 裁剪框整区（含边框线）cursor 必须是 move
            if (frame) {
                const fCursor = getComputedStyle(frame).cursor;
                r.checks.push({name:'[FIX#3] frame cursor is "move"', pass:fCursor==='move', detail:'cursor='+fCursor});
                const fBg = getComputedStyle(frame).backgroundColor;
                const hasBg = fBg && fBg !== 'transparent';
                r.checks.push({name:'[FIX#3] frame has background-color set', pass:hasBg, detail:'bg='+String(fBg).substring(0,40)});
            }
            return r;
        }''', {'VW': VIEW_W, 'VH': VIEW_H})

                # ── [FIX#5] 验证边中把手拖拽：拖动 n 边（上边）改变高度 ──
        fr = page.locator('.pea-crop-frame').bounding_box()
        h_before = fr['height'] if fr else 0
        n_handle = page.locator('.pea-crop-handle.edge.n')
        if n_handle.count() > 0 and fr:
            n_box = n_handle.bounding_box()
            if n_box:
                start_x = n_box['x'] + n_box['width'] / 2
                start_y = n_box['y'] + n_box['height'] / 2
                page.mouse.move(start_x, start_y)
                page.mouse.down()
                page.mouse.move(start_x, start_y + 100, steps=12)
                page.mouse.up()
                page.wait_for_timeout(600)
                fr_after = page.locator('.pea-crop-frame').bounding_box()
                if fr_after:
                    h_after = fr_after['height']
                    h_changed = abs(h_after - h_before) > 20
                    diag['checks'].append({'name': '[FIX#5] drag N-edge changes height', 'pass': h_changed, 'detail': f'h: {round(h_before)} -> {round(h_after)} (diff={round(h_after - h_before)})'})
                    page.screenshot(path='verify/shots/crop_v5_edge_drag.png', full_page=False)
                else:
                    diag['checks'].append({'name': '[FIX#5] drag N-edge', 'pass': False, 'reason': 'no frame after edge drag'})
            else:
                diag['checks'].append({'name': '[FIX#5] drag N-edge', 'pass': False, 'reason': 'handle no bounding_box'})
        else:
            diag['checks'].append({'name': '[FIX#5] drag N-edge', 'pass': False, 'reason': f'handle_count={n_handle.count()} frame={bool(fr)}'})

# ── 取消后浮层消失、节点恢复 ──
        page.locator('.pea-crop-toolbar-btn').first.click()  # ✕ 取消
        page.wait_for_timeout(500)
        still_open = page.evaluate('() => !!document.querySelector(".pea-crop-overlay")')
        diag['checks'].append({'name': 'cancel closes overlay', 'pass': not still_open})

        print('=== CROP v5 VERIFICATION ===')
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
