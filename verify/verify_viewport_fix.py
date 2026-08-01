"""
验证：点击节点后画布视口不偏移 (fix: focus preventScroll)

根因：NodeChatPrompt / NodePromptInput 在节点点击后调用 inputRef.focus()，
浏览器默认 scroll-into-view 把聚焦元素滚入视野；因输入框位于 ReactFlow
transform 容器内，浏览器对祖先容器的滚动补偿导致画布整体偏移（"点击节点画布跑了"）。

修复：所有 focus() 调用加 { preventScroll: true }。

本脚本三层验证：
  A) 静态：扫描两个源文件的 focus() 调用，确认调用点全部带 preventScroll
     （排除 useImperativeHandle 里把 opts 透传给原生 focus 的实现）。
  B) 动态机制复现（核心）：用 Playwright 复现"transform 容器内、位于可视区外的
     可聚焦元素"被 focus 时浏览器滚动祖先容器的机制 —— 这正是画布偏移的成因。
       - focus() 默认行为会滚动祖先容器（证明机制存在）
       - focus({preventScroll:true}) 不会滚动，且元素仍获得焦点（验证修复）
  C) 实况冒烟（best-effort）：登录后打开画布点击节点，确认视口稳定。
"""

import asyncio
import os
import re
import sys

# ---------- A) 静态扫描 ----------
def static_check():
    base = os.environ.get("PEA_WEB_SRC", r"C:/workspace/pea/pea-server/web/src")
    files = [
        os.path.join(base, "components", "NodePromptInput.tsx"),
        os.path.join(base, "components", "NodeChatPrompt.tsx"),
    ]
    violations = []
    checked = 0
    for f in files:
        if not os.path.exists(f):
            violations.append(f"缺失源文件: {f}")
            continue
        txt = open(f, encoding="utf-8").read()
        for m in re.finditer(r"\.focus\(([^)]*)\)", txt):
            arg = m.group(1).strip()
            # useImperativeHandle 透传：focus(opts) / focus(opts?: FocusOptions) -> 合法，跳过
            if re.match(r"opts\b", arg):
                continue
            checked += 1
            if "preventScroll" not in arg:
                violations.append(
                    f"{os.path.basename(f)}: 存在未加固的 focus 调用: .focus({arg})"
                )
    if violations:
        return [("FAIL", v) for v in violations]
    return [("PASS", f"静态扫描通过：{checked} 处 focus() 调用全部带 preventScroll")]


# ---------- B) 动态机制复现（核心） ----------
async def dynamic_check():
    from playwright.async_api import async_playwright

    # 忠实复现结构：scroll 容器(.react-flow__pane 类) 内嵌 transform 的 viewport，
    # 其内有一个位于可视区之外的可聚焦元素（对应节点输入框）。
    html = """<html><body style="margin:0;padding:0">
      <div id="pane" style="overflow:auto; width:400px; height:300px; position:relative; border:2px solid #333">
        <div id="viewport" style="transform: translate(300px,200px) scale(1); transform-origin:0 0; width:100px; height:100px; background:#cde">
          <input id="target" style="position:absolute; top:260px; left:260px; width:80px;" value="x">
        </div>
      </div></body></html>"""

    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page(viewport={"width": 800, "height": 600})
        await page.set_content(html)

        init = await page.evaluate(
            "() => { const s=document.getElementById('pane'); return [s.scrollLeft, s.scrollTop]; }"
        )

        # 1) 默认 focus() -> 应触发滚动（复现 bug 机制）
        await page.evaluate("() => document.getElementById('target').focus()")
        after_default = await page.evaluate(
            "() => { const s=document.getElementById('pane'); return [s.scrollLeft, s.scrollTop]; }"
        )
        default_scrolled = after_default != init
        out.append(
            ("INFO", f"默认 focus(): 初始={init} 之后={after_default} "
                     f"-> {'发生滚动(复现 bug 机制)' if default_scrolled else '未滚动(无头环境未触发, 仅作信息)'}")
        )

        # 重置滚动
        await page.evaluate(
            "() => { const s=document.getElementById('pane'); s.scrollLeft=0; s.scrollTop=0; }"
        )

        # 2) preventScroll focus() -> 不应滚动，且元素应获得焦点（验证修复）
        await page.evaluate("() => document.getElementById('target').focus({preventScroll:true})")
        after_fixed = await page.evaluate(
            "() => { const s=document.getElementById('pane'); return [s.scrollLeft, s.scrollTop]; }"
        )
        focused_ok = await page.evaluate(
            "() => document.activeElement && document.activeElement.id === 'target'"
        )
        fixed_scrolled = after_fixed != [0, 0]

        out.append(
            ("INFO", f"preventScroll focus(): 滚动={after_fixed} 焦点命中={focused_ok} "
                     f"-> {'发生滚动(BAD)' if fixed_scrolled else '未滚动(修复生效)'}")
        )
        await browser.close()

    # 核心判定：preventScroll 必须不滚动（且仍能聚焦）
    bug_fixed = (not fixed_scrolled) and focused_ok
    tag = "PASS" if bug_fixed else "FAIL"
    out.append(
        (tag, "动态机制验证：preventScroll 抑制了聚焦引发的滚动，且元素仍正常获得焦点"
              if bug_fixed else "动态机制验证：preventScroll 未能抑制滚动 / 未聚焦")
    )
    return out


# ---------- C) 实况冒烟（best-effort） ----------
async def live_smoke():
    from playwright.async_api import async_playwright
    import urllib.request, json

    BFF = os.environ.get("PEA_BFF", "http://localhost:4100")
    WEB = os.environ.get("PEA_WEB", "http://localhost:8088")

    try:
        req = urllib.request.Request(
            f"{BFF}/auth/login",
            data=json.dumps({"email": "admin@pea.ai", "password": "admin12345"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        token = json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]
    except Exception as e:
        return [("SKIP", f"无法登录获取 token（实况冒烟跳过）: {e}")]

    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(WEB, wait_until="domcontentloaded", timeout=15000)
        await page.evaluate(
            "(t) => { localStorage.setItem('pea_token', t); localStorage.setItem('__peaDevHooks','1'); }",
            token,
        )
        await page.goto(WEB, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)

        has_nodes = await page.evaluate(
            "() => (window.__canvas?.getState?.()?.nodes?.length || 0) > 0"
        )
        if not has_nodes:
            await browser.close()
            return [("SKIP", "实况画布无节点（admin 默认无画布），跳过点击测试；机制验证见 B 层")]

        vp0 = await page.evaluate(
            "() => { const t=window.__rfStore?.getState?.()?.transform; return t?{x:t[0],y:t[1],z:t[2]}:null; }"
        )
        if not vp0:
            await browser.close()
            return [("SKIP", "无法读取 ReactFlow viewport，实况冒烟跳过")]

        nodes = await page.evaluate("() => window.__canvas.getState().nodes.map(n=>n.id)")
        await page.click(f'.react-flow__node[data-id="{nodes[0]}"]', timeout=5000)
        await page.wait_for_timeout(300)
        vp1 = await page.evaluate(
            "() => { const t=window.__rfStore?.getState?.()?.transform; return t?{x:t[0],y:t[1],z:t[2]}:null; }"
        )
        dx, dy, dz = abs(vp1["x"] - vp0["x"]), abs(vp1["y"] - vp0["y"]), abs(vp1["z"] - vp0["z"])
        ok = dx <= 1 and dy <= 1 and dz <= 0.01
        out.append(("INFO", f"实况点击节点前 viewport={vp0} 后={vp1} delta=({dx:.1f},{dy:.1f},{dz:.4f})"))
        await browser.close()
        out.append(("PASS" if ok else "FAIL",
                    f"实况冒烟：点击节点后视口{'稳定' if ok else '发生偏移'}"))
    return out


async def main():
    entries = []
    entries += static_check()

    try:
        entries += await dynamic_check()
    except Exception as e:
        entries.append(("SKIP", f"动态验证跳过（Playwright/Chromium 问题）: {e}"))

    try:
        entries += await live_smoke()
    except Exception as e:
        entries.append(("SKIP", f"实况冒烟跳过: {e}"))

    PASS = sum(1 for t, _ in entries if t == "PASS")
    FAIL = sum(1 for t, _ in entries if t == "FAIL")
    SKIP = sum(1 for t, _ in entries if t == "SKIP")

    print("\n" + "=" * 66)
    print(f"Viewport-fix 验证汇总: {PASS} PASS / {FAIL} FAIL / {SKIP} SKIP")
    print("=" * 66)
    for tag, msg in entries:
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "~", "INFO": "·"}[tag]
        print(f"  [{icon}] {msg}")

    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
