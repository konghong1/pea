"""素材库 E2E 验证：个人/团队 scope、新建文件夹、进入文件夹、上传素材、收藏。
流程：注册 -> 新建项目 -> 进画布 -> 打开「文件/素材库」-> 创建/切换/上传/收藏。
"""
import os
import sys
import time
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def log(*a):
    print("[material]", *a, flush=True)

def check(name, cond, detail=""):
    if cond:
        log(f"PASS: {name}")
    else:
        log(f"FAIL: {name} {detail}")
        raise AssertionError(f"{name} {detail}")

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = '1';")
        pg = ctx.new_page()
        errs = []
        def on_console(m):
            if m.type == "error":
                errs.append(m.text)
                log("CONSOLE ERR:", m.text)
        pg.on("console", on_console)
        pg.on("pageerror", lambda e: errs.append("PAGEERR:" + str(e)) or log("PAGE ERR:", e))

        pg.goto(BASE, wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)

        # 捕获 404 等失败请求，便于诊断
        failed = []
        pg.on("requestfailed", lambda r: failed.append(f"REQFAIL {r.url} {r.failure}"))
        pg.on("response", lambda r: failed.append(f"RESP {r.status} {r.url}") if r.status >= 400 else None)

        # 注册/登录
        pg.wait_for_selector("button.ant-btn-primary", timeout=15000)
        submit_text = pg.locator("button.ant-btn-primary").inner_text(timeout=5000)
        if failed:
            log("NETWORK ISSUES:", failed[:10])
        if "注册" not in submit_text:
            pg.click("text=去注册", timeout=3000)
            pg.wait_for_timeout(500)
        email = "mat_%d@pea.ai" % int(time.time())
        pg.fill('input[placeholder="you@pea.ai"]', email)
        pg.fill('input[placeholder="至少 8 位"]', "Passw0rd!")
        try:
            pg.fill('input[placeholder="可选"]', "verify")
        except Exception:
            pass
        pg.click("button.ant-btn-primary")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=os.path.join(SHOTS, "material_after_auth.png"))
        pg.wait_for_selector("text=新建项目", timeout=12000)

        # 新建项目并进入画布
        pg.click("text=新建项目")
        pg.wait_for_timeout(1500)
        pg.wait_for_selector(".pea-canvas-flow", timeout=8000)
        pg.wait_for_timeout(600)
        pg.screenshot(path=os.path.join(SHOTS, "material_canvas.png"))
        check("画布工具栏存在", pg.locator("aside[aria-label='画布工具栏']").count() == 1)

        # 打开素材库
        pg.click("aside[aria-label='画布工具栏'] button[aria-label='文件']")
        pg.wait_for_timeout(500)
        log("panel count after click:", pg.locator(".pea-material-panel").count())
        pg.screenshot(path=os.path.join(SHOTS, "material_after_click.png"))
        pg.wait_for_selector(".pea-material-panel", timeout=5000)
        check("素材库面板展开", pg.is_visible(".pea-material-panel"))
        pg.screenshot(path=os.path.join(SHOTS, "material_open.png"))

        # 在个人 scope 下新建文件夹
        pg.click(".pea-material-header-right button[aria-label='新建']")
        pg.click("text=新建文件夹")
        pg.wait_for_selector(".ant-modal input", timeout=3000)
        pg.fill(".ant-modal input", "角色")
        pg.click(".ant-modal .ant-btn-primary")
        pg.wait_for_timeout(600)
        check("个人文件夹「角色」创建成功", pg.is_visible(".pea-material-row:has-text('角色')"))

        # 进入「角色」文件夹
        pg.click(".pea-material-row:has-text('角色')")
        pg.wait_for_timeout(400)
        check("进入文件夹后标题为角色", "角色" in pg.inner_text(".pea-material-title"))

        # 上传一个测试图片（1x1 透明 PNG）
        tmpdir = tempfile.mkdtemp()
        test_file = os.path.join(tmpdir, "test.png")
        # 最小合法 PNG 1x1 透明
        Path(test_file).write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452"
                "000000010000000108060000001f15c4"
                "890000000d49444154789c6360606060"
                "00000003010005a463b6000000004945"
                "4e44ae426082"
            )
        )
        pg.click(".pea-material-header-right button[aria-label='新建']")
        pg.click("text=上传")
        pg.set_input_files(".pea-material-panel input[type='file']", test_file)
        pg.wait_for_timeout(1200)
        pg.screenshot(path=os.path.join(SHOTS, "material_uploaded.png"))
        check("文件夹内出现素材", pg.locator(".pea-material-asset").count() >= 1)

        # 收藏素材
        pg.click(".pea-material-asset >> button >> nth=0")
        pg.wait_for_timeout(400)
        pg.click(".pea-material-header-left button[aria-label='返回']")
        pg.wait_for_timeout(400)
        pg.click(".pea-material-row:has-text('收藏')")
        pg.wait_for_timeout(600)
        pg.screenshot(path=os.path.join(SHOTS, "material_favorites.png"))
        check("收藏视图有素材", pg.locator(".pea-material-asset").count() >= 1)

        # 返回根目录，切换到团队 scope，创建文件夹
        pg.click(".pea-material-header-left button[aria-label='返回']")
        pg.wait_for_timeout(300)
        pg.click(".pea-material-scope >> text=团队")
        pg.wait_for_timeout(400)
        pg.click(".pea-material-header-right button[aria-label='新建']")
        pg.click("text=新建文件夹")
        pg.wait_for_selector(".ant-modal input", timeout=3000)
        pg.fill(".ant-modal input", "场景")
        pg.click(".ant-modal .ant-btn-primary")
        pg.wait_for_timeout(600)
        check("团队文件夹「场景」创建成功", pg.is_visible(".pea-material-row:has-text('场景')"))
        pg.screenshot(path=os.path.join(SHOTS, "material_team.png"))

        # 关闭面板
        pg.click(".pea-material-header-left button[aria-label='关闭']")
        pg.wait_for_timeout(400)
        check("素材库面板关闭", not pg.is_visible(".pea-material-panel"))

        check("无 console/page 错误", len(errs) == 0, str(errs[:5]))
        log("全部验证通过")
        b.close()

if __name__ == "__main__":
    main()
