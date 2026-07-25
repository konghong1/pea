"""
verify_e14_generation.py — Phase 4 #10 / #11 真机 E2E
驱动新生成入口（NodeChatPrompt）完整链路：
  注册 → 登录 → 购免费套餐(到账 Tapies) → 进画布 → 加图片节点
  → 选模型(动态加载) → 看预估 Tapies → 填提示词 → 发送
  → 节点进入"生成中" → 经 WS job.updated 异步回填结果(或终态)
硬标准：0 console error；节点最终离开生成中态（成功回填 / 失败退款均可）。
"""
import os, json, time, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"e14_{STAMP}@pea.ai"
PW = "Password123"
errors = []
log = []

def shot(page, name):
    p = os.path.join(SHOTS, f"e14_{name}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")
    return p

def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def apipost(method, path, token=None, body=None):
    """POST 容忍非 2xx（用于注册/购买可能返回 4xx 的场景）。"""
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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册（若已存在忽略）+ 登录拿 token
    st, _ = apipost("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    log.append(f"[auth] register -> {st}")
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    log.append(f"[auth] login OK, token len={len(tok)}")

    # 2) 购免费套餐（到账 1000 Tapies，planLevel 0 → 默认可用 image 模型）
    st, body = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase free -> {st} {body}")
    me = api("GET", "/users/me", token=tok)
    log.append(f"[me] balance={me.get('balance')} planLevel={me.get('planLevel')} effective={me.get('effectivePlanLevel')}")

    # 3) 注入登录态并打开应用
    page.add_init_script(f"localStorage.setItem('pea_token', '{tok}');")
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1000)
    shot(page, "01_loaded")

    # 4) 进入工作空间 → 新建项目（跳画布）
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(400)
    # 工作空间入口（UserMenu 中的"工作空间"）
    try:
        page.get_by_text("工作空间", exact=False).first.click(timeout=4000)
    except Exception as e:
        log.append(f"[nav][WARN] 工作空间点击失败: {e}")
    page.wait_for_timeout(900)
    shot(page, "02_workspace")

    # 新建项目按钮
    try:
        page.get_by_text("新建项目", exact=False).first.click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as e:
        log.append(f"[nav][WARN] 新建项目点击失败: {e}")
    shot(page, "03_canvas")

    # 5) 双击空白 → 节点库 → 选"图片"
    pane = page.locator(".react-flow__pane").first
    pane.dblclick(position={"x": 400, "y": 300})
    page.wait_for_timeout(700)
    shot(page, "04_nodelib")
    try:
        page.locator(".pea-add-menu-item").filter(has_text="图片").first.click(timeout=5000)
        page.wait_for_timeout(1200)
    except Exception as e:
        log.append(f"[node][WARN] 选图片失败: {e}")
    shot(page, "05_image_node")

    # 6) 节点被选中 → NodeChatPrompt 出现；打开模型选择浮层
    assert page.locator(".node-chat-prompt").count() > 0, "NodeChatPrompt 未出现（节点未选中）"
    log.append("[check] NodeChatPrompt 出现")

    # 模型浮层（动态加载可用模型）
    page.locator(".node-input-model").click()
    page.wait_for_timeout(900)
    shot(page, "06_model_picker")
    # 浮层内应有模型 <select>
    sel = page.locator(".node-model-picker select").first
    opts = sel.locator("option").all_inner_texts()
    log.append(f"[check] 模型选项: {opts}")
    assert len(opts) > 0, "模型列表为空（/models/available 未返回）"

    # 7) 预估 Tapies 应显示数字
    tapies = page.locator(".node-input-tapies").inner_text()
    log.append(f"[check] 预估条: {tapies}")
    assert "💎" in tapies and any(c.isdigit() for c in tapies), f"预估 Tapies 未显示数字: {tapies}"

    # 8) 填提示词并发送
    page.locator(".node-chat-prompt-input").fill("一只在星空下奔跑的橘猫，霓虹城市，电影感")
    page.wait_for_timeout(300)
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 已发送生成任务")
    page.wait_for_timeout(2000)
    shot(page, "07_submitted")

    # 9) 节点应进入"生成中"
    gen_seen = page.locator(".pea-node-generate-text").count() > 0
    log.append(f"[check] 发送后进入生成中: {gen_seen}")

    # 10) 等待异步回填（WS job.updated）：最多 120s
    done = False
    failed = False
    for _ in range(60):
        page.wait_for_timeout(2000)
        if page.locator(".pea-node-result-preview").count() > 0:
            done = True
            break
        # 仍在生成中？
        if page.locator(".pea-node-generate-text").count() == 0:
            # 生成态已消失但无结果预览 → 视为失败/退款终态
            failed = True
            break
    shot(page, "08_after_wait")
    log.append(f"[check] 结果回填(done={done}) / 终态无结果(failed={failed})")

    # 11) 汇总
    print("\n".join(log))
    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:40]:
            print("  ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    print(f"GENERATION E2E: {'PASS' if (done or failed) and len(errors)==0 else 'FAIL'} "
          f"(done={done}, failed_terminal={failed}, errors={len(errors)})")
    browser.close()
