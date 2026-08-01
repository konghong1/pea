#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证两项修复（E2E，Playwright + 托管 Python）:
  A) 节点框尺寸标准化：image=9:16 / video=16:9 / text=1:1，最长边恒为 340px，
     与内容无关（杜绝"有图后框被素材比例撑变形"导致的画布比例混乱）。
  B) 画布视口持久化：退出画布后视口（x,y,zoom）写入 localStorage，再次进入原样恢复，
     不再每次回到初始状态。

流程：注册 -> 工作空间 -> 新建项目 -> 画布。依赖 dev hooks（localStorage.__peaDevHooks=1）
暴露的 window.__ui / window.__canvas / window.__peaSetViewport。
"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"


def banner(t):
    print("\n" + "=" * 64)
    print("  " + t)
    print("=" * 64)


def check(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  -> {detail}" if detail else ""))
    return ok


def read_vp(pg):
    """从 .react-flow__viewport 的 transform 解析当前视口（x,y,zoom）。"""
    tf = pg.evaluate(
        "() => { const e=document.querySelector('.react-flow__viewport'); "
        "return e ? getComputedStyle(e).transform : ''; }"
    )
    if not tf or tf == "none":
        return None
    # matrix(a,b,c,d,e,f) -> scale=a, tx=e, ty=f
    import re
    m = re.search(r"matrix\(([^)]+)\)", tf)
    if not m:
        return None
    a, b, c, d, e, f = [float(x) for x in m.group(1).split(",")]
    return {"x": e, "y": f, "zoom": a}


def main():
    all_ok = True
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        # dev hooks 必须在页面脚本执行前写入
        ctx.add_init_script("localStorage.setItem('__peaDevHooks','1');")
        pg = ctx.new_page()
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(400)

        banner("1) 注册 / 进入工作空间")
        try:
            pg.click("text=去注册", timeout=5000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        ts = int(time.time())
        email = "vpts_%d@pea.ai" % ts
        pg.fill("input:visible >> nth=0", email)
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        pg.click("button:has-text('注')", timeout=5000)
        pg.wait_for_timeout(1500)

        # 直接跳到工作空间（dev hook 暴露 __ui）
        pg.evaluate("() => window.__ui.getState().setActive('workspace')")
        try:
            pg.wait_for_selector(".projects-new-btn", timeout=8000)
        except Exception as e:
            all_ok &= check("进入工作空间", False, "找不到新建项目按钮: %s" % e)
            b.close()
            return
        all_ok &= check("进入工作空间", True)

        banner("2) 新建项目 -> 进入画布")
        pg.locator(".projects-new-btn").first.click()
        try:
            pg.wait_for_selector(".react-flow__viewport", timeout=15000)
        except Exception as e:
            all_ok &= check("进入画布", False, "画布未加载: %s" % e)
            b.close()
            return
        pg.wait_for_timeout(800)
        canvas_id = pg.evaluate("() => window.__canvas.getState().canvasId")
        all_ok &= check("进入画布", True, "canvasId=%s" % canvas_id)

        banner("3) A) 节点框尺寸标准化")
        # 注入三种 kind 的节点（空态，验证框由比例锁定而非内容）
        pg.evaluate(
            """() => {
              const s = window.__canvas.getState();
              s.addNode({ kind: 'image', title: 'IMG' }, {x: 0, y: 0});
              s.addNode({ kind: 'video', title: 'VID' }, {x: 500, y: 0});
              s.addNode({ kind: 'text',  title: 'TXT' }, {x: 1000, y: 0});
            }"""
        )
        pg.wait_for_timeout(600)

        def box(kind):
            # offsetWidth/Height = 布局像素，不受 ReactFlow 视口缩放影响
            return pg.evaluate(
                "() => { const e=document.querySelector('.pea-node-%s'); "
                "return e ? { width: e.offsetWidth, height: e.offsetHeight } : null; }" % kind
            )

        b_img = box("image")
        b_vid = box("video")
        b_txt = box("text")
        ok_img = bool(b_img)
        ok_vid = bool(b_vid)
        ok_txt = bool(b_txt)
        all_ok &= check("渲染 image/video/text 节点", ok_img and ok_vid and ok_txt,
                        "img=%s vid=%s txt=%s" % (b_img, b_vid, b_txt))

        LONG = 340
        if b_img:
            # image 9:16 -> 竖屏：宽=round(340*9/16)=191, 高=340
            exp_w, exp_h = round(LONG * 9 / 16), LONG
            img_ok = abs(b_img["width"] - exp_w) <= 3 and abs(b_img["height"] - exp_h) <= 3
            all_ok &= check("image 框=9:16(锁~191x340)",
                            img_ok, "got %.0fx%.0f exp ~%dx%d" % (b_img["width"], b_img["height"], exp_w, exp_h))
        if b_vid:
            # video 16:9 -> 横屏：宽=340, 高=round(340*9/16)=191
            exp_w, exp_h = LONG, round(LONG * 9 / 16)
            vid_ok = abs(b_vid["width"] - exp_w) <= 3 and abs(b_vid["height"] - exp_h) <= 3
            all_ok &= check("video 框=16:9(锁340x~191)",
                            vid_ok, "got %.0fx%.0f exp ~%dx%d" % (b_vid["width"], b_vid["height"], exp_w, exp_h))
        if b_txt:
            txt_ok = abs(b_txt["width"] - LONG) <= 3 and abs(b_txt["height"] - LONG) <= 3
            all_ok &= check("text 框=1:1(锁340x340)",
                            txt_ok, "got %.0fx%.0f exp %dx%d" % (b_txt["width"], b_txt["height"], LONG, LONG))
        # 标准化不变量：每个节点 max(宽,高) 恒=340（无论横竖屏，物理最长边一致）
        if b_img and b_vid and b_txt:
            long_edges = {
                max(round(b_img["width"]), round(b_img["height"])),
                max(round(b_vid["width"]), round(b_vid["height"])),
                max(round(b_txt["width"]), round(b_txt["height"])),
            }
            std_ok = long_edges == {LONG}
            all_ok &= check("最长边不变量 max(W,H)=340（统一标准）",
                            std_ok, "最长边集合=%s" % sorted(long_edges))

        banner("4) B) 画布视口持久化")
        # 设置明确的目标视口
        pg.evaluate("() => window.__peaSetViewport(150, -90, 1.4)")
        pg.wait_for_timeout(200)
        # 滚动一下确保 onMove 触发并落盘（panOnScroll：wheel=平移）
        cx, cy = 720, 450
        pg.mouse.move(cx, cy)
        pg.mouse.wheel(0, 80)
        pg.wait_for_timeout(300)
        vp_before = read_vp(pg)
        all_ok &= check("设置视口成功", vp_before is not None,
                        "vp=%s" % vp_before)
        # 等防抖落盘（250ms）+ 兜底
        pg.wait_for_timeout(700)
        saved = pg.evaluate(
            "() => localStorage.getItem('pea_canvas_vp_%s')" % canvas_id
        )
        import json
        saved_ok = False
        if saved:
            sv = json.loads(saved)
            saved_ok = (abs(sv["x"] - vp_before["x"]) <= 4 and
                        abs(sv["y"] - vp_before["y"]) <= 4 and
                        abs(sv["zoom"] - vp_before["zoom"]) <= 0.05)
            detail = "saved=%s live=%s" % (sv, {k: round(v, 3) for k, v in vp_before.items()})
        else:
            detail = "localStorage 无记录"
        all_ok &= check("视口已写入 localStorage", saved_ok, detail)

        banner("5) 退出画布 -> 再次进入 -> 视口应恢复")
        pg.evaluate("() => window.__ui.getState().setActive('workspace')")
        pg.wait_for_selector(".projects-new-btn", timeout=8000)
        pg.wait_for_timeout(400)
        # 点击对应 canvas 卡片重新进入
        card = pg.locator("[data-canvas-id='%s']" % canvas_id)
        if card.count() == 0:
            all_ok &= check("重新进入画布", False, "找不到 canvas 卡片 id=%s" % canvas_id)
            b.close()
            return
        card.first.click()
        pg.wait_for_selector(".react-flow__viewport", timeout=15000)
        pg.wait_for_timeout(900)
        vp_after = read_vp(pg)
        restored = (vp_after and saved and
                    abs(vp_after["x"] - vp_before["x"]) <= 4 and
                    abs(vp_after["y"] - vp_before["y"]) <= 4 and
                    abs(vp_after["zoom"] - vp_before["zoom"]) <= 0.05)
        all_ok &= check("再次进入视口已恢复（非初始态）",
                        restored, "before=%s after=%s" % (
                            {k: round(v, 2) for k, v in vp_before.items()},
                            {k: round(v, 2) for k, v in (vp_after or {}) .items()}))
        # 额外证明：恢复后 zoom≈1.4，而不是 fitView 的默认 1
        if vp_after:
            all_ok &= check("恢复 zoom≈1.4（验证未走 fitView 初始态）",
                            abs(vp_after["zoom"] - 1.4) <= 0.05,
                            "zoom=%.3f" % vp_after["zoom"])

        b.close()

    banner("RESULT")
    print("ALL PASS" if all_ok else "SOME FAILED")
    import sys
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
