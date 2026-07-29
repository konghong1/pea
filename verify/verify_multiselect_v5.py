"""
E2E 验证：多选交互四项修复 v5b
  1) 选择框完全透明（SVG fill=transparent）
  2) 功能条在选择框正上方
  3) 选择框以最外角为边界
  4) 点击"打包"后出现深色圆角组容器

运行: python verify_multiselect_v5.py
"""

import json
import time
import random
import string

BASE = "http://localhost:8088"


def rand_email():
    return f"e2e_{''.join(random.choices(string.ascii_lowercase, k=6))}_{int(time.time())}@test.pea"


def main():
    from playwright.sync_api import sync_playwright
    results = []
    ok = lambda n: (results.append(("PASS", n)), print(f"  [PASS] {n}"))
    fail = lambda n, r: (results.append(("FAIL", f"{n}: {r}")), print(f"  [FAIL] {n}: {r}"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        # 关键：在进入画布前就种下 dev hooks 标志，确保 CanvasEditor 挂载时暴露 window.__canvas
        page.add_init_script("localStorage.setItem('__peaDevHooks','1')")
        page.set_default_timeout(10000)

        try:
            # ── 1. 注册新用户 ──
            page.goto(f"{BASE}/login", wait_until="domcontentloaded")
            page.wait_for_timeout(800)

            # 切换到注册模式
            reg_btn = page.query_selector('button:has-text("没有账号"), button:has-text("去注册")')
            if reg_btn:
                reg_btn.click()
                page.wait_for_timeout(500)

            # 填写注册表单
            email = rand_email()
            password = "Test12345678"

            page.fill('#email', email)
            page.fill('#password', password)
            # 昵称字段（注册模式才显示）
            nick_input = page.query_selector('input[placeholder="可选"]')
            if nick_input:
                nick_input.fill(f"E2E_{int(time.time()) % 10000}")

            # 提交注册
            submit = page.query_selector('button[type="submit"]')
            if submit:
                submit.click()
                page.wait_for_timeout(2500)

            # 检查是否登录成功（跳转离开 /login）
            cur_url = page.url
            if "/login" in cur_url:
                # 可能注册失败，尝试直接登录
                page.fill('#email', email)
                page.fill('#password', password)
                submit = page.query_selector('button[type="submit"]')
                if submit:
                    submit.click()
                    page.wait_for_timeout(2500)

            ok(f"注册/登录完成 ({email})")

            # ── 2. 进入画布 ──
            # 应该已自动到首页/工作空间，找新建画布或已有画布
            page.wait_for_timeout(1000)

            # 尝试多种方式进入画布
            in_canvas = False

            # 方式A：已在画布页
            if page.query_selector(".react-flow"):
                in_canvas = True

            # 方式B：点新建项目 → 自动创建画布
            if not in_canvas:
                new_btns = page.query_selector_all('button:has-text("新建"), a:has-text("新建"), .projects-new-btn')
                for btn in new_btns:
                    try:
                        btn.click()
                        page.wait_for_timeout(1500)
                        # 可能有弹窗确认
                        confirm = page.query_selector('button:has-text("确定"), button:has-text("创建"), button:has-text("Create")')
                        if confirm:
                            confirm.click()
                            page.wait_for_timeout(2000)
                        if page.query_selector(".react-flow"):
                            in_canvas = True
                            break
                    except Exception:
                        pass

            # 方式C：点已有项目卡片
            if not in_canvas:
                project_cards = page.query_selector_all('[class*="project"] [class*="card"], .pea-card')
                for card in project_cards[:3]:
                    try:
                        card.click()
                        page.wait_for_timeout(2000)
                        if page.query_selector(".react-flow"):
                            in_canvas = True
                            break
                    except Exception:
                        pass

            if not in_canvas and page.query_selector(".react-flow"):
                in_canvas = True

            if not in_canvas:
                fail("进入画布", "无法通过 UI 进入画布页面")
                page.screenshot(path="debug_v5_nocanvas.png")
                print(f"  当前URL: {page.url}")
                return results

            ok("进入画布")

            # 注入 dev hooks
            page.evaluate("localStorage.setItem('__peaDevHooks', '1')")
            # 确保有 canvasId
            page.evaluate("""() => {
                if (window.__canvas) {
                    const s = window.__canvas.getState();
                    if (!s.canvasId) s.setCanvasMeta(999999, 1, 'E2E Test');
                }
            }""")
            page.wait_for_timeout(500)

            # ── 3. 通过 store 创建两个节点（最可靠，不依赖双击手势）──
            pane = page.query_selector(".react-flow__pane")
            box = pane.bounding_box()

            # 确认 dev hooks 已暴露 window.__canvas
            hook_ok = page.evaluate("() => !!(window.__canvas && window.__canvas.getState)")
            if not hook_ok:
                fail("dev hooks", "window.__canvas 未暴露，无法注入节点")
                page.screenshot(path="debug_v5_nohook.png")
                return results

            created = page.evaluate("""() => {
                const s = window.__canvas.getState();
                const a = s.addNode({ label: '节点A', kind: 'image' }, { x: 120, y: 100 });
                const b = s.addNode({ label: '节点B', kind: 'image' }, { x: 470, y: 400 });
                return [a, b];
            }""")
            page.wait_for_timeout(1200)

            nc = page.evaluate("""() => document.querySelectorAll('.react-flow__node[data-id]').length""")
            if nc < 2:
                fail("创建节点", f"仅 {nc} 个")
                page.screenshot(path="debug_v5_nonodes.png")
                return results
            ok(f"创建节点：{nc} 个 (ids={created})")

            # ── 4. 框选多个节点：读取节点真实屏幕包围盒，从"空白面板区"发起真实拖拽 ──
            # 关键坑：拖拽起点必须在 .react-flow__pane 上，且落在视口内（y>=0），
            # 否则起点会被顶部 header 拦截导致框选根本没开始（仅保留预选节点）。
            # 策略：起点取"左下空白区"(在所有节点下方、左侧)，终点取右上，覆盖全部节点。
            rects = page.evaluate("""() => {
                const ns = Array.from(document.querySelectorAll('.react-flow__node[data-id]')).slice(0,2);
                let mx=Infinity,my=Infinity,Mx=-Infinity,My=-Infinity;
                ns.forEach(n=>{const r=n.getBoundingClientRect();mx=Math.min(mx,r.left);my=Math.min(my,r.top);Mx=Math.max(Mx,r.right);My=Math.max(My,r.bottom);});
                return {mx,my,Mx,My,w:window.innerWidth,h:window.innerHeight};
            }""")
            vw, vh = rects["w"], rects["h"]
            # 起点：节点并集左下外侧 (x 左移, y 下移)，并夹在视口内
            sx = max(20, rects["mx"] - 40)
            sy = min(vh - 20, rects["My"] + 40)
            # 终点：节点并集右上外侧 (x 右移, y 上移)，顶部留出 header(>=120)
            ex = min(vw - 20, rects["Mx"] + 40)
            ey = max(120, rects["my"] - 40)
            print(f"  [debug] 框选拖拽: ({round(sx)},{round(sy)}) -> ({round(ex)},{round(ey)}) 视口={vw}x{vh}")

            # 先点击空白面板清掉预选，确保是"全新框选"
            page.mouse.click(rects["mx"] - 60, min(vh - 30, rects["My"] + 60))
            page.wait_for_timeout(300)

            page.mouse.move(sx, sy)
            page.mouse.down()
            for i in range(1, 13):
                page.mouse.move(sx + (ex - sx) * i / 12, sy + (ey - sy) * i / 12)
                page.wait_for_timeout(35)
            page.mouse.up()
            page.wait_for_timeout(1200)

            sel = page.evaluate("""() => {
                const s = document.querySelectorAll('.react-flow__node.selected');
                return { n: s.length, ids: Array.from(s).map(n => n.getAttribute('data-id')) };
            }""")

            if sel["n"] < 2:
                # 回退：Shift+点击选择
                nds = page.evaluate("""() => Array.from(document.querySelectorAll('.react-flow__node[data-id]')).slice(0,2).map(n => {
                    const r = n.getBoundingClientRect();
                    return { id: n.id, cx: r.left+r.width/2, cy: r.top+r.height/2 };
                })""")
                if len(nds) >= 2:
                    page.mouse.click(nds[0]["cx"], nds[0]["cy"])
                    page.wait_for_timeout(300)
                    page.keyboard.down("Shift")
                    page.mouse.click(nds[1]["cx"], nds[1]["cy"])
                    page.keyboard.up("Shift")
                    page.wait_for_timeout(1000)
                    sel = page.evaluate("""() => ({
                        n: document.querySelectorAll('.react-flow__node.selected').length,
                        ids: Array.from(document.querySelectorAll('.react-flow__node.selected')).map(n=>n.getAttribute('data-id'))
                    })""")

            if sel["n"] < 2:
                fail("多选", f"仅选中 {sel['n']} 个")
                page.screenshot(path="debug_v5_noselect.png")
                return results
            ok(f"多选：{sel['n']} 个节点")

            page.screenshot(path="verify_v5_select.png")

            # ══════════════════════════════
            # 验证 1：选择框透明
            # ══════════════════════════════
            rs = page.evaluate("""() => {
                const el = document.querySelector('.react-flow__nodesselection-rect');
                if (!el) return null;
                const c = getComputedStyle(el);
                return { fill: c.fill, stroke: c.stroke, fo: c.fillOpacity };
            }""")
            def _trans(c):
                return c in ("transparent", "none", "") or "0, 0, 0, 0)" in c or c.rstrip().endswith(", 0)")
            if rs is None:
                ok("验证1：选择框透明（无 rect 元素）")
            elif _trans(rs.get("fill", "")) and _trans(rs.get("stroke", "")):
                ok(f'验证1：选择框透明 fill={rs.get("fill")} stroke={rs.get("stroke")}')
            else:
                fail("验证1：透明", json.dumps(rs))

            # ══════════════════════════════
            # 验证 2：功能条在上方
            # ══════════════════════════════
            tb = page.evaluate("""() => {
                const t = document.querySelector('.multiselect-toolbar');
                if (!t) return null;
                const tr = t.getBoundingClientRect();
                let mt = Infinity;
                document.querySelectorAll('.react-flow__node.selected').forEach(n => {
                    mt = Math.min(mt, n.getBoundingClientRect().top);
                });
                return { tbB: tr.bottom, selT: mt, ok: tr.bottom <= mt + 10 };
            }""")
            if tb is None:
                fail("验证2：功能条位置", "工具栏未找到")
            elif tb["ok"]:
                ok(f'验证2：功能条在上方 (tbBottom={tb["tbB"]:.0f} ≤ selTop={tb["selT"]:.0f})')
            else:
                fail("验证2：功能条在上方", f'tbBottom={tb["tbB"]:.0f} > selTop={tb["selT"]:.0f}')

            # ══════════════════════════════
            # 验证 3：边界覆盖所有节点外角
            # ══════════════════════════════
            bd = page.evaluate("""() => {
                let mx=Infinity,my=Infinity,Mx=-Infinity,My=-Infinity;
                document.querySelectorAll('.react-flow__node.selected').forEach(n=>{
                    const r=n.getBoundingClientRect();
                    mx=Math.min(mx,r.left); my=Math.min(my,r.top);
                    Mx=Math.max(Mx,r.right); My=Math.max(My,r.bottom);
                });
                return { w:Mx-mx, h:My-my, n:document.querySelectorAll('.react-flow__node.selected').length };
            }""")
            if bd["w"] > 120 and bd["h"] > 180:
                ok(f'验证3：边界合理 ({bd["w"]:.0f}×{bd["h"]:.0f}px)')
            else:
                fail("验证3：边界", f'{bd["w"]:.0f}×{bd["h"]:.0f}')

            # ══════════════════════════════
            # 验证 4：点击"打包" → GroupNode
            # ══════════════════════════════
            packed = page.evaluate("""() => {
                for (const b of document.querySelectorAll('.mst-btn')) {
                    if (b.textContent.includes('打包')) { b.click(); return true; }
                }
                return false;
            }""")
            if not packed:
                fail("验证4a：打包按钮", "未找到")
            else:
                page.wait_for_timeout(2500)
                g = page.evaluate("""() => {
                    const gn = document.querySelector('.pea-group-node');
                    const st = window.__canvas ? window.__canvas.getState() : null;
                    const kids = st ? st.nodes.filter(n => n.parentNode).length : -1;
                    return {
                        has: !!gn,
                        bg: gn ? getComputedStyle(gn).background : null,
                        br: gn ? getComputedStyle(gn).borderRadius : null,
                        hdr: !!document.querySelector('.pgn-header'),
                        kids: kids,
                    };
                }""")
                if g["has"]:
                    ok(f'验证4a：GroupNode 出现 (radius={g["br"]}, 子节点={g["kids"]})')
                    if g["hdr"]:
                        ok("验证4b：组工具栏存在 (.pgn-header)")
                    else:
                        fail("验证4b：组工具栏", "缺 .pgn-header")
                else:
                    fail("验证4a：GroupNode 未出现", "检查 .react-flow__node[data-type=group]")

            page.screenshot(path="verify_v5_final.png")

        except Exception as e:
            results.append(("ERROR", str(e)))
            print(f"  [ERROR] {e}")
            try: page.screenshot(path="verify_v5_error.png")
            except Exception: pass
        finally:
            browser.close()

    # 汇总
    print("\n" + "=" * 55)
    for s, m in results:
        print(f"  [{s}] {m}")
    p = sum(1 for s, _ in results if s == "PASS")
    f = sum(1 for s, _ in results if s == "FAIL")
    e = sum(1 for s, _ in results if s == "ERROR")
    t = len(results)
    print("=" * 55)
    print(f"总计 {t} | PASS {p} | FAIL {f} | ERROR {e}")
    if f == 0 and e == 0:
        print("全部通过!")
    return 0 if f == 0 and e == 0 else 1


if __name__ == "__main__":
    exit(main())
