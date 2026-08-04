import time
import json
import os
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright, expect

WEB = "http://localhost:5173"
EMAIL = "admin@pea.ai"
PASSWORD = "konghong"
SHOT_DIR = "D:/workspace/pea/verify/shots"


def make_test_image(path: str):
    """生成一张 200x200 的测试图片，用于上传/收藏验证。"""
    img = Image.new("RGB", (200, 200), color=(31, 162, 220))
    img.save(path, "PNG")


def login(page):
    page.goto(f"{WEB}/login")
    page.fill("input#email", EMAIL)
    page.fill("input#password", PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    time.sleep(1.5)
    # SPA 登录成功后仍可能显示 /login URL，但页面会渲染 workspace 内容
    if page.locator("input#email").is_visible(timeout=3000):
        raise RuntimeError("login failed: login form still visible")


def open_canvas(page):
    """进入画布：优先打开第一个项目，没有则新建。"""
    page.goto(f"{WEB}/")
    page.wait_for_selector("text=未命名画布", timeout=20000)
    time.sleep(1)
    # 如果有项目卡片则打开第一个
    cards = page.locator("text=未命名画布").all()
    if cards:
        cards[0].click()
    else:
        page.click("text=新建项目")
        time.sleep(1)
    page.wait_for_selector(".react-flow__pane", timeout=30000)
    time.sleep(1)


def enable_dev_hooks(page):
    page.evaluate("""() => {
        localStorage.setItem('__peaDevHooks', '1');
    }""")
    page.reload()
    page.wait_for_selector(".react-flow__pane", timeout=30000)
    time.sleep(1)


def inject_image_node(page, image_path: str):
    """先上传图片到后端 MinIO，再创建一个带 fileKey 的 image 节点，用于测试一键收藏。"""
    with open(image_path, "rb") as f:
        data = f.read()
    result = page.evaluate("""async (data) => {
        const blob = new Blob([new Uint8Array(data)], { type: 'image/png' });
        const form = new FormData();
        form.append('file', blob, 'verify_test_image.png');
        const token = localStorage.getItem('pea_token') || '';
        const resp = await fetch('/api/files/upload', {
            method: 'POST',
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: form,
        });
        if (!resp.ok) throw new Error('upload failed: ' + resp.status);
        const { key } = await resp.json();
        const id = window.__canvas.getState().addNode(
            { kind: 'image', label: '验证图片', fileKey: key, url: '', isFavorite: false, savedToLibrary: false },
            { x: 500, y: 300 }
        );
        return { id, fileKey: key };
    }""", list(data))
    time.sleep(1.5)
    return result["id"]


def open_material_panel_favorites(page):
    """打开左侧素材面板并切换到收藏视图。"""
    page.click("[aria-label='收藏夹']")
    time.sleep(0.8)
    # 确保进入收藏视图：点击“收藏”行
    page.click(".pea-material-row:has-text('收藏')")
    time.sleep(0.8)


def open_material_panel_root(page):
    """打开左侧素材面板并保持在根目录视图。"""
    page.click("[aria-label='收藏夹']")
    time.sleep(0.8)


def count_favorite_assets(page):
    """统计收藏视图中当前可见的素材卡片数量。"""
    return page.locator(".pea-material-fav-grid .pea-material-thumb-wrap").count()


def run():
    os.makedirs(SHOT_DIR, exist_ok=True)
    img_path = os.path.join(SHOT_DIR, "verify_test_image.png")
    make_test_image(img_path)

    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        login(page)
        open_canvas(page)
        enable_dev_hooks(page)

        # =================== 问题1：节点一键收藏后左侧收藏夹实时刷新 ===================
        node_id = inject_image_node(page, img_path)
        open_material_panel_favorites(page)
        before = count_favorite_assets(page)
        page.screenshot(path=f"{SHOT_DIR}/fav_before_click.png")

        # 点击节点左上角收藏星标
        star = page.locator(f"[data-id='{node_id}'] .pea-node-result-star")
        star.click(timeout=5000)
        time.sleep(1.5)  # 等待 API + 面板刷新

        after = count_favorite_assets(page)
        page.screenshot(path=f"{SHOT_DIR}/fav_after_click.png")

        results["favorite_refresh"] = {
            "node_id": node_id,
            "before": before,
            "after": after,
            "ok": after > before,
        }

        # =================== 问题2：自己上传的内容有收藏键 ===================
        # 先取消收藏，回到 root 视图
        page.click(".pea-material-header-left button[aria-label='返回']")
        time.sleep(0.5)

        # 点击 + -> 上传
        page.click("[aria-label='新建']")
        time.sleep(0.3)
        page.click("text=上传")
        time.sleep(0.3)

        file_input = page.locator(".pea-material-panel input[type='file']")
        file_input.set_input_files(img_path)
        time.sleep(2)  # 等待上传完成并刷新列表

        page.screenshot(path=f"{SHOT_DIR}/upload_in_root.png")

        # 验证根目录素材卡片存在收藏按钮
        card = page.locator(".pea-material-root-assets .pea-material-thumb-wrap").first
        fav_btn = card.locator(".pea-material-thumb-actions button[aria-label='收藏'], .pea-material-thumb-actions button[aria-label='取消收藏']")
        results["upload_has_favorite_button"] = {
            "card_visible": card.is_visible(),
            "favorite_button_visible": fav_btn.is_visible(),
            "ok": card.is_visible() and fav_btn.is_visible(),
        }

        # 顺手验证点击收藏能生效
        fav_btn.click()
        time.sleep(1.5)
        page.click(".pea-material-row:has-text('收藏')")
        time.sleep(0.8)
        fav_count_after_upload_favorite = count_favorite_assets(page)
        page.screenshot(path=f"{SHOT_DIR}/upload_favorite_in_favorites.png")
        results["upload_favorite_works"] = {
            "favorite_count": fav_count_after_upload_favorite,
            "ok": fav_count_after_upload_favorite > 0,
        }

        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    run()
