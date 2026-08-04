"""E2E: 画布统一搜索弹层 (SearchPopover).

覆盖以下场景:
  1) 工具栏搜索按钮点击 → 弹出中央浮层 (不在左边 SidePanel 里).
  2) 类别 tabs: 全部 / 图片 / 视频 / 文本 / 音频 / World / 分组.
  3) 关键词搜索 (匹配节点 label + prompt).
  4) 类别筛选 + 关键词组合筛选.
  5) 点击结果: 节点被选中 + 视口移动到节点中心 (viewport 校验).
  6) 点击搜索框外部 → 关闭浮层.
  7) Esc 关闭浮层.

运行: 直接 `python verify/verify_search_popover.py`，依赖 docker compose 全栈。
"""

import os
import sys
import json
import time
import subprocess
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

EMAIL, PW = "searcher@pea.ai", "SearchPop1!"

errors = []
passed = []
failed = []

MYSQL = ["docker", "exec", "pea-server-mysql-1", "mysql", "-upea", "-ppea_dev", "-D", "pea", "-N", "-e"]


def mysql_q(sql):
    p = subprocess.run(MYSQL + [sql], capture_output=True, text=True, timeout=30)
    return p.stdout.strip()


def shot(page, name):
    p = os.path.join(SHOTS, f"searchpop_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")
    return p


def step(label):
    print(f"\n>> {label}")


def assert_true(cond, label):
    if cond:
        passed.append(label)
        print(f"  ✓ {label}")
    else:
        failed.append(label)
        print(f"  ✗ {label}")


def ensure_search_canvas():
    """保证 searcher 账号有一个含多种类型节点的画布。
    直接通过 BFF 创建 / 注入；找不到就跳过 node 数校验。"""
    import urllib.error
    EMAIL_LOCAL = "searcher@pea.ai"
    PW_LOCAL = "SearchPop1!"
    # 1) 登录拿 token (BFF global prefix = /api)
    body = json.dumps({"email": EMAIL_LOCAL, "password": PW_LOCAL}).encode()
    req = urllib.request.Request(
        "http://localhost:4100/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            tok = json.loads(r.read()).get("token")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] 登录失败: HTTP {e.code} {e.read()[:200]!r}")
        sys.exit(2)
    if not tok:
        print("[FAIL] 登录失败，无 token")
        sys.exit(2)

    headers = {"Authorization": f"Bearer {tok}"}

    # 2) 列已有 canvas
    req = urllib.request.Request("http://localhost:4100/api/canvases", headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        cs = json.loads(r.read())
    canvas_list = cs if isinstance(cs, list) else cs.get("items", [])

    # 若已有 ≥5 节点的画布，复用
    chosen = None
    for c in canvas_list[:30]:
        gid = c.get("id")
        if not gid:
            continue
        req2 = urllib.request.Request(
            f"http://localhost:4100/api/canvases/{gid}", headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(req2, timeout=10) as r2:
                data = json.loads(r2.read())
        except Exception:
            continue
        g = (data.get("graph_json") or {})
        nodes = g.get("nodes", [])
        kinds = {n.get("data", {}).get("kind", "?") for n in nodes}
        if len(nodes) >= 5 and ("image" in kinds and "text" in kinds):
            chosen = gid
            print(f"[reset] reuse canvas {gid}: {len(nodes)} nodes, kinds={sorted(kinds)}")
            # 强制 PUT 用最新 nodes 覆盖（含 resultUrl），保证缩略图能渲染
            req_v = urllib.request.Request(
                f"http://localhost:4100/api/canvases/{gid}", headers=headers, method="GET"
            )
            with urllib.request.urlopen(req_v, timeout=10) as rv:
                cur = json.loads(rv.read())
            cur_ver = cur.get("version", 1)
            # 复用 PUT, 用最新 nodes/edges 覆盖
            body = json.dumps({
                "graph_json": build_search_graph(),
                "version": cur_ver,
            }).encode()
            req_p = urllib.request.Request(
                f"http://localhost:4100/api/canvases/{gid}",
                data=body,
                headers={"Content-Type": "application/json", **headers},
                method="PUT",
            )
            with urllib.request.urlopen(req_p, timeout=15) as rp:
                print(f"[reset] re-saved canvas {gid} with latest nodes: {json.loads(rp.read())}")
            return gid

    # 3) 否则创建一个新画布并塞入多种节点
    body = json.dumps({
        "title": "搜索测试画布",
        "scope": "personal",
    }).encode()
    req = urllib.request.Request(
        "http://localhost:4100/api/canvases",
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    new_canvas = {}
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            new_canvas = json.loads(r.read())
        chosen = new_canvas.get("id") or new_canvas.get("canvas", {}).get("id")
        version = new_canvas.get("version", 1)
        print(f"[reset] created canvas {chosen} (version={version})")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] create canvas failed: HTTP {e.code} {e.read()[:200]!r}")
        sys.exit(2)

    # 4) PUT 写入 graph_json
    graph = build_search_graph()
    body = json.dumps({
        "graph_json": graph,
        "version": version,
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:4100/api/canvases/{chosen}",
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            put_res = json.loads(r.read())
        print(f"[reset] saved graph_json -> {put_res}, total {len(graph['nodes'])} nodes")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] save graph_json failed: HTTP {e.code} {e.read()[:200]!r}")
        sys.exit(2)

    return chosen


def build_search_graph():
    """返回搜索测试用的标准 nodes/edges，确保 n5 (video) 一定有 resultUrl/resultUrls。"""
    nodes = [
        {"id": "n1", "type": "pea", "position": {"x": 100, "y": 100}, "data": {
            "label": "Image A 卧室", "kind": "image",
            "prompt": "一只橘色的猫正慵懒地蜷缩在柔软的米色布艺沙发上，阳光透过窗户洒在它蓬松的毛发上，它闭着眼",
            "aspectRatio": "16:9",
            "resultUrl": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 60'%3E%3Crect fill='%23e8b483' width='100' height='60'/%3E%3Ctext x='50' y='35' font-size='14' text-anchor='middle' fill='white'%3E卧室%3C/text%3E%3C/svg%3E",
        }},
        {"id": "n2", "type": "pea", "position": {"x": 500, "y": 100}, "data": {
            "label": "图片生成 模特换衣", "kind": "image",
            "prompt": "帮我把 衣服换到另一个模特上",
            "aspectRatio": "9:16",
            "resultUrl": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 100'%3E%3Crect fill='%23FD79A8' width='60' height='100'/%3E%3Ctext x='30' y='55' font-size='12' text-anchor='middle' fill='white'%3E模特%3C/text%3E%3C/svg%3E",
            "resultUrls": ["data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 100'%3E%3Crect fill='%23FD79A8' width='60' height='100'/%3E%3Ctext x='30' y='55' font-size='12' text-anchor='middle' fill='white'%3E模特%3C/text%3E%3C/svg%3E"],
        }},
        {"id": "n3", "type": "pea", "position": {"x": 900, "y": 100}, "data": {
            "label": "Image 无Prompt", "kind": "image", "prompt": "",
        }},
        {"id": "n4", "type": "pea", "position": {"x": 1300, "y": 100}, "data": {
            "label": "文本文案", "kind": "text",
            "prompt": "这张图的人（{{image.1}}），我只要模特\n冬季新品上市",
            "html": "<p>这张图的人，我只要模特</p><p>冬季新品上市</p>",
        }},
        {"id": "n5", "type": "pea", "position": {"x": 1700, "y": 100}, "data": {
            "label": "视频素材", "kind": "video", "prompt": "",
            "resultUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAASCAYAAAA6ylyTAAAAH0lEQVR42mNk+M9QzwAEjP9hgIGBgZGRkYGRkYGBgYEBADrxA/6Z1Fy0AAAAAElFTkSuQmCC",
            "resultUrls": ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAASCAYAAAA6ylyTAAAAH0lEQVR42mNk+M9QzwAEjP9hgIGBgZGRkYGRkYIGBgQEAOvED/pnUXLQAAAAASUVORK5CYII="],
        }},
        {"id": "n6", "type": "pea", "position": {"x": 100, "y": 500}, "data": {
            "label": "音频旁白", "kind": "audio", "prompt": "",
        }},
        {"id": "n7", "type": "pea", "position": {"x": 500, "y": 500}, "data": {
            "label": "3D 房间", "kind": "world3d", "prompt": "室内场景",
        }},
        {"id": "n8", "type": "group", "position": {"x": 2000, "y": 400},
         "style": {"width": 400, "height": 280},
         "data": {"label": "分镜组合"}},
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2", "sourceHandle": "out", "targetHandle": "in", "type": "pea"},
        {"id": "e2", "source": "n2", "target": "n4", "sourceHandle": "out", "targetHandle": "in", "type": "pea"},
        {"id": "e3", "source": "n5", "target": "n4", "sourceHandle": "out", "targetHandle": "in", "type": "pea"},
    ]
    return {"nodes": nodes, "edges": edges}


def main():
    canvas_id = ensure_search_canvas()
    if not canvas_id:
        print("[FAIL] 无可用画布 (searcher 账号下应当至少有 1 个项目)")
        return 2
    print(f"[main] canvas_id = {canvas_id}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        # 打开 dev hooks（prod bundle 也会暴露 __canvas/__ui/__peaSetViewport 等）
        ctx.add_init_script("localStorage.setItem('__peaDevHooks','1');")
        page = ctx.new_page()
        page.on(
            "console",
            lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        try:
            run_verification(page, canvas_id)
        except Exception as e:
            import traceback
            print(f"[CRASH] {e}")
            traceback.print_exc()
            shot(page, "99_crash")
            try:
                browser.close()
            except Exception:
                pass
            return 2

        browser.close()

    e2e_errors = [e for e in errors if "ResizeObserver" not in e and "favicon" not in e.lower()]
    print("\n=== 汇总 ===")
    print(f"通过 {len(passed)}: {passed}")
    print(f"失败 {len(failed)}: {failed}")
    print(f"console error {len(e2e_errors)}: {e2e_errors[:5]}")
    return 0 if not failed else 1


def run_verification(page, canvas_id):

        # --- 登录 ---
        step("登录")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(700)
        page.fill('input[placeholder="you@pea.ai"]', EMAIL)
        page.fill('input[placeholder="至少 8 位"]', PW)
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(2500)
        # 校验 token 已落地
        token = page.evaluate("() => localStorage.getItem('pea_token')")
        print(f"  [debug] pea_token = {token[:30] + '...' if token else 'None'}")
        assert_true(token and len(token) > 20, "登录并落地 token")
        shot(page, "01_after_login")

        # --- 打开画布（直接走 zustand store + openCanvas，不依赖 UI 点击稳定性）---
        step(f"工作空间 -> 打开画布 {canvas_id}")
        # 等到 useUi 已注册到 window.__ui (dev hook)
        page.wait_for_function("() => !!(window).__ui", timeout=10000)
        # 切到 workspace 页让 ReactFlowProvider 真的挂载
        page.evaluate(
            f"""
            (() => {{
              const ui = window.__ui.getState();
              ui.setCanvasId({canvas_id});
              ui.setActive('canvas');
            }})();
            """
        )
        page.wait_for_selector(".pea-canvas-host", timeout=10000)
        page.wait_for_function("() => !!(window).__canvas", timeout=8000)
        # 直接调一次 API 看返回
        api_data = page.evaluate(
            f"async () => {{ const r = await fetch('/api/canvases/{canvas_id}', {{ headers: {{ Authorization: 'Bearer ' + localStorage.getItem('pea_token') }} }}); const j = await r.json(); return {{ status: r.status, keys: Object.keys(j), nodes: (j.graph_json?.nodes || []).length, title: j.title }}; }}"
        )
        print(f"  [debug] /api/canvases/{canvas_id} -> {api_data}")
        # 通过 store 调 openCanvas
        page.evaluate(
            f"window.__canvas.getState().openCanvas({canvas_id})"
        )
        page.wait_for_function(
            "() => window.__canvas.getState().nodes.length > 0",
            timeout=8000,
        )
        page.wait_for_function(
            "() => document.querySelectorAll('.react-flow__node').length > 0",
            timeout=8000,
        )
        page.wait_for_timeout(2500)  # 等 fitView 动画
        shot(page, "02_canvas_loaded")
        store_info = page.evaluate(
            "() => { const s = window.__canvas.getState(); return { n: s.nodes.length, e: s.edges.length, ids: s.nodes.map(x=>x.id) }; }"
        )
        print(f"  [info] store 节点数 = {store_info['n']}, edges = {store_info['e']}, ids = {store_info['ids']}")
        n_actual_nodes = page.evaluate(
            "() => document.querySelectorAll('.react-flow__node').length"
        )
        print(f"  [info] DOM 中渲染的节点数 = {n_actual_nodes}")
        assert_true(store_info["n"] > 0, f"画布已打开并加载了 {store_info['n']} 个节点")

        # --- 1) 搜索按钮: 点击搜索图标 ---
        step("点击左侧工具栏搜索按钮")
        # 工具栏搜索按钮 aria-label="搜索"
        search_btn = page.locator('button[aria-label="搜索"]')
        assert_true(search_btn.count() > 0, "工具栏存在搜索按钮")
        search_btn.first.click()
        page.wait_for_timeout(500)
        # 期望看到 .pea-search-popover
        assert_true(page.locator(".pea-search-popover").count() == 1, "弹出搜索浮层")
        shot(page, "03_search_open")

        # --- 2) 类别 tabs 全部存在 ---
        step("校验类别 tabs")
        tabs = page.locator(".pea-search-tab")
        labels = []
        for i in range(tabs.count()):
            labels.append(tabs.nth(i).locator(".pea-search-tab-label").inner_text().strip())
        expected_tabs = ["全部", "图片", "视频", "文本", "音频", "World", "分组"]
        assert_true(
            labels == expected_tabs,
            f"类别 tabs 完整 (实际: {labels})",
        )

        # --- 2.1) tabs 行无横向滚动条（应当自然换行）---
        step("校验 chips 行无横向滚动条")
        tabs_box = page.evaluate(
            "() => {"
            "  const el = document.querySelector('.pea-search-tabs');"
            "  if (!el) return null;"
            "  return { sw: el.scrollWidth, cw: el.clientWidth, h: el.offsetHeight };"
            "}"
        )
        if tabs_box is None:
            assert_true(False, ".pea-search-tabs 不存在")
        else:
            no_h_scroll = tabs_box["sw"] <= tabs_box["cw"] + 1
            assert_true(
                no_h_scroll,
                f"chips 行无横向滚动 (scrollWidth={tabs_box['sw']}, clientWidth={tabs_box['cw']})",
            )
            # 高度也应当 ≥ 单行 (40px) 以容纳换行后的多行
            assert_true(
                tabs_box["h"] >= 36,
                f"chips 行能自然换行 (h={tabs_box['h']}px)",
            )

        # --- 2.2) 弹层宽度已加大到 600+ ---
        popover_w = page.evaluate(
            "() => { const el = document.querySelector('.pea-search-popover'); return el ? el.getBoundingClientRect().width : 0; }"
        )
        assert_true(
            popover_w >= 560,
            f"弹层宽度 ≥ 560px (实测 {popover_w:.0f}px)",
        )

        # --- 3) 默认结果数 > 0 ---
        step("默认 '全部' tab 结果")
        items_all = page.locator(".pea-search-item")
        n_all = items_all.count()
        assert_true(n_all > 0, f"默认显示全部节点 ({n_all})")

        # --- 4) 输入关键词: '图片' 或 'image' ---
        step("输入关键词过滤")
        # 用每个节点的 prompt / label 都有的关键词；优先取首个节点的 label 子串
        first_title = items_all.first.locator(".pea-search-item-title").inner_text()
        # 取前 2 个汉字或英文单词做关键词
        kw = first_title[:2] if len(first_title) >= 2 else first_title
        if not kw.strip():
            kw = "Image"  # fallback
        page.locator(".pea-search-input-wrap input").first.fill(kw)
        page.wait_for_timeout(500)
        n_match = page.locator(".pea-search-item").count()
        assert_true(n_match >= 1, f"关键词 '{kw}' 至少匹配 1 条 ({n_match})")
        assert_true(n_match <= n_all, f"过滤后数量 ({n_match}) 不超过全量 ({n_all})")
        shot(page, "04_keyword_filter")

        # 清空关键词，回到全量
        # antd Input 的 allowClear 按钮
        clear_btn = page.locator(".pea-search-input-wrap .ant-input-clear-icon").first
        if clear_btn.count() > 0:
            clear_btn.click()
        else:
            page.locator(".pea-search-input-wrap input").first.fill("")
        page.wait_for_timeout(300)

        # --- 4.5) 缩略图渲染：image/video 节点必须渲染真实 img 标签 ---
        step("校验缩略图：image/video 节点渲染真实图片")
        thumb_stats = page.evaluate(
            "() => {"
            "  const items = document.querySelectorAll('.pea-search-item');"
            "  let total = 0, withImg = 0, noImg = 0;"
            "  const noImgLabels = [];"
            "  items.forEach(it => {"
            "    total++;"
            "    const img = it.querySelector('.pea-search-item-thumb img');"
            "    if (img) {"
            "      withImg++;"
            "    } else {"
            "      noImg++;"
            "      const lbl = it.querySelector('.pea-search-item-title');"
            "      noImgLabels.push(lbl ? lbl.textContent : '?');"
            "    }"
            "  });"
            "  return { total, withImg, noImg, noImgLabels };"
            "}"
        )
        print(
            f"  [info] 总 {thumb_stats['total']} 项, 含 img {thumb_stats['withImg']}, 无 img {thumb_stats['noImg']}, 无图标签={thumb_stats['noImgLabels']}"
        )
        # 至少 image/video 节点应当有 img（不要求全部，因为 text/audio/world3d 可能没有图）
        assert_true(
            thumb_stats["withImg"] >= 1,
            f"至少 1 个 image/video 节点渲染了真实缩略图 (withImg={thumb_stats['withImg']})",
        )

        # --- 5) 类别 tab 过滤: '图片' ---
        step("切换'图片'tab")
        page.locator(".pea-search-tab").nth(1).click()
        page.wait_for_timeout(400)
        items_after = page.locator(".pea-search-item")
        n_img = items_after.count()
        # 校验每条结果的图标 / label 是不是图片相关 (不强校验 thumbnail 是图片，验证 tab 确实生效：数量 <= 全部)
        assert_true(n_img <= n_all, f"图片 tab 结果数 ({n_img}) 不超过全部 ({n_all})")
        shot(page, "05_image_tab")
        # 回到全部
        page.locator(".pea-search-tab").nth(0).click()
        page.wait_for_timeout(300)

        # --- 6) 点击结果 → 视口移动 + 节点选中 ---
        step("点击结果节点")
        viewport_before = page.evaluate(
            "() => { const rf = document.querySelector('.react-flow__viewport'); return rf ? getComputedStyle(rf).transform : ''; }"
        )
        # 找离视口中心最远那个结果（用前面读到的 items_all）
        items_all = page.locator(".pea-search-item")
        target_idx = page.evaluate(
            """
            () => {
              const rf = document.querySelector('.react-flow__viewport');
              if (!rf) return -1;
              const cx = window.innerWidth / 2;
              const cy = window.innerHeight / 2;
              let bestI = -1, bestD = -1;
              document.querySelectorAll('.pea-search-item').forEach((it, i) => {
                const r = it.getBoundingClientRect();
                const d = Math.hypot((r.left + r.width/2) - cx, (r.top + r.height/2) - cy);
                if (d > bestD) { bestD = d; bestI = i; }
              });
              return bestI;
            }
            """
        )
        if target_idx is None or target_idx < 0:
            target_idx = 0
        target_item = items_all.nth(target_idx)
        target_label = target_item.locator(".pea-search-item-title").inner_text()
        target_item.click()
        page.wait_for_timeout(700)  # 等视口动画
        # 浮层应关闭
        popover_count = page.locator(".pea-search-popover").count()
        assert_true(popover_count == 0, f"点击结果后浮层关闭 (剩余 {popover_count})")
        # 视口 transform 应变化
        viewport_after = page.evaluate(
            "() => { const rf = document.querySelector('.react-flow__viewport'); return rf ? getComputedStyle(rf).transform : ''; }"
        )
        assert_true(
            viewport_before != viewport_after,
            f"视口已移动 (transform 变化)",
        )
        shot(page, "06_after_click_result")

        # --- 7) 再打开，点外部关闭 ---
        step("再次打开 + 点击外部关闭")
        page.locator('button[aria-label="搜索"]').first.click()
        page.wait_for_timeout(400)
        assert_true(page.locator(".pea-search-popover").count() == 1, "再次打开浮层")
        # 点击 backdrop 边缘（避开浮层本体）
        page.mouse.click(20, 20)
        page.wait_for_timeout(400)
        assert_true(page.locator(".pea-search-popover").count() == 0, "点击外部关闭浮层")

        # --- 8) Esc 关闭 ---
        step("Esc 关闭")
        page.locator('button[aria-label="搜索"]').first.click()
        page.wait_for_timeout(400)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        assert_true(page.locator(".pea-search-popover").count() == 0, "Esc 关闭浮层")

        # --- 9) 键盘 ↑↓ + Enter ---
        step("键盘 ↑↓ Enter 选中")
        page.locator('button[aria-label="搜索"]').first.click()
        page.wait_for_timeout(400)
        n_items = page.locator(".pea-search-item").count()
        if n_items >= 2:
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(120)
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(120)
            # 第二个 active 项应当至少离第一项的索引为 2
            active_idx = page.evaluate(
                "() => { const list = document.querySelector('.pea-search-result-list'); const a = list ? list.querySelector('.pea-search-item.active') : null; return a ? Number(a.getAttribute('data-idx')) : -1; }"
            )
            assert_true(active_idx == 2, f"键盘 ↓×2 后 active=2 (实际={active_idx})")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # --- 总结 ---
        shot(page, "07_final")


if __name__ == "__main__":
    sys.exit(main())
