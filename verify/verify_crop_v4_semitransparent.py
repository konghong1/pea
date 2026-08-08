"""Crop overlay verification v4.3 (2026-08-08):
Fixes verified:
1. Node border HIDDEN in crop mode (body-card: bg=transparent, border=none, shadow=none, radius=0)
2. Mask uses box-shadow VIGNETTE on frame (uniform transparency, no corner overlap)
3. Toolbar BELOW image (image-stage bottom:52px, toolbar in independent area below)
4. Stage has visible dark background (provides visual container boundary)
5. No "double-border" or "two-images" visual artifacts
6. Screenshots output to verify/ directory (not shots/)
7. [v4.2] Corner/edge handles use HOLLOW fine-line style (not solid white squares)
8. [v4.3] Frame WITHIN image bounds (fitDisplay subtracts 52px toolbar space from H)

Reference: screenshot 2 shows clean image+frame only, semi-transparent uniform mask,
           subtle hollow handles, toolbar below image, frame tightly around image.
"""
from playwright.sync_api import sync_playwright
import os, re, time

VIEW_W, VIEW_H = 1440, 900
SHOT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel='chrome')
        page = b.new_page(viewport={'width': VIEW_W, 'height': VIEW_H})
        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto('http://localhost:8088', wait_until='networkidle')
        page.wait_for_timeout(600)
        try:
            page.get_by_role('button', name='没有账号？去注册').first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f'cropv41_{ts}@pea.dev')
            page.fill('input[placeholder="至少 8 位"]', 'Password123')
            page.locator('form button[type=submit]').click()
            page.wait_for_timeout(4000)
            page.locator('text=新建项目').first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f'nav: {e}')
        page.wait_for_selector('.react-flow__viewport', timeout=15000)

        # Create image node and upload
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

        # ── Comprehensive DOM probe ──
        info = page.evaluate(r'''() => {
            const orig = document.querySelector('.pea-node-result-preview');
            const bodyCard = document.querySelector('.pea-node-body-card');
            const mediaCard = document.querySelector('.pea-node-media-card');
            const stage = document.querySelector('.pea-crop-stage');
            const imgStage = document.querySelector('.pea-crop-image-stage');
            const cropImg = document.querySelector('.pea-crop-image');
            const masks = document.querySelectorAll('.pea-crop-mask');
            const frame = document.querySelector('.pea-crop-frame');
            const toolbar = document.querySelector('.pea-crop-toolbar');
            const wrap = document.querySelector('.pea-node-result-image-wrap');
            const croppingNode = document.querySelector('.pea-node.is-cropping');
            const handles = document.querySelectorAll('.pea-crop-handle');
            const cornerHandles = document.querySelectorAll('.pea-crop-handle.nw, .pea-crop-handle.ne, .pea-crop-handle.sw, .pea-crop-handle.se');
            const edgeHandles = document.querySelectorAll('.pea-crop-handle.edge');

            function box(el) {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { x: Math.round(r.x), y: Math.round(r.y),
                         w: Math.round(r.width), h: Math.round(r.height),
                         right: Math.round(r.right), bottom: Math.round(r.bottom) };
            }
            function cs(el, props) {
                if (!el) return null;
                const s = getComputedStyle(el);
                const out = {};
                for (const p of props) out[p] = s[p];
                return out;
            }

            // Parse first rgba value from a string (handles box-shadow like "0 0 0 3000px rgba(0,0,0,0.55)")
            function parseFirstAlpha(str) {
                if (!str) return null;
                const m = str.match(/rgba?\([^)]+\)/);
                if (!m) return null;
                const nums = m[0].match(/[\d.]+/g);
                return nums && nums.length >= 4 ? parseFloat(nums[3]) : null;
            }

            const maskOpacities = Array.from(masks).map(m => parseFloat(getComputedStyle(m).opacity));
            const frameBs = getComputedStyle(frame).boxShadow;

            // Handle style checks (v4.2: hollow fine-line style)
            let handleStyle = null;
            if (cornerHandles.length > 0) {
                const h = cornerHandles[0];
                const hs = getComputedStyle(h);
                handleStyle = {
                    width: hs.width,
                    height: hs.height,
                    background: hs.background,
                    backgroundColor: hs.backgroundColor,
                    border: hs.border,
                    borderWidth: hs.borderWidth,
                    borderStyle: hs.borderStyle,
                    borderColor: hs.borderColor,
                    borderRadius: hs.borderRadius,
                    count: handles.length,
                    cornerCount: cornerHandles.length,
                    edgeCount: edgeHandles.length,
                };
            }

            return {
                hasCroppingClass: !!croppingNode,
                orig: { box: box(orig), cs: cs(orig, ['visibility', 'display', 'opacity']) },
                bodyCard: {
                    box: box(bodyCard),
                    cs: cs(bodyCard, ['background', 'backgroundColor', 'border', 'borderColor',
                                        'boxShadow', 'borderRadius', 'outline', 'overflow'])
                },
                stage: { box: box(stage), cs: cs(stage, ['background', 'backgroundColor', 'position',
                                                              'paddingBottom', 'boxSizing']) },
                imgStage: { box: box(imgStage) },
                cropImg: { box: box(cropImg) },
                masks: { count: masks.length, opacities: maskOpacities },
                frame: { box: box(frame), cs: cs(frame, ['boxShadow']), boxShadowStr: frameBs },
                toolbar: { box: box(toolbar), cs: toolbar ? cs(toolbar, ['position', 'bottom']) : null },
                wrap: { box: box(wrap) },
                handleStyle: handleStyle,
            };
        }''')

        print('\n=== DOM State during crop ===')
        for k, v in info.items():
            print(f'  {k}: {v}')

        # ── TEST 1: Node has .is-cropping class ──
        checks.append({
            'name': '[1] .pea-node.is-cropping class present',
            'pass': info['hasCroppingClass'],
            'detail': f"hasCroppingClass={info['hasCroppingClass']}",
        })

        # ── TEST 2-5: Body-card decorations HIDDEN ──
        bc = info['bodyCard']['cs']
        bg_transparent = (
            bc.get('background', '') == 'transparent' or
            '0, 0, 0, 0)' in bc.get('backgroundColor', '') or
            bc.get('backgroundColor', '') == 'transparent'
        )
        border_none = bc.get('border', '') == 'none' or '0px none' in bc.get('border', '')
        shadow_none = bc.get('boxShadow', '') == 'none' or not bc.get('boxShadow')
        radius_zero = bc.get('borderRadius', '') in ('0px', '0')

        checks.append({'name': '[2] body-card background transparent', 'pass': bg_transparent,
                       'detail': f"bg={bc.get('background','?')}"})
        checks.append({'name': '[3] body-card border none', 'pass': border_none,
                       'detail': f"border={bc.get('border','?')}"})
        checks.append({'name': '[4] body-card shadow none', 'pass': shadow_none,
                       'detail': f"shadow={bc.get('boxShadow','?')}"})
        checks.append({'name': '[5] body-card borderRadius 0', 'pass': radius_zero,
                       'detail': f"radius={bc.get('borderRadius','?')}"})

        # ── TEST 6: Old masks are HIDDEN (opacity:0) — replaced by frame vignette ──
        mask_opacities = info['masks'].get('opacities', [])
        masks_hidden = all(o == 0 for o in mask_opacities) if mask_opacities else False
        checks.append({
            'name': '[6] old 4-mask elements hidden (opacity:0, replaced by vignette)',
            'pass': masks_hidden,
            'detail': f"mask opacities={mask_opacities}",
        })

        # ── TEST 7: Frame uses box-shadow VIGNETTE (has large spread radius ~3000px) ──
        frame_bs = info['frame'].get('boxShadowStr', '')
        has_vignette = bool(re.search(r'3000px', frame_bs)) and bool(re.search(r'rgba?\(', frame_bs))
        # Also check alpha is in semi-transparent range
        frame_alpha = None
        am = re.search(r'rgba?\([^)]+\)', frame_bs)
        if am:
            nums2 = re.findall(r'[\d.]+', am.group(0))
            if len(nums2) >= 4:
                frame_alpha = float(nums2[3])
        is_semi = frame_alpha is not None and 0.25 <= frame_alpha <= 0.75
        checks.append({
            'name': '[7] frame box-shadow vignette (3000px spread + semi-transparent)',
            'pass': has_vignette and is_semi,
            'detail': f"boxShadow={frame_bs[:80]}, alpha={frame_alpha}",
        })

        # ── TEST 8-9: Stage background + image-stage shorter than stage ──
        stage_cs = info['stage']['cs']
        stage_bg = stage_cs.get('backgroundColor', '')
        stage_has_bg = stage_bg and '0, 0, 0, 0)' not in stage_bg and stage_bg != 'transparent'
        checks.append({
            'name': '[8] stage has visible background',
            'pass': stage_has_bg,
            'detail': f"bg={stage_bg}",
        })
        # Image-stage should be shorter than stage (bottom:52px leaves room for toolbar)
        stage_box = info['stage'].get('box', {})
        imgstage_box = info['imgStage'].get('box', {})
        img_shorter = (imgstage_box.get('h', 0) < stage_box.get('h', 0) - 30)
        checks.append({
            'name': '[9] image-stage shorter than stage (>30px room for toolbar below)',
            'pass': img_shorter,
            'detail': f"stage.h={stage_box.get('h')} imgStage.h={imgstage_box.get('h')}",
        })

        # ── TEST 10: Original image hidden ──
        orig_hidden = info['orig']['cs'].get('visibility') == 'hidden'
        checks.append({
            'name': '[10] original <img> visibility:hidden',
            'pass': orig_hidden,
            'detail': f"visibility={info['orig']['cs'].get('visibility')}",
        })

        # ── TEST 11: Toolbar BELOW image (toolbar top >= imgStage bottom, or close) ──
        tb_box = info['toolbar'].get('box')
        is_box = info['imgStage'].get('box', {})  # imgStage is { box: {...} }
        toolbar_below_image = False
        if tb_box and is_box:
            img_bottom = is_box.get('bottom', 0)
            tb_top = tb_box.get('y', 0)
            # Toolbar should be at or below image bottom (with small tolerance)
            toolbar_below_image = tb_top >= img_bottom - 10
        checks.append({
            'name': '[11] toolbar positioned BELOW image (not overlapping)',
            'pass': toolbar_below_image,
            'detail': f"imgStage.bottom={is_box.get('bottom')} toolbar.top={tb_box.get('y') if tb_box else '?'}",
        })

        # ── TEST 12-15: v4.2 Handle fine-line style (NOT solid white squares) ──
        hs = info.get('handleStyle')
        if hs:
            w = float(hs.get('width', '0').replace('px', ''))
            h = float(hs.get('height', '0').replace('px', ''))
            bg = hs.get('backgroundColor', '')
            border_w = float(hs.get('borderWidth', '0').replace('px', ''))

            # Corner handles should be ~6x6 (not 8x8 solid blocks)
            is_small = 4 <= w <= 8 and 4 <= h <= 8
            checks.append({'name': '[12] corner handle size ~6×6 (not large squares)',
                           'pass': is_small, 'detail': f"size={w}×{h}"})

            # Background should be transparent (hollow), NOT solid white/rgb(255,255,255)
            is_hollow = ('0, 0, 0, 0)' in bg or bg == 'transparent')
            checks.append({'name': '[13] handle background TRANSPARENT (hollow, not solid white)',
                           'pass': is_hollow, 'detail': f"bg={bg}"})

            # Should have visible white border (1.5px)
            has_border = border_w >= 1
            checks.append({'name': '[14] handle has white border (fine-line style)',
                           'pass': has_border, 'detail': f"borderWidth={border_w}"})

            # Should have 8 handles total (4 corners + 4 edges)
            right_count = hs.get('cornerCount', 0) == 4 and hs.get('edgeCount', 0) == 4
            checks.append({'name': '[15] 8 handles present (4 corners + 4 edges)',
                           'pass': right_count,
                           'detail': f"corners={hs.get('cornerCount')} edges={hs.get('edgeCount')}"})
        else:
            for t in ['[12] corner handle size ~6×6', '[13] handle background transparent',
                      '[14] handle has white border', '[15] 8 handles present']:
                checks.append({'name': t, 'pass': False, 'detail': 'no handle data'})

        # ── TEST 16: Frame WITHIN image bounds (critical fix — frame must not exceed image) ──
        fb = info['frame'].get('box', {})
        isb = info['imgStage'].get('box', {})
        if fb and isb:
            # Frame should be within or equal to image-stage bounds (allowing 2px tolerance)
            f_within_x = fb.get('x', 9999) >= isb.get('x', 0) - 2
            f_within_y = fb.get('y', 9999) >= isb.get('y', 0) - 2
            f_within_right = fb.get('right', 0) <= isb.get('right', 9999) + 2
            f_within_bottom = fb.get('bottom', 0) <= isb.get('bottom', 9999) + 2
            all_within = f_within_x and f_within_y and f_within_right and f_within_bottom
            checks.append({
                'name': '[16] frame WITHIN image bounds (not exceeding image)',
                'pass': all_within,
                'detail': f"frame=({fb.get('x')},{fb.get('y')},{fb.get('w')}×{fb.get('h')}) "
                        f"imgStage=({isb.get('x')},{isb.get('y')},{isb.get('w')}×{isb.get('h')}) "
                        f"overflow_b={fb.get('bottom',0)-isb.get('bottom',9999) if fb.get('bottom',0)>isb.get('bottom',9999) else 'OK'}",
            })
        else:
            checks.append({'name': '[16] frame WITHIN image bounds', 'pass': False, 'detail': 'missing data'})

        # ── Screenshot evidence (output to verify/) ──
        shot_path = os.path.join(SHOT_DIR, 'crop_v4.3_frame_within_image.png')
        page.screenshot(path=shot_path, full_page=False)
        print(f'\n  screenshot: {shot_path}')

        # ── Print results ──
        print('\n=== RESULTS ===')
        n_pass = sum(1 for c in checks if c['pass'])
        for c in checks:
            mark = '\u2713' if c['pass'] else '\u2717'
            print(f"  [{mark}] {c['name']}: {c.get('detail','')}")
        print(f"\n  {n_pass}/{len(checks)} PASS")

        b.close()
        return 0 if n_pass == len(checks) else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
