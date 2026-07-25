import asyncio, json, re, sys, urllib.request

BASE = "http://localhost:8088"

def api(method, path, data=None):
    url = f"http://localhost:4100{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

async def main():
    from playwright.async_api import async_playwright
    errors = []
    out = {}

    # 1) 注册拿 token
    email = f"cfg_{int(asyncio.get_event_loop().time())}@pea.ai"
    try:
        resp = api("POST", "/auth/register", {"email": email, "password": "Test1234!"})
        token = resp["token"]; user = resp.get("user", {})
    except Exception as e:
        print("REGISTER_FAIL", e); sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error","warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        await page.goto(BASE, timeout=20000)
        await page.evaluate(
            "(a)=>{ localStorage.setItem('pea_token', a.t); localStorage.setItem('pea_user', JSON.stringify(a.u)); }",
            {"t": token, "u": user})
        # 关键：navigate 到 / 而非 reload，否则 /login 路由会抢在 token 网关前
        await page.goto(BASE + "/", timeout=20000)
        try:
            await page.wait_for_selector(".pea-nav", timeout=10000)
            out["nav"] = True
        except Exception:
            out["nav"] = False
            print("NAV_FAIL url=", page.url); await page.screenshot(path="shot_ecom_cfg.png"); await browser.close(); print(json.dumps(out)); return

        # 2) 进入电商套图
        try:
            await page.get_by_text("电商套图").first.click(timeout=8000)
            await page.wait_for_selector(".gallery-page", timeout=10000)
            out["gallery_page"] = True
        except Exception as e:
            out["gallery_page"] = False
            print("GALLERY_FAIL", str(e)); await page.screenshot(path="shot_ecom_cfg.png"); await browser.close(); print(json.dumps(out)); return

        # 3) 市场配置：打开第一个 Select，数选项
        try:
            sel = page.locator(".cfg-field .ant-select-selector").first
            await sel.click(timeout=5000)
            await page.wait_for_selector(".ant-select-dropdown:visible .ant-select-item-option", timeout=5000)
            n = await page.locator(".ant-select-dropdown:visible .ant-select-item-option").count()
            out["market_first_select_options"] = n
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception as e:
            out["market_first_select_options"] = -1
            out["market_err"] = str(e)

        # 市场配置字段数量
        out["market_fields"] = await page.locator(".cfg-field").count()

        # 4) 打开策划台，数推荐类型卡片
        try:
            await page.locator(".btn-plan-ai").click(timeout=8000)
            await page.wait_for_selector(".g-drawer", timeout=8000)
            await page.wait_for_selector(".dg-card", timeout=8000)
            n_types = await page.locator(".dg-card").count()
            out["recommended_type_cards"] = n_types
        except Exception as e:
            out["recommended_type_cards"] = -1
            out["planner_err"] = str(e)

        await page.screenshot(path="shot_ecom_cfg.png", full_page=False)
        await browser.close()

    # 过滤掉已知非样式/非功能性的 console（如 /api/gallery/tasks/stream 404）
    real = [e for e in errors if "tasks/stream" not in e and "favicon" not in e]
    out["console_real_errors"] = real
    out["console_raw_count"] = len(errors)
    print(json.dumps(out, ensure_ascii=False, indent=2))

asyncio.run(main())
