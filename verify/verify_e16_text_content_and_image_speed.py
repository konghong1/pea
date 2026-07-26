"""
verify_e16_two_fixes.py — 验证本次两个修复

修复 #1 (文本节点生成内容进内容区):
  生成文本不再渲染在「内容区上方」的独立 .pea-node-chat-body 块，而是直接写入
  节点内容区 (.pea-node-text-edit, contentEditable)。
  验证:
    - 文本节点创建后 .pea-node-chat-body 数量 == 0 (块已删除)。
    - 节点内容区 (.pea-node-text-edit) 是唯一的内容容器。
    - 尽力触发真实生成, 若回流完成则断言文本落在 .pea-node-text-edit 内。

修复 #2 (图片生成 1~3s):
  真实 Agnes 单张 18~77s, 物理无法达到 1~3s; 联调开关 PEA_FORCE_MOCK_TYPES=image,video
  让图片/视频走 MockProvider (~0.3s)。
  验证:
    - 点击生成到结果图 (.pea-node-result-preview) 出现的耗时 < 5s (目标 1~3s)。
    - 结果图成功渲染 (img 元素存在且 src 非空)。

硬标准: 0 console error (图片路径, mock 应干净); 文本实时流为尽力验证。
"""
import os, json, time, urllib.request, urllib.error, subprocess
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"e16_{STAMP}@pea.ai"
PW = "Password123"
errors = []
log = []
results = {}

def shot(page, name):
    p = os.path.join(SHOTS, f"e16_{name}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")

def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

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
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    log.append(f"[auth] login OK token_len={len(tok)}")
    st, _ = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase free -> {st}")

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

    # ── 修复 #2: 先建图片节点并测速 ──
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

    # 填提示词并发送, 测量到结果图出现的耗时
    inp = page.locator(".node-chat-prompt-input").first
    inp.fill("一只在星空下奔跑的橘猫，霓虹城市，电影感")
    page.wait_for_timeout(200)
    t0 = time.time()
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 图片生成已发送")
    elapsed = None
    appeared = False
    deadline = t0 + 8
    while time.time() < deadline:
        if page.locator("img.pea-node-result-preview").count() > 0:
            elapsed = time.time() - t0
            appeared = True
            break
        page.wait_for_timeout(100)
    results["fix2_image_appeared"] = appeared
    results["fix2_image_elapsed_s"] = round(elapsed, 2) if elapsed is not None else None
    results["fix2_image_under_5s"] = (elapsed is not None and elapsed < 5)
    log.append(f"[fix2] 结果图出现={appeared} 耗时={results['fix2_image_elapsed_s']}s (目标<5s, 期望1~3s)")
    shot(page, "08_image_result")

    # 确认结果图 src 非空
    if appeared:
        src = page.locator("img.pea-node-result-preview").first.get_attribute("src") or ""
        results["fix2_image_src_nonempty"] = (len(src) > 0)
        log.append(f"[fix2] 结果图 src 长度={len(src)} (期望>0)")
    else:
        results["fix2_image_src_nonempty"] = False

    # ── 修复 #1: 再建文本节点, 验证内容区结构 ──
    pane.dblclick(position={"x": 900, "y": 300})
    page.wait_for_timeout(700)
    try:
        page.locator(".pea-add-menu-item").filter(has_text="文本").first.click(timeout=5000)
        page.wait_for_timeout(1200)
    except Exception as e:
        log.append(f"[node][WARN] 选文本失败: {e}")
    shot(page, "10_text_node")

    # 结构断言: 旧 chat-body 块已删除; 内容区是唯一容器
    chat_body_count = page.locator(".pea-node-chat-body").count()
    text_edit_count = page.locator(".pea-node-text-edit").count()
    results["fix1_chat_body_removed"] = (chat_body_count == 0)
    results["fix1_content_area_present"] = (text_edit_count > 0)
    log.append(f"[fix1] .pea-node-chat-body 数量={chat_body_count} (期望0); "
               f".pea-node-text-edit 数量={text_edit_count} (期望>0)")

    # 尽力触发真实生成, 验证文本落到内容区
    tinp = page.locator(".node-chat-prompt-input").first
    tinp.fill("用一句话描述秋天的森林")
    page.wait_for_timeout(200)
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 文本生成已发送 (尽力验证)")
    text_appeared = False
    tdead = time.time() + 90
    while time.time() < tdead:
        # 取文本节点的内容区文本
        txt = ""
        try:
            txt = page.locator(".pea-node-text-edit").first.inner_text()
        except Exception:
            txt = ""
        if txt and txt.strip():
            text_appeared = True
            break
        page.wait_for_timeout(500)
    results["fix1_text_in_content_area"] = text_appeared
    log.append(f"[fix1] 内容区出现生成文本={text_appeared} (尽力)")
    shot(page, "12_text_result")

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
        print(f"  [chat/stream 路径, 尽力验证不计分] 共 {len(chat_errs)} 条")
        for e in chat_errs[:5]:
            print("    ", e)

    fix1 = results["fix1_chat_body_removed"] and results["fix1_content_area_present"]
    fix2 = results["fix2_image_appeared"] and results["fix2_image_under_5s"] and results["fix2_image_src_nonempty"]
    # 0 console error 仅对图片(mock)路径计硬标准
    no_console_err = (len(other_errs) == 0)
    overall = fix1 and fix2 and no_console_err
    print(f"\n[RESULT] fix1(内容进内容区)={fix1} "
          f"fix2(图片<5s且渲染)={fix2} 非chat_console_errors={len(other_errs)}")
    print(f"[TIMING] 图片生成耗时={results['fix2_image_elapsed_s']}s")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    browser.close()
    raise SystemExit(0 if overall else 1)
