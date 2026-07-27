# -*- coding: utf-8 -*-
"""
复现/验证「进入项目 A 却显示最近编辑的项目 B」bug。

流程：
1. 注册新用户 → 开 devHooks
2. 新建项目 P1 → 注入带 P1-MARKER 的文本节点 → 触发自动保存 → 退出画布
3. 新建项目 P2 → 注入带 P2-MARKER 的文本节点 → 触发自动保存 → 退出画布
4. 回到项目列表：
   a. 记录列表卡片顺序（data-canvas-id）
   b. 精确点击 P1 卡片（by data-canvas-id）
   c. 断言画布 canvasId == P1 且内容含 P1-MARKER、不含 P2-MARKER
5. 直接 GET /canvases/P1、/canvases/P2 校验 DB 数据是否被写串
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOT = "verify/shots"


def log(msg):
    print(msg, flush=True)


def register(page):
    ts = int(time.time())
    email = f"vps_{ts}@pea.dev"
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(700)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', email)
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "VPS")
    page.locator("form button[type=submit]").click()
    page.wait_for_function("() => !!localStorage.getItem('pea_token')", timeout=15000)
    log(f"[ok] registered {email}")
    return email


def enable_dev_hooks(page):
    page.evaluate("() => localStorage.setItem('__peaDevHooks','1')")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(800)


def create_project(page, marker):
    """从项目列表新建项目，注入 marker 文本节点并等自动保存，返回 canvasId。"""
    page.wait_for_selector('button:has-text("新建项目")', timeout=15000)
    page.locator(".projects-new-btn", has_text="新建项目").first.click()
    page.wait_for_selector(".react-flow", timeout=15000)
    page.wait_for_function("() => !!window.__canvas", timeout=10000)
    cid = page.evaluate("() => window.__canvas.getState().canvasId")
    assert cid, "canvasId is null after create"
    # 注入文本节点（addNode 会置 dirty=true → 1s 后自动保存）
    page.evaluate(
        """(m) => {
            const s = window.__canvas.getState();
            s.addNode({ kind: 'text', label: '文本', html: m }, { x: 200, y: 200 });
        }""",
        marker,
    )
    # 等自动保存完成（dirty -> false 且 saveCount>0）
    page.wait_for_function(
        "() => { const s = window.__canvas.getState(); return !s.dirty && s.saveCount > 0; }",
        timeout=15000,
    )
    ver = page.evaluate("() => window.__canvas.getState().version")
    log(f"[ok] project created id={cid} marker={marker} savedVersion={ver}")
    return cid


def exit_canvas(page):
    page.click(".pea-canvas-header-trigger")
    page.wait_for_selector("text=返回工作空间", timeout=5000)
    page.click("text=返回工作空间")
    page.wait_for_selector(".projects-grid", timeout=15000)
    page.wait_for_timeout(600)  # 等列表加载
    log("[ok] back to workspace")


def edit_project(page, marker2):
    """在当前画布再加一个节点触发保存（模拟'编辑'）。"""
    page.wait_for_function("() => !!window.__canvas", timeout=10000)
    before = page.evaluate("() => window.__canvas.getState().saveCount")
    page.evaluate(
        """(m) => {
            const s = window.__canvas.getState();
            s.addNode({ kind: 'text', label: '文本', html: m }, { x: 420, y: 320 });
        }""",
        marker2,
    )
    page.wait_for_function(
        f"() => {{ const s = window.__canvas.getState(); return !s.dirty && s.saveCount > {before}; }}",
        timeout=15000,
    )
    log(f"[ok] edited, marker {marker2} saved")


def open_project_by_id(page, cid):
    sel = f".projects-card[data-canvas-id='{cid}']"
    page.wait_for_selector(sel, timeout=10000)
    page.click(sel)
    page.wait_for_selector(".react-flow", timeout=15000)
    page.wait_for_function("() => !!window.__canvas", timeout=10000)
    page.wait_for_timeout(500)


def canvas_snapshot(page):
    return page.evaluate(
        """() => {
            const s = window.__canvas.getState();
            return {
                canvasId: s.canvasId,
                title: s.title,
                htmls: s.nodes.map(n => (n.data && n.data.html) || '').join('|'),
                nodeCount: s.nodes.length,
            };
        }"""
    )


def api_get_canvas(page, cid):
    return page.evaluate(
        """async (cid) => {
            const t = localStorage.getItem('pea_token');
            const r = await fetch('/canvases/' + cid, { headers: { Authorization: 'Bearer ' + t } });
            const d = await r.json();
            const g = typeof d.graph_json === 'string' ? JSON.parse(d.graph_json || '{}') : (d.graph_json || {});
            return {
                id: d.id, title: d.title, version: d.version,
                htmls: ((g.nodes || []).map(n => (n.data && n.data.html) || '')).join('|'),
            };
        }""",
        cid,
    )


def main():
    fails = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("console", lambda m: m.type == "error" and log(f"[console.error] {m.text[:200]}"))

        register(page)
        enable_dev_hooks(page)

        # ---- 建 P1 ----
        p1 = create_project(page, "P1-MARKER")
        exit_canvas(page)

        # ---- 建 P2 并编辑 ----
        p2 = create_project(page, "P2-MARKER")
        edit_project(page, "P2-EDIT")
        exit_canvas(page)

        # ---- 列表顺序：修复后默认按「最近创建」，编辑 P2 不应让它跳到 P1 前面 ----
        order = page.evaluate(
            "() => Array.from(document.querySelectorAll('.projects-card[data-canvas-id]')).map(e => e.getAttribute('data-canvas-id'))"
        )
        log(f"[info] card order in list (P1={p1}, P2={p2}): {order}")
        page.screenshot(path=f"{SHOT}/vps_list.png")
        # P2 创建晚于 P1：按创建序（新→旧）应为 [P2, P1]，且顺序不因"谁刚被编辑"而漂移。
        # 关键断言：无论谁刚被编辑，顺序都由创建时间唯一决定 —— 再编辑一次 P1 后顺序必须不变。

        # ---- 模拟用户操作：点「第一张卡」，记住它是谁，进去后 canvasId 必须等于它 ----
        first_card = page.evaluate(
            "() => { const e = document.querySelector('.projects-card[data-canvas-id]'); return Number(e && e.getAttribute('data-canvas-id')); }"
        )
        open_project_by_id(page, first_card)
        snap0 = canvas_snapshot(page)
        log(f"[info] clicked FIRST card (id={first_card}) -> canvas {snap0['canvasId']}")
        if snap0["canvasId"] != first_card:
            fails.append(f"first-card mismatch: card {first_card} but canvas {snap0['canvasId']}")
        exit_canvas(page)

        # ---- 再编辑 P1，回列表：顺序必须与之前完全一致（不跳位）----
        open_project_by_id(page, p1)
        edit_project(page, "P1-EDIT")
        exit_canvas(page)
        order2 = page.evaluate(
            "() => Array.from(document.querySelectorAll('.projects-card[data-canvas-id]')).map(e => e.getAttribute('data-canvas-id'))"
        )
        log(f"[info] card order after editing P1: {order2}")
        if order2 != order:
            fails.append(f"card order drifted after editing P1: {order} -> {order2}")

        # ---- 精确点击 P1 卡片 ----
        open_project_by_id(page, p1)
        snap = canvas_snapshot(page)
        log(f"[info] after clicking P1 card: {json.dumps(snap, ensure_ascii=False)}")
        page.screenshot(path=f"{SHOT}/vps_open_p1.png")

        if snap["canvasId"] != p1:
            fails.append(f"canvasId mismatch: expect {p1}, got {snap['canvasId']}")
        if "P1-MARKER" not in snap["htmls"]:
            fails.append(f"P1 content missing P1-MARKER: {snap['htmls']}")
        if "P2-MARKER" in snap["htmls"] or "P2-EDIT" in snap["htmls"]:
            fails.append(f"P1 canvas shows P2 content! htmls={snap['htmls']}")

        # ---- 回列表再点 P2 精确验证 ----
        exit_canvas(page)
        open_project_by_id(page, p2)
        snap2 = canvas_snapshot(page)
        log(f"[info] after clicking P2 card: {json.dumps(snap2, ensure_ascii=False)}")
        if snap2["canvasId"] != p2:
            fails.append(f"P2 canvasId mismatch: expect {p2}, got {snap2['canvasId']}")
        if "P2-MARKER" not in snap2["htmls"]:
            fails.append(f"P2 content missing P2-MARKER: {snap2['htmls']}")
        if "P1-MARKER" in snap2["htmls"]:
            fails.append(f"P2 canvas shows P1 content! htmls={snap2['htmls']}")

        # ---- DB 层校验 ----
        db1 = api_get_canvas(page, p1)
        db2 = api_get_canvas(page, p2)
        log(f"[info] DB P1: {json.dumps(db1, ensure_ascii=False)}")
        log(f"[info] DB P2: {json.dumps(db2, ensure_ascii=False)}")
        if "P2-MARKER" in db1["htmls"] or "P2-EDIT" in db1["htmls"]:
            fails.append("DB CORRUPTION: P1 row contains P2 content")
        if "P1-MARKER" in db2["htmls"]:
            fails.append("DB CORRUPTION: P2 row contains P1 content")
        if "P1-MARKER" not in db1["htmls"]:
            fails.append("DB: P1 row missing its own marker (save lost)")

        # ---- 最终确认：列表首卡固定（按创建序），不随编辑漂移 ----
        exit_canvas(page)
        final_first = page.evaluate(
            "() => { const e = document.querySelector('.projects-card[data-canvas-id]'); return e && e.getAttribute('data-canvas-id'); }"
        )
        log(f"[info] FINAL first card = {final_first} (创建序应恒为最新创建的 P2={p2}，与谁被编辑无关)")
        if str(final_first) != str(order[0]):
            fails.append(f"first card drifted at the end: {order[0]} -> {final_first}")

        browser.close()

    log("=" * 60)
    if fails:
        for f in fails:
            log(f"[FAIL] {f}")
        sys.exit(1)
    log("[PASS] 精确按卡片 id 点击时，两个项目内容均正确、DB 无写串")


if __name__ == "__main__":
    main()
