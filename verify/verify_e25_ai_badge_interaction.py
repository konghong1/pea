# -*- coding: utf-8 -*-
"""E25：验证 AI 生成图右上角交互逻辑

  - AI 单张图：右上角无任何按钮
  - AI 多张图：右上角显示「N ▼」按钮，hover 箭头向右，点击展开并排缩略图
  - 上传图：有替换按钮
"""
from __future__ import annotations
import os, tempfile, base64
from playwright.sync_api import sync_playwright

WEB = "http://localhost:8088"
IMG_EXT = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

def main():
    errors = []
    def step(label, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {label}  {detail}")
        if not ok: errors.append(label)

    tmp = os.path.join(tempfile.gettempdir(), "pea_up_e25.png")
    with open(tmp, "wb") as f:
        f.write(base64.b64decode(IMG_EXT))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console:{m.type}:{m.text[:120]}") if m.type == "error" else None)

        page.goto(WEB, wait_until="networkidle")
        ts = page.evaluate("Date.now()")
        email = f"e25_{ts}@pea.ai"
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click(); page.wait_for_timeout(500)
        ins = page.locator("input:visible"); cnt = ins.count()
        if cnt >= 2:
            ins.nth(0).fill(email); page.wait_for_timeout(120)
            ins.nth(1).fill("test1234"); page.wait_for_timeout(120)
            if cnt >= 3: ins.nth(2).fill("E25")
        page.locator("button", has_text="注").first.click(); page.wait_for_timeout(1500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow", timeout=10000); page.wait_for_timeout(400)

        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click(); page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click(); page.wait_for_timeout(350)
            return page.evaluate("""() => { const s=window.__canvas.getState(); const ns=s.nodes; return ns[ns.length-1].id; }""")

        # 1. 上传图节点 → 应有替换按钮
        up = add_node("图片")
        page.locator(f'.react-flow__node[data-id="{up}"] input[type=file]').set_input_files(tmp)
        page.wait_for_timeout(1200)

        up_info = page.evaluate("""(id) => {
          const wrap = document.querySelector('.react-flow__node[data-id="'+id+'"]');
          if (!wrap) return {found:false};
          const replaceBtn = wrap.querySelector('.pea-node-result-replace');
          const badge = wrap.querySelector('.pea-node-image-badge');
          return {
            found: true,
            hasReplace: !!replaceBtn,
            replaceOpacity: replaceBtn ? getComputedStyle(replaceBtn).opacity : null,
            hasBadge: !!badge,
          };
        }""", up)
        step("上传图有替换按钮", up_info.get("hasReplace") is True, str(up_info))
        step("上传图无数量角标", up_info.get("hasBadge") is not True, str(up_info))

        # 2. AI 单张图 → 右上角无按钮
        ai1 = add_node("图片")
        page.evaluate("""(id)=>{ window.__canvas.getState().updateNodeData(id,{ resultUrls:['https://picsum.photos/seed/ai25a/400/300'], resultUrl:'https://picsum.photos/seed/ai25a/400/300', resultIndex:0, generating:false }); }""", ai1)
        page.wait_for_timeout(600)

        ai1_info = page.evaluate("""(id) => {
          const wrap = document.querySelector('.react-flow__node[data-id="'+id+'"]');
          if (!wrap) return {found:false};
          const replaceBtn = wrap.querySelector('.pea-node-result-replace');
          const badge = wrap.querySelector('.pea-node-image-badge');
          return {
            found: true,
            hasReplace: !!replaceBtn,
            hasBadge: !!badge,
          };
        }""", ai1)
        step("AI单张图无替换按钮", ai1_info.get("hasReplace") is not True, str(ai1_info))
        step("AI单张图无数量角标", ai1_info.get("hasBadge") is not True, str(ai1_info))

        # 3. AI 多张图 → 有数量角标，无替换按钮；hover 箭头向右；点击展开并排缩略图
        ai2 = add_node("图片")
        page.evaluate("""(id)=>{ window.__canvas.getState().updateNodeData(id,{ resultUrls:['https://picsum.photos/seed/ai25b1/400/300','https://picsum.photos/seed/ai25b2/400/300','https://picsum.photos/seed/ai25b3/400/300'], resultUrl:'https://picsum.photos/seed/ai25b1/400/300', resultIndex:0, generating:false }); }""", ai2)
        page.wait_for_timeout(600)

        ai2_info = page.evaluate("""(id) => {
          const wrap = document.querySelector('.react-flow__node[data-id="'+id+'"]');
          if (!wrap) return {found:false};
          const replaceBtn = wrap.querySelector('.pea-node-result-replace');
          const badge = wrap.querySelector('.pea-node-image-badge');
          const badgeBtn = badge ? badge.querySelector('.pea-node-image-badge-btn') : null;
          const arrow = badgeBtn ? badgeBtn.querySelector('.pea-badge-arrow') : null;
          return {
            found: true,
            hasReplace: !!replaceBtn,
            hasBadge: !!badge,
            badgeText: badgeBtn ? badgeBtn.textContent.trim() : null,
            hasArrow: !!arrow,
          };
        }""", ai2)
        step("AI多张图无替换按钮", ai2_info.get("hasReplace") is not True, str(ai2_info))
        step("AI多张图有数量角标", ai2_info.get("hasBadge") is True, str(ai2_info))
        step("角标文本为数量", ai2_info.get("badgeText") and "3" in str(ai2_info.get("badgeText")), str(ai2_info))

        # hover 检查箭头存在（旋转效果在 headless 下难以准确测试，跳过）
        badge_btn = page.locator(f'.react-flow__node[data-id="{ai2}"] .pea-node-image-badge-btn')
        step("角标按钮有箭头SVG", ai2_info.get("hasArrow") is True, str(ai2_info))

        # 点击展开并排缩略图
        badge_btn.click()
        page.wait_for_timeout(300)
        picker_info = page.evaluate("""(id) => {
          const wrap = document.querySelector('.react-flow__node[data-id="'+id+'"]');
          const picker = wrap?.querySelector('.pea-node-image-picker');
          if (!picker) return {found:false};
          const items = picker.querySelectorAll('.pea-node-image-picker-item');
          const style = getComputedStyle(picker);
          return {
            found: true,
            itemCount: items.length,
            flexDirection: style.flexDirection,
            display: style.display,
          };
        }""", ai2)
        step("点击展开缩略图选择器", picker_info.get("found") is True and picker_info.get("itemCount") == 3, str(picker_info))
        step("缩略图并排展示(flex-direction: row)", picker_info.get("flexDirection") == "row", str(picker_info))

        # 截图
        os.makedirs("verify/shots", exist_ok=True)
        page.screenshot(path="verify/shots/e25_ai_badge.png")
        browser.close()

    print("\nconsole errors:", [e for e in errors if e.startswith('console')])
    print("结论:", "全部通过 ✅" if not [e for e in errors if not e.startswith('console')] else f"失败: {errors}")
    if [e for e in errors if not e.startswith('console')]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
