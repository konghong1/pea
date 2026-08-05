"""隔离复现：document.execCommand(formatBlock) 在 contentEditable + 工具栏场景下的行为。

跑法：python verify/tne_exec_repro_test.py
依赖：playwright (python) + 已安装 chromium。
"""
import os
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = "file://" + os.path.join(HERE, "tne_exec_repro.html")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda m: print("CONSOLE:", m.text))
        page.goto(HTML)
        page.wait_for_selector("#editor")

        # 1) 先把光标放进编辑区（模拟用户已点进去输入过）
        page.click("#editor")
        page.evaluate("() => { const e=document.getElementById('editor'); const r=document.createRange(); r.selectNodeContents(e); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); }")

        results = {}
        for label, btn in [("onClick(当前代码同款)", "#btn-click"),
                           ("mousedown直接", "#btn-md"),
                           ("md-prevent+onClick", "#btn-md-pre")]:
            # 重置编辑区内容
            page.evaluate("() => { const e=document.getElementById('editor'); e.innerHTML='这是一段测试文本，用来验证 execCommand 是否能把这段文字变成一级标题。'; const r=document.createRange(); r.selectNodeContents(e); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); }")
            page.click(btn)
            page.wait_for_timeout(150)
            html = page.evaluate("() => document.getElementById('editor').innerHTML")
            has_h1 = "<h1" in html.lower()
            results[label] = {"html_head": html[:70], "has_h1": has_h1}
            print(f"\n=== {label} ===")
            print("  innerHTML 前70:", html[:70])
            print("  -> 是否生成 <h1>:", has_h1)

        browser.close()
        print("\n=== 结论 ===")
        for k, v in results.items():
            print(f"  {k}: has_h1={v['has_h1']}")

if __name__ == "__main__":
    main()
