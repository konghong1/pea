"""
PeaNode 视觉回归 — 离线 (无后端)
================================
对 build 产物 dist/index.html (vite preview) 直接做以下断言：

A. 媒体节点 — 用户上传后左侧 Handle 必须隐藏
   - 模拟登录 → 注入 mock canvas (含 image/video/audio 已上传节点 + AI 结果节点) → 截图
   - 断言：上传节点的左侧 react-flow__handle 不存在；AI 结果节点有左侧 handle

B. 生成覆盖层 — 必须不显示提示词
   - 注入 mock canvas (含 generating=true 节点, prompt 字段填充)
   - 断言：.pea-node-gen-prompt 不在 DOM 中
   - 断言：.pea-node-generating 存在且包含 .tech-loader__svg

不依赖后端：fetch + axios 都 mock 成静态响应。
"""
import asyncio, json, sys, os, re
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "pea-server" / "web" / "dist"
INDEX = f"http://127.0.0.1:4123/"
SHOT_DIR = ROOT / "verify"
SHOT_DIR.mkdir(exist_ok=True)


# 伪造节点数据：覆盖所有需要验证的 kind（type 一律 'pea'，与 CanvasEditor nodeTypes 注册一致）
def mock_nodes():
    return [
        # 已上传 image — 应隐藏左侧 Handle
        {"id": "img-up", "type": "pea", "position": {"x": 40, "y": 40},
         "data": {"kind": "image", "fileKey": "uploads/i1.png", "prompt": "用户提示词A"}},
        # AI 结果 image — 应有左侧 Handle
        {"id": "img-ai", "type": "pea", "position": {"x": 40, "y": 240},
         "data": {"kind": "image", "resultUrl": "https://example.com/ai.png", "prompt": "AI提示词B"}},
        # 已上传 video
        {"id": "vid-up", "type": "pea", "position": {"x": 320, "y": 40},
         "data": {"kind": "video", "fileKey": "uploads/v1.mp4", "prompt": "用户提示词C"}},
        # 已上传 audio
        {"id": "aud-up", "type": "pea", "position": {"x": 600, "y": 40},
         "data": {"kind": "audio", "fileKey": "uploads/a1.mp3", "prompt": "用户提示词D"}},
        # 生成中（带 prompt）— 覆盖层不应回显 prompt
        {"id": "img-gen", "type": "pea", "position": {"x": 40, "y": 440},
         "data": {"kind": "image", "generating": True, "prompt": "生成中不应展示的提示词E",
                  "lastJobId": "job-1", "jobStartAt": 1700000000000}},
    ]


async def main():
    print("DEBUG: start main", flush=True)
    async with async_playwright() as p:
        print("DEBUG: got playwright", flush=True)
        browser = await p.chromium.launch()
        print("DEBUG: browser launched", flush=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        def on_reqfail(r):
            print(f"[reqfail] {r.url} - {r.failure}", flush=True)
        def on_res(r):
            if r.status >= 400:
                print(f"[res] {r.status} {r.url}", flush=True)
        def on_err(e):
            print(f"[pageerror] {e}", flush=True)
        def on_console(m):
            print(f"[console:{m.type}] {m.text}", flush=True)
        page.on("requestfailed", on_reqfail)
        page.on("response", on_res)
        page.on("pageerror", on_err)
        page.on("console", on_console)

        # 注入 store 初始态 + 假登录态（与 useAuth 一致用 pea_token / pea_user）
        await page.add_init_script("""
        window.localStorage.setItem('pea_token', 'fake.jwt.token');
        window.localStorage.setItem('pea_user', JSON.stringify({id:1, email:'t@x.com', displayName:'tester'}));
        window.localStorage.setItem('pea_ui_route', JSON.stringify({active:'canvas', canvasId:1}));
        """)

        # mock 路由：只拦 API 调用，**不要**拦 / 静态资源（HTML/JS/CSS）否则 SPA 启不来
        async def handle_route(route):
            url = route.request.url
            res = route.request.resource_type
            if res in ("document", "script", "stylesheet", "font", "image", "media"):
                # 放行静态资源 + HTML；favicon 404 也无所谓
                if url.endswith((".html", ".js", ".css", ".map", ".svg", ".png", ".jpg", ".ico")) or res == "document":
                    await route.continue_()
                else:
                    await route.continue_()
                return
            # API 拦截
            if "login" in url or "/auth/me" in url or "/users/me" in url or "/auth/refresh" in url or "/billing/balance" in url:
                await route.fulfill(json={"id": 1, "email": "t@x.com", "displayName": "tester",
                                          "balance": 999, "isAdmin": False, "planLevel": 0,
                                          "effectivePlanLevel": 0, "planExpiresAt": None})
            elif re.search(r"/canvases/\d+", url):
                await route.fulfill(json={"id": 1, "title": "reg", "version": 1,
                                          "graph_json": {"nodes": mock_nodes(), "edges": []}})
            elif re.search(r"/canvases(\?|$)", url) and not re.search(r"/canvases/\d+", url):
                await route.fulfill(json=[{"id": 1, "title": "reg", "version": 1, "scope": "personal"}])
            elif "file/url" in url or "signed" in url:
                await route.fulfill(json={"url": "https://placehold.co/200x120/1a1d24/d6dae2?text=uploaded"})
            elif "ws" in url.lower() or "socket" in url.lower():
                await route.abort()
            elif res == "fetch" or res == "xhr" or res == "other":
                # 兜底：其余 API（models/available, generation/jobs/*, plans 等）都返空 200，
                # 避免 vite preview fallthrough 出 401 把登录态踢掉
                body = "[]" if url.endswith(("s", "es")) or "list" in url else "{}"
                await route.fulfill(json=json.loads(body) if body.startswith("{") else json.loads(body))
            else:
                await route.continue_()
        await page.route("**/*", handle_route)

        await page.goto(INDEX, wait_until="networkidle")
        print("DEBUG: goto done", flush=True)
        title = await page.title()
        print(f"DEBUG: title={title!r}", flush=True)
        body_html = await page.content()
        print(f"DEBUG: body_len={len(body_html)}, first 500={body_html[:500]!r}", flush=True)
        await page.wait_for_timeout(2500)

        # 等待节点出现（生成节点轮询会一直跑，但节点本身要等 openCanvas 完成）
        try:
            await page.wait_for_selector(".pea-node", timeout=25000)
        except Exception as e:
            await page.screenshot(path=str(SHOT_DIR / "fail_no_nodes.png"), full_page=True)
            html = await page.content()
            print(f"DEBUG: body tail = ...{html[-1500:]!r}", flush=True)
            print(f"❌ 节点未渲染：{e}")
            return 2

        # 截图：全画布
        await page.screenshot(path=str(SHOT_DIR / "reg_full.png"), full_page=True)

        # 断言 A：上传节点的左侧 Handle 数量 = 0；AI 节点的左侧 Handle 数量 = 1
        results = {}
        for nid, want_left in [
            ("img-up", 0), ("vid-up", 0), ("aud-up", 0), ("img-ai", 1)
        ]:
            node = page.locator(f'[data-id="{nid}"]')
            try:
                await node.wait_for(timeout=4000)
                left = await node.locator(".react-flow__handle-left").count()
                results[nid] = (left, want_left, left == want_left)
            except Exception as e:
                results[nid] = (-1, want_left, False)
                print(f"⚠️ 节点 {nid} 找不到：{e}")

        # 断言 B：生成态节点的 .pea-node-gen-prompt 不存在
        gen = page.locator('[data-id="img-gen"]')
        gen_prompt_count = -1
        loader_count = -1
        try:
            await gen.wait_for(timeout=4000)
            gen_prompt_count = await gen.locator(".pea-node-gen-prompt").count()
            loader_count = await gen.locator(".tech-loader__svg").count()
        except Exception as e:
            print(f"⚠️ 生成态节点找不到：{e}")

        results["img-gen_prompt_echo"] = (gen_prompt_count, 0, gen_prompt_count == 0)
        results["img-gen_tech_loader"] = (loader_count, 1, loader_count >= 1)

        # 输出
        all_pass = True
        for k, (got, want, ok) in results.items():
            mark = "✅" if ok else "❌"
            print(f"{mark} {k}: 实际={got} 期望={want}")
            if not ok:
                all_pass = False

        # 单节点特写截图
        for nid in ["img-up", "img-ai", "vid-up", "aud-up", "img-gen"]:
            try:
                el = page.locator(f'[data-id="{nid}"]')
                await el.screenshot(path=str(SHOT_DIR / f"reg_{nid}.png"))
            except Exception:
                pass

        await browser.close()
        return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
