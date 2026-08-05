# -*- coding: utf-8 -*-
"""
文本节点「边框框」功能条根因验证脚本。

背景（用户反馈）：
  «文本节点框，点击后这个边框框功能全部不能使用»
  «点击还是会刷闪功能条和编辑框»

验证对象：真实 TextNodeToolbar 组件 + 真实 index.css（通过 /probe.html 挂载，
不依赖 BFF 后端）。

三个场景：
  A. selected=true & editing=false（新建节点自动选中 / 框选 / blur 之后的真实状态）
     → 点 H1：预期【修复前失败】，execCommand 静默失败，innerHTML 不含 <h1>
  B. 先点文本区进入编辑态 → 点 H1
     → 预期成功（这是唯一"碰巧能用"的路径）
  C. 编辑态下点下方输入栏按钮 → 检查是否被踢出编辑态 + class 抖动次数（闪动）

用法： python verify/probe_text_toolbar.py
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/probe.html"


def probe(page):
    return {
        "html": page.evaluate("window.__probe.html()"),
        "editing": page.evaluate("window.__probe.editing()"),
        "ce": page.evaluate("window.__probe.contentEditable()"),
        "flips": page.evaluate("window.__probe.classFlips()"),
        "trace": page.evaluate("window.__probe.classTrace()"),
        "active": page.evaluate("window.__probe.active()"),
    }


def click_h1(page):
    """点击工具条「一级标题」按钮（真实 trusted 点击）。"""
    btn = page.locator('.tnt-bar button[title="一级标题"]')
    btn.wait_for(state="visible", timeout=5000)
    btn.click()
    page.wait_for_timeout(200)


def main():
    results = []
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#probe-edit", timeout=10000)
        page.wait_for_timeout(300)

        # ── 场景 A：仅选中、未进编辑态 ───────────────────────────
        page.click("#probe-select-only")
        page.wait_for_timeout(200)
        page.evaluate("window.__probe.reset()")
        before = probe(page)
        bar_visible = page.locator(".tnt-bar").is_visible()
        click_h1(page)
        after = probe(page)
        a_pass = "<h1>" in after["html"].lower()
        results.append(
            {
                "case": "A. selected=true, editing=false → 点 H1",
                "toolbar_visible": bar_visible,
                "contentEditable_before": before["ce"],
                "html_after": after["html"][:90],
                "h1_applied": a_pass,
                "verdict": "PASS" if a_pass else "FAIL(功能失效)",
            }
        )
        ok = ok and a_pass

        # ── 场景 B：先点文本区进编辑态，再点 H1 ─────────────────
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#probe-edit", timeout=10000)
        page.wait_for_timeout(300)
        page.click("#probe-edit")
        page.wait_for_timeout(250)
        page.evaluate("window.__probe.reset()")
        before_b = probe(page)
        click_h1(page)
        after_b = probe(page)
        b_pass = "<h1>" in after_b["html"].lower()
        results.append(
            {
                "case": "B. 点文本区进编辑态 → 点 H1",
                "contentEditable_before": before_b["ce"],
                "html_after": after_b["html"][:90],
                "h1_applied": b_pass,
                "flips": after_b["flips"],
                "verdict": "PASS" if b_pass else "FAIL",
            }
        )
        ok = ok and b_pass

        # ── 场景 C：编辑态下点下方输入栏按钮 → 是否掉编辑态/闪动 ──
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#probe-edit", timeout=10000)
        page.wait_for_timeout(300)
        page.click("#probe-edit")
        page.wait_for_timeout(250)
        page.evaluate("window.__probe.reset()")
        page.click("#probe-mic")
        page.wait_for_timeout(250)
        after_c = probe(page)
        # 期望：点输入栏按钮后仍保持编辑态（不掉 contentEditable），且无 class 抖动
        c_pass = after_c["ce"] and after_c["flips"] == 0
        results.append(
            {
                "case": "C. 编辑态 → 点下方输入栏 🎤",
                "still_editable": after_c["ce"],
                "class_flips": after_c["flips"],
                "trace": after_c["trace"],
                "verdict": "PASS" if c_pass else "FAIL(掉编辑态/闪动)",
            }
        )
        ok = ok and c_pass

        # ── 场景 D：C 之后再点 H1（用户最常见路径）──────────────
        page.evaluate("window.__probe.reset()")
        click_h1(page)
        after_d = probe(page)
        d_pass = "<h1>" in after_d["html"].lower()
        results.append(
            {
                "case": "D. 点过输入栏后再点 H1（最常见路径）",
                "html_after": after_d["html"][:90],
                "h1_applied": d_pass,
                "verdict": "PASS" if d_pass else "FAIL(功能失效)",
            }
        )
        ok = ok and d_pass

        results.append({"pageerrors": errors})
        browser.close()

    print("=" * 78)
    for r in results:
        for k, v in r.items():
            print(f"  {k}: {v}")
        print("-" * 78)
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
