"""
上传素材节点 —— 选中时不弹「下方编辑框」全类型回归（离线，无后端）
================================================================================
需求：用户自己上传的节点，点击选中时不需要出现下方的编辑框（NodeChatPrompt）。
要求覆盖所有节点类型，逐一验证。

断言矩阵（每个节点单独点击 → 检查其 anchor 下的 .node-input-bar）：

  A. 上传素材节点（fileKey 或 url，无生成结果） → 编辑框必须【不出现】
     image / video / audio，含 blob url 形式
  B. AI 生成结果节点（resultUrl / resultUrls）   → 编辑框必须【出现】
  C. 空白待生成节点（无素材无结果）              → 编辑框必须【出现】
  D. 生成中的上传节点（generating=true）         → 编辑框必须【出现】
     ⚠️ 历史回归护栏：生成中编辑框是「停止」按钮唯一入口，且卸载会带走提示词
  E. 其余所有 kind（text/generate/agent/story/
     world3d/camera/light/playlist/replace/ref） → 编辑框必须【出现】
  F. 左侧 target Handle：上传节点=0，其余=1（与编辑框规则同源，防两套判定漂移）

运行：
  1) cd pea-server/web && npm run build
  2) npx vite preview --port 4123 --strictPort   （脚本会自动尝试拉起）
  3) python verify/verify_upload_no_editor.py
"""
import asyncio
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "pea-server" / "web"
PORT = 4123
INDEX = f"http://127.0.0.1:{PORT}/"
SHOT_DIR = ROOT / "verify"
SHOT_DIR.mkdir(exist_ok=True)

COL = 460
ROW = 520

# (id, data, 期望出现编辑框, 期望左侧 handle 数)
CASES = [
    # ── A. 用户上传素材：编辑框必须不出现 ──────────────────────────────
    ("img-up",  {"kind": "image", "fileKey": "uploads/i1.png"},          False, 0),
    ("vid-up",  {"kind": "video", "fileKey": "uploads/v1.mp4"},          False, 0),
    ("aud-up",  {"kind": "audio", "fileKey": "uploads/a1.mp3"},          False, 0),
    ("img-url", {"kind": "image", "url": "https://placehold.co/200x120"}, False, 0),
    # ── B. AI 生成结果：编辑框必须出现（可继续改词重生成）──────────────
    ("img-ai",  {"kind": "image", "resultUrl": "https://placehold.co/200x120"}, True, 1),
    ("vid-ai",  {"kind": "video", "resultUrls": ["https://placehold.co/200x120"]}, True, 1),
    # ── C. 空白待生成节点：编辑框必须出现 ──────────────────────────────
    ("img-empty", {"kind": "image"}, True, 1),
    ("vid-empty", {"kind": "video"}, True, 1),
    ("aud-empty", {"kind": "audio"}, True, 1),
    # ── D. 生成中的上传节点：编辑框必须出现（停止按钮 + 防提示词丢失）──
    #    lastJobId 必填，否则 store.reconcileGeneratingNodes 会把孤儿 generating 清零，
    #    节点退化成普通上传态，用例就测不到想测的分支了。
    #    左侧 handle 仍为 0：上传素材节点内容源自文件，任何时候都不接受上游入边。
    ("img-up-gen", {"kind": "image", "fileKey": "uploads/i2.png", "generating": True,
                    "lastJobId": "job-up-gen", "prompt": "生成中的提示词"}, True, 0),
    ("img-gen", {"kind": "image", "generating": True, "lastJobId": "job-gen",
                 "prompt": "空节点生成中"}, True, 1),
    # ── E. 其余全部 kind：编辑框必须出现 ───────────────────────────────
    ("n-text",     {"kind": "text", "html": "文本"}, True, 1),
    ("n-generate", {"kind": "generate"}, True, 1),
    ("n-agent",    {"kind": "agent"}, True, 1),
    ("n-story",    {"kind": "story"}, True, 1),
    ("n-world3d",  {"kind": "world3d"}, True, 1),
    ("n-camera",   {"kind": "camera"}, True, 1),
    ("n-light",    {"kind": "light"}, True, 1),
    ("n-playlist", {"kind": "playlist"}, True, 1),
    ("n-replace",  {"kind": "replace"}, True, 1),
    ("n-ref",      {"kind": "ref"}, True, 1),
]


def mock_nodes():
    nodes = []
    for i, (nid, data, _want_editor, _want_handle) in enumerate(CASES):
        nodes.append({
            "id": nid,
            "type": "pea",
            "position": {"x": (i % 5) * COL, "y": (i // 5) * ROW},
            "data": {"label": nid, **data},
        })
    return nodes


def ensure_preview():
    """确保 vite preview 已在 4123 提供 dist 产物；未启动则拉起。"""
    try:
        with urllib.request.urlopen(INDEX, timeout=2) as r:
            if r.status == 200:
                print(f"· preview 已在 {INDEX} 运行")
                return None
    except Exception:
        pass
    # 用标准库静态服务 dist（比 npx vite preview 更稳，且本应用用 localStorage 路由，
    # 不依赖 SPA history fallback）。
    dist = WEB / "dist"
    if not (dist / "index.html").exists():
        raise RuntimeError(f"未找到构建产物 {dist}/index.html，请先 npm run build")
    print(f"· 拉起静态服务 :{PORT} （dist）…")
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=str(dist), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(INDEX, timeout=2) as r:
                if r.status == 200:
                    print("· preview 就绪")
                    return proc
        except Exception:
            continue
    raise RuntimeError("vite preview 启动失败")


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda e: print(f"[pageerror] {e}", flush=True))

        await page.add_init_script("""
        window.localStorage.setItem('pea_token', 'fake.jwt.token');
        window.localStorage.setItem('pea_user', JSON.stringify({id:1, email:'t@x.com', displayName:'tester'}));
        window.localStorage.setItem('pea_ui_route', JSON.stringify({active:'canvas', canvasId:1}));
        """)

        async def handle_route(route):
            url = route.request.url
            res = route.request.resource_type
            if res in ("document", "script", "stylesheet", "font", "image", "media"):
                await route.continue_()
                return
            if any(k in url for k in ("login", "/auth/me", "/users/me", "/auth/refresh", "/billing/balance")):
                await route.fulfill(json={"id": 1, "email": "t@x.com", "displayName": "tester",
                                          "balance": 999, "isAdmin": False, "planLevel": 0,
                                          "effectivePlanLevel": 0, "planExpiresAt": None})
            elif re.search(r"/canvases/\d+", url):
                await route.fulfill(json={"id": 1, "title": "reg", "version": 1,
                                          "graph_json": {"nodes": mock_nodes(), "edges": []}})
            elif re.search(r"/canvases(\?|$)", url):
                await route.fulfill(json=[{"id": 1, "title": "reg", "version": 1, "scope": "personal"}])
            elif "/files/upload" in url:
                await route.fulfill(json={"key": "uploads/mock-upload.png"})
            elif "/generation/jobs/" in url:
                # 保持 running：让生成中节点不被 reconcile 清零
                await route.fulfill(json={"id": "job-x", "status": "running"})
            elif "file/url" in url or "signed" in url or "/files/" in url:
                await route.fulfill(json={"url": "https://placehold.co/200x120/1a1d24/d6dae2?text=uploaded"})
            elif "ws" in url.lower() or "socket" in url.lower():
                await route.abort()
            elif res in ("fetch", "xhr", "other"):
                body = [] if (url.rstrip("/").endswith(("s", "es")) or "list" in url) else {}
                await route.fulfill(json=body)
            else:
                await route.continue_()

        await page.route("**/*", handle_route)
        await page.goto(INDEX, wait_until="networkidle")

        try:
            await page.wait_for_selector(".pea-node", timeout=25000)
        except Exception as e:
            await page.screenshot(path=str(SHOT_DIR / "upload_editor_fail_no_nodes.png"), full_page=True)
            print(f"❌ 节点未渲染: {e}")
            return 2
        await page.wait_for_timeout(1200)
        # 缩小到能一次点到所有节点
        await page.keyboard.press("Escape")
        await page.screenshot(path=str(SHOT_DIR / "upload_editor_overview.png"))

        results = []
        for nid, _data, want_editor, want_handle in CASES:
            node = page.locator(f'.react-flow__node[data-id="{nid}"]')
            try:
                await node.wait_for(timeout=5000)
            except Exception:
                results.append((nid, "节点未渲染", "-", False))
                continue

            # 左侧 target handle 数量（与编辑框规则同源）
            got_handle = await node.locator(".react-flow__handle-left").count()

            # 点击选中：依次尝试几个落点，避开 <audio controls> / 结果工具条等会吞事件的子元素
            box = await node.bounding_box()
            if not box:
                results.append((nid, "无 bounding box", "-", False))
                continue
            selected = 0
            for fx, fy in ((0.5, 0.62), (0.5, 0.12), (0.12, 0.5)):
                await page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
                await page.wait_for_timeout(380)
                selected = await page.locator(
                    f'.react-flow__node[data-id="{nid}"] .pea-node.selected'
                ).count()
                if selected == 1:
                    break
            # 该节点 anchor 下的编辑框
            scoped = await page.locator(
                f'[data-pea-anchor="{nid}"] .node-input-bar'
            ).count()
            # 全局编辑框数量（确保没有渲染到别的地方去）
            globl = await page.locator(".node-input-bar").count()

            got_editor = scoped > 0
            ok = (got_editor == want_editor) and (got_handle == want_handle) and selected == 1
            if want_editor is False and globl > 0:
                ok = False
            results.append((
                nid,
                f"编辑框={'有' if got_editor else '无'} handle={got_handle} 选中={selected} 全局编辑框={globl}",
                f"编辑框={'有' if want_editor else '无'} handle={want_handle} 选中=1",
                ok,
            ))

            if nid in ("img-up", "img-ai", "vid-up", "img-up-gen"):
                try:
                    await page.screenshot(path=str(SHOT_DIR / f"upload_editor_{nid}.png"))
                except Exception:
                    pass

        # ── Phase 2：数据安全护栏 ────────────────────────────────────────
        # 场景：空图片节点里先写提示词 → 再上传文件 → 节点变上传态、编辑框收起。
        # 编辑框子树被卸载时，用户刚敲的字不能跟着消失（v8 回归的镜像场景）。
        phase2 = []
        try:
            node = page.locator('.react-flow__node[data-id="img-empty"]')
            box = await node.bounding_box()
            await page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
            await page.wait_for_timeout(400)
            editor = page.locator('[data-pea-anchor="img-empty"] .node-prompt-editor')
            await editor.wait_for(timeout=5000)
            await editor.click()
            typed = "上传前写下的提示词ABC"
            await page.keyboard.type(typed, delay=12)
            await page.wait_for_timeout(900)  # 越过 700ms 防抖

            before = await page.locator(".node-input-bar").count()
            async with page.expect_file_chooser() as fc_info:
                await page.locator('.react-flow__node[data-id="img-empty"] .pea-node-upload-btn').click()
            fc = await fc_info.value
            await fc.set_files({"name": "mock.png", "mimeType": "image/png",
                                "buffer": b"\x89PNG\r\n\x1a\n" + b"0" * 64})
            await page.wait_for_timeout(1500)

            after = await page.locator(".node-input-bar").count()
            draft = await page.evaluate("() => localStorage.getItem('pea:draft:1:img-empty') || ''")

            phase2.append(("上传前编辑框存在", before == 1, f"{before}"))
            phase2.append(("上传后编辑框收起", after == 0, f"{after}"))
            phase2.append(("输入内容未丢失", typed in draft, draft[:60]))
            await page.screenshot(path=str(SHOT_DIR / "upload_editor_after_upload.png"))
        except Exception as e:
            phase2.append(("Phase2 执行", False, f"异常: {e}"))

        print("\n" + "=" * 82)
        print("上传素材节点 · 编辑框显隐全类型回归")
        print("=" * 82)
        all_pass = True
        for nid, got, want, ok in results:
            print(f"{'✅' if ok else '❌'} {nid:<12} 实际[{got}]  期望[{want}]")
            if not ok:
                all_pass = False
        print("-" * 82)
        print("Phase 2 · 「先写提示词再上传」数据安全护栏")
        for name, ok, detail in phase2:
            print(f"{'✅' if ok else '❌'} {name:<18} {detail}")
            if not ok:
                all_pass = False
        print("=" * 82)
        print(("全部通过 ✅" if all_pass else "存在失败 ❌")
              + f"  共 {len(results) + len(phase2)} 例")

        await browser.close()
        return 0 if all_pass else 1


if __name__ == "__main__":
    proc = ensure_preview()
    try:
        code = asyncio.run(run())
    finally:
        if proc:
            proc.terminate()
    sys.exit(code)
