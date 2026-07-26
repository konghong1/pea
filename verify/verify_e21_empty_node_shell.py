"""
E21 — 空节点（刚添加、未生成内容）外壳统一验证
================================================
对照用户诉求：添加节点时节点样式也要适配，不要显得突兀。

核验点：
  1) 注册 + 进入画布（启用 dev hooks）
  2) 通过“添加节点”菜单创建 4 个空节点（文本/图片/视频/音频），不注入任何结果
  3) 每个空节点头部都是统一透明小标签 .pea-node-tag-pill（不再有悬浮大黑“上传”药丸 .pea-node-upload-btn）
  4) 空媒体节点（图片/视频/音频）内部有安静上传区：.pea-node-media-placeholder + .pea-node-media-upload 按钮
  5) 4 个空节点 body-card 宽度一致（=280px），与结果态统一
  6) 空媒体节点可见 file input（上传入口仍可达、功能没坏）
  7) 0 非 chat console error
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)

results = []
console_errors = []


def step(name, ok, note=""):
    results.append((name, ok, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")


def shot(page, name):
    p = SHOTS / f"e21_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    return p


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        # 1) 注册 + 进入画布（启用 dev hooks）
        page.add_init_script("window.__peaDevHooks = 1;")
        page.goto(BASE, wait_until="networkidle")
        ts = int(time.time() * 1000)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', f"e21_{ts}@pea.ai")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "E21")
        page.locator("form button[type=submit]").click()
        try:
            page.wait_for_selector("text=新建项目", timeout=15000)
        except Exception:
            shot(page, "00_debug_after_register")
            print("DEBUG body:", page.inner_text("body")[:300])
            raise
        page.wait_for_timeout(800)
        new_btns = page.get_by_role("button", name="新建项目").all()
        if new_btns:
            new_btns[0].click()
            page.wait_for_selector(".react-flow", timeout=15000)
        page.wait_for_timeout(1200)
        step("注册+进入画布", True)

        # 2) 通过“添加节点”菜单创建 4 个空节点（不注入任何结果）
        def open_add_menu():
            page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click()
            page.wait_for_selector(".pea-add-menu", timeout=4000)

        def pick(text):
            open_add_menu()
            items = page.locator(".pea-add-menu-item").all()
            for it in items:
                if text in (it.text_content() or ""):
                    box = it.bounding_box()
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.wait_for_timeout(600)
                    return
            raise RuntimeError(f"menu item {text!r} not found")

        for kind in ("文本", "图片", "视频", "音频"):
            pick(kind)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.wait_for_selector('.pea-node[data-kind="audio"]', timeout=8000)
        total = page.locator(".pea-node").count()
        step(f"创建四个空节点(文本/图片/视频/音频) count={total}", total >= 4)

        shot(page, "01_empty_nodes")

        # 3) 头部统一透明小标签，无悬浮上传药丸
        upload_pills = page.locator(".pea-node-upload-btn").count()
        tag_pills = page.locator(".pea-node .pea-node-tag-pill").count()
        step(f"头部统一透明小标签(无悬浮上传药丸) upload_pill={upload_pills} tag_pill={tag_pills}",
             upload_pills == 0 and tag_pills >= 4)

        # 4) 空媒体节点有安静上传区（placeholder + 幽灵上传按钮）
        zones = 0
        for k in ("image", "video", "audio"):
            node = page.locator(f'.pea-node[data-kind="{k}"]')
            if node.count() == 0:
                continue
            ph = node.locator(".pea-node-media-placeholder")
            btn = node.locator(".pea-node-media-upload")
            if ph.count() > 0 and btn.count() > 0:
                zones += 1
        step(f"空媒体节点有安静上传区(placeholder+按钮) zones={zones}/3", zones == 3)

        # 5) 4 个空节点 body-card 宽度一致 = 280
        widths = []
        for k in ("text", "image", "video", "audio"):
            node = page.locator(f'.pea-node[data-kind="{k}"]')
            if node.count() == 0:
                continue
            w = node.locator(".pea-node-body-card").first.evaluate(
                "el => Math.round(el.getBoundingClientRect().width)")
            widths.append(w)
        uniq = sorted(set(widths))
        step(f"四个空节点 body-card 宽度一致 widths={widths} unique={uniq}",
             len(uniq) == 1 and uniq[0] == 280)

        # 6) 空媒体节点可见 file input（上传入口仍可用）
        file_inputs = 0
        for k in ("image", "video", "audio"):
            node = page.locator(f'.pea-node[data-kind="{k}"]')
            if node.count() == 0:
                continue
            if node.locator('input[type="file"]').count() > 0:
                file_inputs += 1
        step(f"空媒体节点 file input 可达 inputs={file_inputs}/3", file_inputs == 3)

        # 7) 空媒体节点的上传按钮可见且可交互（不在 headless 真点，避免触发原生文件选择框卡住）
        img_node = page.locator('.pea-node[data-kind="image"]')
        if img_node.count() > 0:
            up = img_node.locator(".pea-node-media-upload").first
            visible = up.is_visible()
            enabled = up.is_enabled()
            step("空节点上传按钮可见且可交互", visible and enabled)
        else:
            step("空节点上传按钮可见且可交互", False, "no image node")

        shot(page, "02_empty_nodes_header")

        browser.close()

    print("\n========= E21 空节点外壳统一验证汇总 =========")
    for n, ok, note in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}  {note}")
    print(f"\nconsole errors: {len(console_errors)}")
    for e in console_errors[:20]:
        print("   -", e)
    # 过滤掉 chat/SSE 类噪声（与本次改动无关）
    non_chat = [e for e in console_errors
                if not any(x in e.lower() for x in ("chat", "eventsource", "sse", "[vite]"))]
    print(f"非 chat console errors: {len(non_chat)}")
    failed = [n for n, ok, _ in results if not ok]
    print("\n结论:", "全部通过 ✅" if not failed and not non_chat else "有失败/报错 ⚠️")
    sys.exit(0 if not failed and not non_chat else 1)


if __name__ == "__main__":
    main()
