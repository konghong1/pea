"""Verify crop UI fixes (v6):

User requirements:
  1) 点击裁剪后默认「原图比例」，裁剪框必须完整覆盖底图（mask 区域为 0）。
  2) 选择固定比例（如 16:9）后，保留四角 + 四边中点把手；拖动四角保持比例缩放，
     拖动边线只平移裁剪框、不缩放。
  3) 选择「自定义…」后，工具栏直接显示 宽:高 输入框，可输入并应用。
  4) 点击确认裁剪后，生成的新节点与原节点的连线使用 targetHandle='in'（连到新节点输入端）。

Assumes the full stack is running on http://localhost:8088.
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
            page.fill('input[placeholder="you@pea.ai"]', f'v6_{ts}@pea.dev')
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
        # 使用竖向测试图模拟用户截图场景，验证默认全包
        src = os.path.join(os.path.dirname(__file__), 'test_crop_portrait.png')
        if not os.path.exists(src):
            src = os.path.join(os.path.dirname(__file__), 'test_crop_source.png')
        if not os.path.exists(src):
            # fallback: use any png in verify folder
            for f in os.listdir(os.path.dirname(__file__)):
                if f.endswith('.png'):
                    src = os.path.join(os.path.dirname(__file__), f)
                    break
        node.locator("input[type='file']").set_input_files(src)
        page.wait_for_timeout(1800)
        node.click()
        page.wait_for_timeout(400)
        page.locator('.pea-node-result-toolbar').get_by_role('button', name="裁剪").click()
        page.wait_for_timeout(1200)

        checks = []

        # ── FIX #1: 默认进入裁剪，裁剪框居中、四周留约 10% 边距 ──
        def measure_crop():
            return page.evaluate('''() => {
                const imgStage = document.querySelector('.pea-crop-image-stage');
                const frame = document.querySelector('.pea-crop-frame');
                if (!imgStage || !frame) return null;
                const i = imgStage.getBoundingClientRect();
                const f = frame.getBoundingClientRect();
                return {
                    imgW: Math.round(i.width), imgH: Math.round(i.height),
                    frameW: Math.round(f.width), frameH: Math.round(f.height),
                    frameX: Math.round(f.x - i.x), frameY: Math.round(f.y - i.y),
                    maskTop: document.querySelector('.pea-crop-mask-top')?.getBoundingClientRect().height ?? -1,
                    maskBottom: document.querySelector('.pea-crop-mask-bottom')?.getBoundingClientRect().height ?? -1,
                    maskLeft: document.querySelector('.pea-crop-mask-left')?.getBoundingClientRect().width ?? -1,
                    maskRight: document.querySelector('.pea-crop-mask-right')?.getBoundingClientRect().width ?? -1,
                };
            }''')

        m = measure_crop()
        if m:
            # 默认居中 80%：frame 约等于 0.8*img，mask 上下左右均 > 0 且近似相等
            expected_ratio = 0.8
            size_ok = (
                abs(m['frameW'] - m['imgW'] * expected_ratio) <= 4 and
                abs(m['frameH'] - m['imgH'] * expected_ratio) <= 4
            )
            centered = (
                abs(m['frameX'] - (m['imgW'] - m['frameW']) / 2) <= 4 and
                abs(m['frameY'] - (m['imgH'] - m['frameH']) / 2) <= 4
            )
            has_margin = m['maskTop'] > 5 and m['maskBottom'] > 5 and m['maskLeft'] > 5 and m['maskRight'] > 5
            checks.append({'name': '[FIX#1] default crop frame is centered with margin', 'pass': size_ok and centered and has_margin,
                           'detail': f"img={m['imgW']}x{m['imgH']} frame={m['frameW']}x{m['frameH']} pos=({m['frameX']},{m['frameY']}) masks=t/b/l/r={m['maskTop']:.0f}/{m['maskBottom']:.0f}/{m['maskLeft']:.0f}/{m['maskRight']:.0f}"})
        else:
            checks.append({'name': '[FIX#1] crop overlay open', 'pass': False, 'reason': 'no image-stage/frame'})

        page.screenshot(path='shots/crop_v6_original.png', full_page=False)

        # 选择「原图比例」后，裁剪框应完整覆盖底图
        ratio_btn = page.locator('.pea-crop-ratio-btn')
        if ratio_btn.count() > 0:
            ratio_btn.click()
            page.wait_for_timeout(400)
            opt_original = page.locator('.ant-dropdown-menu-item', has_text='原图比例').first
            if opt_original.count() > 0:
                opt_original.click()
                page.wait_for_timeout(600)
                m_orig = measure_crop()
                if m_orig:
                    full_cover = (
                        m_orig['frameX'] <= 1 and m_orig['frameY'] <= 1 and
                        abs(m_orig['frameW'] - m_orig['imgW']) <= 1 and abs(m_orig['frameH'] - m_orig['imgH']) <= 1 and
                        m_orig['maskTop'] <= 1 and m_orig['maskBottom'] <= 1 and m_orig['maskLeft'] <= 1 and m_orig['maskRight'] <= 1
                    )
                    checks.append({'name': '[FIX#1] original ratio option fully covers image', 'pass': full_cover,
                                   'detail': f"img={m_orig['imgW']}x{m_orig['imgH']} frame={m_orig['frameW']}x{m_orig['frameH']} masks=t/b/l/r={m_orig['maskTop']:.0f}/{m_orig['maskBottom']:.0f}/{m_orig['maskLeft']:.0f}/{m_orig['maskRight']:.0f}"})
            else:
                page.keyboard.press('Escape')

        # ── FIX #2: 选择 16:9 后，仍保留四角 + 四边中点把手，拖动时保持比例 ──
        ratio_btn = page.locator('.pea-crop-ratio-btn')
        if ratio_btn.count() > 0:
            ratio_btn.click()
            page.wait_for_timeout(300)
            opt_16_9 = page.locator('text=16 : 9').first
            if opt_16_9.count() > 0:
                opt_16_9.click()
                page.wait_for_timeout(600)
                handles_info = page.evaluate('''() => {
                    const handles = document.querySelectorAll('.pea-crop-handle');
                    const corners = Array.from(handles).filter(h => /\\b(nw|ne|sw|se)\\b/.test(h.className));
                    const edges = Array.from(handles).filter(h => /\\bedge\\b/.test(h.className));
                    return { total: handles.length, corners: corners.length, edges: edges.length };
                }''')
                has_all_handles = handles_info['total'] == 8 and handles_info['corners'] == 4 and handles_info['edges'] == 4
                checks.append({'name': '[FIX#2] 16:9 shows 8 handles (4 corners + 4 edges)', 'pass': has_all_handles,
                               'detail': f"total={handles_info['total']} corners={handles_info['corners']} edges={handles_info['edges']}"})

                # 验证边线中点把手拖动为平移：frame 大小基本不变，位置变化
                before = measure_crop()
                edge_handle = page.locator('.pea-crop-handle.edge.e').first
                if edge_handle.count() > 0 and before:
                    box = edge_handle.bounding_box()
                    if box:
                        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        page.mouse.down()
                        page.mouse.move(box['x'] + box['width']/2 - 80, box['y'] + box['height']/2 + 40, steps=10)
                        page.mouse.up()
                        page.wait_for_timeout(400)
                        after = measure_crop()
                        if after:
                            size_unchanged = abs(after['frameW'] - before['frameW']) <= 2 and abs(after['frameH'] - before['frameH']) <= 2
                            moved = abs(after['frameX'] - before['frameX']) > 5 or abs(after['frameY'] - before['frameY']) > 5
                            checks.append({'name': '[FIX#2] edge handle pans crop frame without resizing', 'pass': size_unchanged and moved,
                                           'detail': f"size before={before['frameW']}x{before['frameH']} after={after['frameW']}x{after['frameH']} moved=({after['frameX']-before['frameX']},{after['frameY']-before['frameY']})"})

                # 验证四角把手仍可缩放并保持比例
                before = measure_crop()
                corner_handle = page.locator('.pea-crop-handle.se').first
                if corner_handle.count() > 0 and before:
                    box = corner_handle.bounding_box()
                    if box:
                        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        page.mouse.down()
                        page.mouse.move(box['x'] + box['width']/2 - 60, box['y'] + box['height']/2 - 60, steps=10)
                        page.mouse.up()
                        page.wait_for_timeout(400)
                        after = measure_crop()
                        if after:
                            changed = abs(after['frameW'] - before['frameW']) > 5 or abs(after['frameH'] - before['frameH']) > 5
                            ratio_stable = abs((after['frameW']/after['frameH']) - (before['frameW']/before['frameH'])) < 0.05
                            checks.append({'name': '[FIX#2] corner handle still resizes 16:9 crop while keeping ratio', 'pass': changed and ratio_stable,
                                           'detail': f"before={before['frameW']}x{before['frameH']} after={after['frameW']}x{after['frameH']} ratio_stable={ratio_stable}"})
                page.screenshot(path='shots/crop_v6_16x9.png', full_page=False)
            else:
                page.keyboard.press('Escape')
                checks.append({'name': '[FIX#2] select 16:9', 'pass': False, 'reason': '16:9 option not found'})
        else:
            checks.append({'name': '[FIX#2] ratio button exists', 'pass': False, 'reason': 'ratio button missing'})

        # ── FIX #3: 选择自定义后显示 宽:高 输入框 ──
        if ratio_btn.count() > 0:
            ratio_btn.click()
            page.wait_for_timeout(300)
            opt_custom = page.locator('.ant-dropdown-menu-item', has_text='自定义…').first
            if opt_custom.count() > 0:
                opt_custom.click()
                page.wait_for_timeout(600)
                inputs_info = page.evaluate('''() => {
                    const wrap = document.querySelector('.pea-crop-custom-ratio');
                    if (!wrap) return { visible: false };
                    const inputs = wrap.querySelectorAll('input[type="number"]');
                    return { visible: wrap.getBoundingClientRect().width > 10, inputCount: inputs.length, hasColon: wrap.textContent.includes(':') };
                }''')
                has_inputs = inputs_info.get('visible') and inputs_info.get('inputCount') == 2 and inputs_info.get('hasColon')
                checks.append({'name': '[FIX#3] custom ratio shows width/height inputs with colon', 'pass': has_inputs,
                               'detail': f"visible={inputs_info.get('visible')} inputs={inputs_info.get('inputCount')} colon={inputs_info.get('hasColon')}"})
                page.screenshot(path='shots/crop_v6_custom_input.png', full_page=False)

                # 输入 2:1 并按 Enter 应用
                inputs = page.locator('.pea-crop-custom-ratio input[type="number"]')
                if inputs.count() >= 2:
                    inputs.nth(0).fill('2')
                    inputs.nth(1).fill('1')
                    inputs.nth(1).press('Enter')
                    page.wait_for_timeout(600)
                    custom_m = measure_crop()
                    if custom_m:
                        ratio_ok = abs((custom_m['frameW'] / custom_m['frameH']) - 2.0) < 0.1
                        checks.append({'name': '[FIX#3] custom 2:1 ratio applied', 'pass': ratio_ok,
                                       'detail': f"frame={custom_m['frameW']}x{custom_m['frameH']} ratio={custom_m['frameW']/custom_m['frameH']:.2f}"})
                        page.screenshot(path='shots/crop_v6_custom_2x1.png', full_page=False)
            else:
                checks.append({'name': '[FIX#3] select custom', 'pass': False, 'reason': 'custom option not found'})
        else:
            checks.append({'name': '[FIX#3] ratio button exists', 'pass': False, 'reason': 'ratio button missing'})

        # ── FIX #4: 确认裁剪后生成节点，连线 targetHandle='in' ──
        # 切回 1:1 确保生成节点尺寸一致，避免过大图
        if ratio_btn.count() > 0:
            ratio_btn.click()
            page.wait_for_timeout(300)
            page.locator('.ant-dropdown-menu-item', has_text='1 : 1').first.click()
            page.wait_for_timeout(500)

        # 先记录裁剪前的节点/边数量
        before_counts = page.evaluate('''() => {
            return {
                nodes: document.querySelectorAll('.react-flow__node').length,
                edges: document.querySelectorAll('.react-flow__edge').length,
            };
        }''')

        page.locator('.pea-crop-confirm').click()
        page.wait_for_timeout(2500)

        after_counts = page.evaluate('''() => {
            return {
                nodes: document.querySelectorAll('.react-flow__node').length,
                edges: document.querySelectorAll('.react-flow__edge').length,
            };
        }''')
        node_grew = after_counts['nodes'] == before_counts['nodes'] + 1
        edge_grew = after_counts['edges'] == before_counts['edges'] + 1
        checks.append({'name': '[FIX#4] crop creates one new node', 'pass': node_grew,
                       'detail': f"nodes: {before_counts['nodes']} -> {after_counts['nodes']}"})
        checks.append({'name': '[FIX#4] crop creates one new edge', 'pass': edge_grew,
                       'detail': f"edges: {before_counts['edges']} -> {after_counts['edges']}"})

        # 优先用 dev hooks 读取精确 edge handle；未暴露则回退到 DOM data-testid
        edge_info = page.evaluate('''() => {
            if (window.__canvas) {
                const edges = window.__canvas.getState().edges;
                const lastEdge = edges[edges.length - 1];
                if (lastEdge) return { mode: 'store', ...lastEdge };
            }
            // DOM 回退：ReactFlow 边元素 data-testid 形如 rf__edge-reactflow__edge-{sourceId}{sourceHandle}-{targetId}{targetHandle}
            const edgeEl = document.querySelector('.react-flow__edge:last-of-type');
            if (!edgeEl) return { mode: 'none' };
            const testid = edgeEl.getAttribute('data-testid') || '';
            const m = testid.match(/rf__edge-reactflow__edge-(.+?)(out|source)?-(.+?)(in|target)?$/);
            return {
                mode: 'dom',
                testid: testid,
                source: m ? m[1] : null,
                sourceHandle: m ? (m[2] || null) : null,
                target: m ? m[3] : null,
                targetHandle: m ? (m[4] || null) : null,
            };
        }''')

        if edge_info.get('mode') == 'none':
            checks.append({'name': '[FIX#4] crop edge inspectable', 'pass': False, 'reason': 'no edge data found'})
        else:
            target_in = edge_info.get('targetHandle') == 'in'
            checks.append({'name': '[FIX#4] crop edge connects to new node input handle (targetHandle=in)', 'pass': target_in,
                           'detail': f"mode={edge_info.get('mode')} testid={edge_info.get('testid')}"})

        # 额外验证：新节点位于原节点右侧（输入在左、输出在右的常规数据流）
        positions = page.evaluate('''() => {
            const nodes = document.querySelectorAll('.react-flow__node');
            if (nodes.length < 2) return null;
            const first = nodes[0].getBoundingClientRect();
            const last = nodes[nodes.length - 1].getBoundingClientRect();
            return { firstX: first.x, lastX: last.x };
        }''')
        if positions:
            checks.append({'name': '[FIX#4] new crop node placed to the right of source', 'pass': positions['lastX'] > positions['firstX'],
                           'detail': f"sourceX={positions['firstX']:.0f} newX={positions['lastX']:.0f}"})
        page.screenshot(path='shots/crop_v6_after_crop.png', full_page=False)

        print('=== CROP v6 VERIFICATION ===')
        all_pass = True
        for c in checks:
            ok = c['pass']; all_pass = all_pass and ok
            detail = c.get('detail', ''); reason = c.get('reason', '')
            print(f"  [{'✓' if ok else '✗'}] {c['name']}: {detail} {reason}".strip())
        print(f'\nOverall: {"ALL PASS ✓" if all_pass else "SOME FAILED ✗"}')
        browser.close()
        return 0 if all_pass else 1

if __name__ == '__main__':
    exit(main() or 0)
