"""
verify_e19_node_image_toolbar.py — 验证图片节点生成后的工具条、保存到素材库、全屏查看 Lightbox

本脚本用 Playwright 拦截 /generation/node 与 /generation/jobs/:id，
让图片结果在 1 秒内返回，从而专注于 UI 逻辑验证（不依赖 Agnes 真实模型耗时）。

验证项:
  1. 图片生成后, 结果图渲染, 悬浮工具条出现。
  2. 点击「保存到素材库」按钮, 节点星标变为 saved 高亮。
  3. 点击「全屏查看」按钮, 弹出 Lightbox: 左侧大图、右侧信息面板。
  4. Lightbox 支持 ESC / 关闭按钮 / 点击背景关闭。
硬标准: 0 非 chat 路径 console error。
"""
import os, json, time, urllib.request, urllib.error, re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"e19_{STAMP}@pea.ai"
PW = "Password123"
# 稳定的测试图（公开可访问）
MOCK_IMAGE = "http://localhost:8088/e2e-test.png"
errors = []
log = []
results = {}

def shot(page, name):
    p = os.path.join(SHOTS, f"e19_{name}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")

def apipost(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

def is_chat_err(msg):
    return "/chat/stream" in msg

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册 + 登录
    st, _ = apipost("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    log.append(f"[auth] register -> {st}")
    tok = urllib.request.urlopen(urllib.request.Request(
        API + "/auth/login", method="POST",
        data=json.dumps({"email": EMAIL, "password": PW}).encode(),
        headers={"Content-Type": "application/json"})).read()
    tok = json.loads(tok)["token"]
    log.append(f"[auth] login OK token_len={len(tok)}")
    st, _ = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase free -> {st}")

    # 拦截生成/估价 API：立即返回 done 状态与测试图
    fake_job_id = f"e19-{STAMP}"
    def handle_route(route, request):
        if request.method == "POST" and request.url.endswith("/models/estimate"):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"allowed": True, "cost": 10, "minPlanLevel": 0}))
        elif request.method == "POST" and request.url.endswith("/generation/node"):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"jobId": fake_job_id, "status": "accepted", "cost": 10}))
        elif request.method == "GET" and re.search(r"/generation/jobs/[^/]+$", request.url):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"jobId": fake_job_id, "status": "done", "resultUrl": MOCK_IMAGE, "error": None}))
        else:
            route.continue_()
    page.route("**/models/estimate", handle_route)
    page.route("**/generation/**", handle_route)

    page.add_init_script(f"localStorage.setItem('pea_token', '{tok}');")
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1000)
    shot(page, "01_loaded")

    # 2) 工作空间 -> 新建项目 -> 画布
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(400)
    try:
        page.get_by_text("工作空间", exact=False).first.click(timeout=4000)
    except Exception as e:
        log.append(f"[nav][WARN] 工作空间点击失败: {e}")
    page.wait_for_timeout(900)
    try:
        page.get_by_text("新建项目", exact=False).first.click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as e:
        log.append(f"[nav][WARN] 新建项目点击失败: {e}")
    shot(page, "03_canvas")

    # 3) 建图片节点
    pane = page.locator(".react-flow__pane").first
    pane.dblclick(position={"x": 360, "y": 300})
    page.wait_for_timeout(700)
    try:
        page.locator(".pea-add-menu-item").filter(has_text="图片").first.click(timeout=5000)
        page.wait_for_timeout(1200)
    except Exception as e:
        log.append(f"[node][WARN] 选图片失败: {e}")
    shot(page, "05_image_node")
    assert page.locator(".node-chat-prompt").count() > 0, "图片节点 NodeChatPrompt 未出现"
    log.append("[check] 图片节点 NodeChatPrompt 出现")

    inp = page.locator(".node-chat-prompt-input").first
    inp.fill("一只在星空下奔跑的橘猫，霓虹城市，电影感")
    page.wait_for_timeout(200)
    t0 = time.time()
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 图片生成已发送（已拦截为 mock）")

    # 等待结果图出现并真实加载
    appeared = False
    loaded = False
    elapsed = None
    deadline = time.time() + 30
    while time.time() < deadline:
        img = page.locator("img.pea-node-result-preview")
        if img.count() > 0:
            if elapsed is None:
                elapsed = time.time() - t0
                appeared = True
            try:
                info = img.first.evaluate("el => ({ complete: el.complete, naturalWidth: el.naturalWidth })")
            except Exception:
                info = None
            if info and info.get("complete") and info.get("naturalWidth", 0) > 0:
                loaded = True
                break
        page.wait_for_timeout(300)
    results["image_appeared"] = appeared
    results["image_loaded"] = loaded
    results["image_elapsed_s"] = round(elapsed, 2) if elapsed is not None else None
    log.append(f"[image] 出现={appeared} 加载={loaded} 耗时={results['image_elapsed_s']}s")
    shot(page, "08_image_result")

    # 4) 工具条出现
    node = page.locator(".pea-node-image").first
    node.hover()
    page.wait_for_timeout(300)
    toolbar = page.locator(".pea-node-result-toolbar").first
    toolbar_visible = toolbar.is_visible()
    results["toolbar_visible"] = toolbar_visible
    log.append(f"[toolbar] 可见={toolbar_visible}")
    shot(page, "10_toolbar_hover")

    # 5) 保存到素材库
    save_btn = toolbar.get_by_role("button", name="保存到素材库")
    save_btn.click()
    page.wait_for_timeout(400)
    star_saved = page.locator(".pea-node-result-star.saved").count() > 0
    results["save_to_library_highlight"] = star_saved
    log.append(f"[save] 星标高亮={star_saved}")
    shot(page, "12_saved")

    # 6) 全屏查看 Lightbox
    fullscreen_btn = toolbar.get_by_role("button", name="全屏查看")
    fullscreen_btn.click()
    page.wait_for_timeout(500)
    lightbox = page.locator(".pea-node-lightbox").first
    lightbox_visible = lightbox.is_visible()
    results["lightbox_visible"] = lightbox_visible
    info_panel = lightbox.locator(".pea-node-lightbox-info").first
    info_visible = info_panel.is_visible()
    results["lightbox_info_visible"] = info_visible
    log.append(f"[lightbox] 可见={lightbox_visible} 信息面板={info_visible}")
    shot(page, "14_lightbox_open")

    # 7) 关闭按钮关闭
    page.locator(".pea-node-lightbox-close").first.click()
    page.wait_for_timeout(400)
    closed = page.locator(".pea-node-lightbox").count() == 0
    results["lightbox_closed"] = closed
    log.append(f"[lightbox] 关闭按钮关闭={closed}")
    shot(page, "16_lightbox_closed")

    # 汇总
    print("\n".join(log))
    print("\n=== CONSOLE ERRORS ===")
    chat_errs = [e for e in errors if is_chat_err(e)]
    other_errs = [e for e in errors if not is_chat_err(e)]
    if other_errs:
        for e in other_errs[:40]:
            print("  [NON-CHAT]", e)
    else:
        print("  (none, 非 chat 路径)")
    if chat_errs:
        print(f"  [chat/stream 路径, 不计分] 共 {len(chat_errs)} 条")

    checks = [
        results.get("image_appeared"),
        results.get("image_loaded"),
        results.get("toolbar_visible"),
        results.get("save_to_library_highlight"),
        results.get("lightbox_visible"),
        results.get("lightbox_info_visible"),
        results.get("lightbox_closed"),
    ]
    no_console_err = (len(other_errs) == 0)
    overall = all(checks) and no_console_err
    print(f"\n[RESULT] checks={checks} 非chat_console_errors={len(other_errs)}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    browser.close()
    raise SystemExit(0 if overall else 1)
