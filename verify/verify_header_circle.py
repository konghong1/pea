"""验证 CanvasHeader 改圆形按钮 + 409 自动重试修复。

覆盖:
  1. 按钮几何 (40x40 / border-radius: 50%)。
  2. hover Tooltip 显示「画布名 · 上次修改于 X 分钟前」。
  3. 点击展开下拉面板。
  4. 模拟 409 响应：触发 autosave → 验证不弹"画布已被他人更新"、version 自动 GET 同步后重试成功。
"""
import json
import time
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8088"
OUT_DIR = "D:/workspace/pea/verify"


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.on(
            "console",
            lambda m: print(f"[c:{m.type}] {m.text}") if m.type in ("error", "warning") else None,
        )
        page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        # ── 注册/登录 ──────────────────────────────────────────
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        try:
            page.locator("text=没有账号？去注册").first.click(timeout=4000)
            page.wait_for_timeout(400)
            email = f"hdr_{uuid.uuid4().hex[:8]}@pea.ai"
            page.fill('input[placeholder="you@pea.ai"]', email)
            page.fill('input[placeholder="至少 8 位"]', "test1234")
            page.fill('input[placeholder="可选"]', "Dbg")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(2000)
            page.wait_for_selector("text=新建项目", timeout=15000)
        except Exception as e:
            print("register skipped:", repr(e))

        # ── 创建画布 ──────────────────────────────────────────
        title = "圆形按钮验证画布"
        cid = page.evaluate(
            """async (title) => {
                const token = localStorage.getItem('pea_token');
                const r = await fetch('/api/canvases', {
                    method:'POST',
                    headers:{'Content-Type':'application/json', ...(token?{Authorization:`Bearer ${token}`}:{})},
                    body: JSON.stringify({title, scope:'personal'})
                });
                const t = await r.text();
                try { return JSON.parse(t).id; } catch(e){ return 'ERR:'+t.slice(0,200); }
            }""",
            title,
        )
        print("canvas id:", cid)

        # 打开画布
        page.goto(f"{BASE}/workspace", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.locator(f'[data-canvas-id="{cid}"]').first.click(timeout=8000)
        page.wait_for_timeout(2500)

        # 校验画布编辑器已挂载
        if not page.locator(".react-flow").first.is_visible(timeout=6000):
            page.screenshot(path=f"{OUT_DIR}/_diag_no_editor.png")
            raise SystemExit("editor not opened")

        # ── 1. 按钮几何验证 ─────────────────────────────────────
        trigger = page.locator(".pea-canvas-header-trigger").first
        trigger.wait_for(state="visible", timeout=5000)
        box = trigger.bounding_box()
        cs = page.evaluate(
            """() => {
                const el = document.querySelector('.pea-canvas-header-trigger');
                if (!el) return null;
                const cs = getComputedStyle(el);
                return {
                    w: cs.width, h: cs.height, radius: cs.borderRadius,
                    bg: cs.backgroundColor, padding: cs.padding,
                };
            }"""
        )
        print(f"trigger box: {box}")
        print(f"trigger css: {cs}")
        # 期望 40x40, 圆角 50%
        assert cs and "40px" in cs["w"] and "40px" in cs["h"], f"按钮宽高不符合 40x40: {cs}"
        assert cs["radius"].startswith("50%") or "20" in cs["radius"], f"圆角不是 50%: {cs['radius']}"
        # 旧版的长条: min-width 220px, 新版应不再有
        # 触发器中应只剩 logo（无标题/时间/caret）
        inner = page.evaluate(
            """() => {
                const t = document.querySelector('.pea-canvas-header-trigger');
                if (!t) return null;
                return {
                    hasLogo: !!t.querySelector('img.pea-canvas-header-logo'),
                    hasTitleText: t.textContent && t.textContent.trim().length > 2,
                    childCount: t.children.length,
                };
            }"""
        )
        print(f"trigger inner: {inner}")
        assert inner and inner["hasLogo"], "圆形按钮内必须有 logo"
        assert not inner["hasTitleText"], f"按钮内不应有标题文字: {inner}"
        assert inner["childCount"] == 1, f"按钮应只含 1 个子节点（logo），实际 {inner['childCount']}"

        # 截图1：默认态
        page.screenshot(path=f"{OUT_DIR}/shot_header_circle.png")

        # ── 2. hover Tooltip ─────────────────────────────────────
        trigger.hover()
        page.wait_for_timeout(500)
        # antd Tooltip 渲染到 body 上
        tip = page.evaluate(
            """() => {
                const tips = document.querySelectorAll('.ant-tooltip-inner');
                if (!tips.length) return null;
                const t = tips[tips.length - 1];
                return t.textContent || '';
            }"""
        )
        print(f"hover tooltip: {tip!r}")
        assert tip and "圆形按钮验证画布" in tip, f"Tooltip 应包含画布名: {tip!r}"
        assert tip and ("修改" in tip or "尚未保存" in tip), f"Tooltip 应包含修改时间: {tip!r}"
        # 截图2：hover 态（截画布左上角 + tooltip 范围）
        page.screenshot(path=f"{OUT_DIR}/shot_header_hover.png")

        # 移开 hover
        page.mouse.move(700, 500)
        page.wait_for_timeout(400)

        # ── 3. 点击下拉 ─────────────────────────────────────────
        trigger.click()
        page.wait_for_timeout(400)
        drop_open = page.evaluate(
            """() => {
                const t = document.querySelector('.pea-canvas-header-trigger');
                const d = document.querySelector('.pea-canvas-dropdown');
                return {
                    ariaExpanded: t ? t.getAttribute('aria-expanded') : null,
                    dropdownVisible: !!d,
                    dropdownHasTitle: d ? !!d.querySelector('.pea-canvas-dropdown-head') : false,
                };
            }"""
        )
        print(f"dropdown state: {drop_open}")
        assert drop_open["ariaExpanded"] == "true", "点击后 aria-expanded 应为 true"
        assert drop_open["dropdownVisible"], "点击后下拉面板应出现"
        assert drop_open["dropdownHasTitle"], "下拉面板头部应保留画布名 + 修改时间"
        # 截图3：下拉打开
        page.screenshot(path=f"{OUT_DIR}/shot_header_dropdown.png")

        # ESC 关闭
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        # ── 4. 409 自动重试验证 ──────────────────────────────────
        # 策略：拦截 PUT /api/canvases/<id> 一次返回 409，下一次 200，
        # 同时记录弹出的 message.warning 文案。
        # 预期：autosave 收到 409 → 自动 GET 拉新 version → 重试成功 → 无"画布已被他人更新"提示。

        # 先拿一个 node 来拖一下，触发 dirty
        # 直接改 store 让 dirty=true 即可（更快）：用 dev hook 改本地 store
        page.evaluate(
            """(cid) => {
                window.__canvas.getState().setCanvasMeta(cid, 1, '圆形按钮验证画布');
            }""",
            cid,
        )
        page.wait_for_timeout(200)

        # 拦截：第一次返回 409（含 currentVersion=2），之后放行
        conflict_msg = []
        def handle_put(route, request):
            body = request.post_data or ""
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
            # 第 1 次返回 409，后端语义带 currentVersion
            if not getattr(handle_put, 'first_done', False):
                handle_put.first_done = True
                route.fulfill(
                    status=409,
                    content_type='application/json',
                    body=json.dumps({
                        "message": "canvas version conflict",
                        "currentVersion": 2,
                    }),
                )
            else:
                route.continue_()

        page.route(f"**/api/canvases/{cid}", handle_put)

        # 监听 antd message.warning 的文案（通过在 document 注入 hook）
        page.evaluate(
            """() => {
                window.__capturedWarnings = [];
                const orig = console.warn;
                // antd message 用 rc-notification 触发，最稳妥的检测是盯一个全局派发的事件
                // 这里用 MutationObserver 扫所有弹出元素文字
                const obs = new MutationObserver(() => {
                    document.querySelectorAll('.ant-message-notice-warning, .ant-message-warning').forEach(n => {
                        const txt = (n.textContent || '').trim();
                        if (txt && !window.__capturedWarnings.includes(txt)) {
                            window.__capturedWarnings.push(txt);
                        }
                    });
                    document.querySelectorAll('.ant-message-notice').forEach(n => {
                        const txt = (n.textContent || '').trim();
                        if (txt && (txt.includes('他人') || txt.includes('别人') || txt.includes('版本')) && !window.__capturedWarnings.includes(txt)) {
                            window.__capturedWarnings.push(txt);
                        }
                    });
                });
                obs.observe(document.body, {childList: true, subtree: true});
            }"""
        )

        # 触发 dirty：直接调 store 的 updateNodeData，让 dirty 翻为 true
        # 用一个临时节点即可
        page.evaluate(
            """(cid) => {
                const s = window.__canvas.getState();
                s.setCanvasMeta(cid, 1, '圆形按钮验证画布');
                s.onNodesChange([{type:'position', id:'n1', position:{x:0,y:0}, dragging:false}]);
            }""",
            cid,
        )
        # dirty=true 后 1s autosave 触发 → PUT 被拦截 → 409 → 进入重试分支
        # 重试分支：GET 拿 currentVersion=2 → PUT 再来一次（这次放行）→ 200 → markSaved
        # 整个流程 ~2s
        page.wait_for_timeout(3000)

        captured = page.evaluate("() => window.__capturedWarnings || []")
        print(f"captured warnings: {captured}")

        # 检查 version 已经被 GET 同步 + 重试成功
        state = page.evaluate(
            """() => {
                const s = window.__canvas.getState();
                return { version: s.version, dirty: s.dirty, lastSavedAt: s.lastSavedAt };
            }"""
        )
        print(f"final state: {state}")

        # 关键断言：不应再出现"画布已被他人更新"
        bad = [w for w in captured if "画布已被他人更新" in w or "被别人" in w]
        assert not bad, f"不应再弹出'画布已被他人更新'，实际捕获: {bad}"

        # version 应被 GET 同步为 2（handle_put 第一次 409 返回 currentVersion=2）
        # 重试第二次的 PUT 已放行（200），markSaved 会把 version 再 +1 → 实际是 3
        # 但更稳的断言：version >= 2（至少发生了 GET 同步）
        assert state["version"] >= 2, f"version 应已被同步到 ≥ 2，实际: {state['version']}"
        assert state["dirty"] is False, f"重试成功后 dirty 应为 false，实际: {state['dirty']}"

        # 截图4：保存成功后状态
        page.screenshot(path=f"{OUT_DIR}/shot_header_409_recovered.png")

        print("\n✅ 全部断言通过")
        print("截图：")
        print(f"  - {OUT_DIR}/shot_header_circle.png       (默认态)")
        print(f"  - {OUT_DIR}/shot_header_hover.png        (hover Tooltip)")
        print(f"  - {OUT_DIR}/shot_header_dropdown.png     (下拉打开)")
        print(f"  - {OUT_DIR}/shot_header_409_recovered.png (409 自动恢复后)")

        browser.close()


if __name__ == "__main__":
    main()
