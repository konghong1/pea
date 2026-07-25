"""
电商套图 · 样式探针（API 注入登录态，避免 UI 注册表单抖动）
- 调用 bff /auth/register 拿到 token
- 注入 localStorage(pea_token / pea_user) 后 reload，进入工作台
- 点击「电商套图」导航 → 等待 .gallery-page
- 抽取关键元素 computed style，确认令牌已生效
- 截图 verify/shot_ecom.png
"""
import asyncio, re, os, json, time, urllib.request
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
BFF = "http://localhost:4100"
SHOT = os.path.join(os.path.dirname(__file__), "shot_ecom.png")

def api_register():
    email = f"probe_{int(time.time())}@pea.ai"
    data = json.dumps({"email": email, "password": "Test1234!"}).encode()
    req = urllib.request.Request(BFF + "/auth/register", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

async def cs(page, sel):
    try:
        el = await page.query_selector(sel)
        if not el:
            return None
        return await el.evaluate("e => ({"
            "backgroundColor:getComputedStyle(e).backgroundColor,"
            "color:getComputedStyle(e).color,"
            "fontFamily:getComputedStyle(e).fontFamily,"
            "borderRightWidth:getComputedStyle(e).borderRightWidth,"
            "borderRightColor:getComputedStyle(e).borderRightColor,"
            "borderRadius:getComputedStyle(e).borderRadius})")
    except Exception:
        return None

def show(label, el):
    if el is None:
        return f"{label}: <未找到>"
    return (f"{label}: bg={el['backgroundColor']} color={el['color']} "
            f"ff={el['fontFamily'][:24]} br={el['borderRightWidth']}{el['borderRightColor']} "
            f"radius={el['borderRadius']}")

async def main():
    reg = api_register()
    token, user = reg["token"], reg["user"]
    print("REG:", user["email"], "uid=", user["id"])

    errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        page = await b.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))

        await page.goto(BASE, timeout=20000)
        await page.evaluate(
            "(args) => { localStorage.setItem('pea_token', args.t);"
            "localStorage.setItem('pea_user', JSON.stringify(args.u)); }",
            {"t": token, "u": user})
        # 关键：不要 reload（会停留在 /login，被显式 /login 路由拦截）；直接跳到 / 触发 token 门控
        await page.goto(BASE + "/", timeout=20000)
        try:
            await page.wait_for_selector(".pea-nav", timeout=15000)
            print("NAV: ok (.pea-nav visible)")
        except Exception as e:
            await page.screenshot(path=SHOT)
            print("NAV FAIL:", str(e)[:120], "| screenshot saved")
            await b.close()
            return

        # 进入电商套图（状态路由，点导航）
        try:
            await page.get_by_role("button", name="电商套图").click(timeout=5000)
        except Exception:
            await page.get_by_text("电商套图").click()
        await page.wait_for_selector(".gallery-page", timeout=10000)
        await asyncio.sleep(0.8)

        reps = {
            ".gallery-page": await cs(page, ".gallery-page"),
            ".config-panel": await cs(page, ".config-panel"),
            ".content-area": await cs(page, ".content-area"),
            ".btn-generate": await cs(page, ".btn-generate"),
            ".btn-planner": await cs(page, ".btn-planner"),
            ".planner-bar": await cs(page, ".planner-bar"),
            ".g-panel": await cs(page, ".g-panel"),
            ".plan-list": await cs(page, ".plan-list"),
            ".dg-card": await cs(page, ".dg-card"),
            ".page-title": await cs(page, ".page-title"),
        }
        print("==== computed styles ====")
        for k, v in reps.items():
            print(show(k, v))

        # 打开策划台抽屉，确认 drawer 也有样式
        try:
            await page.get_by_text(re.compile(r"AI智能策划台|策划")).first.click(timeout=4000)
            await asyncio.sleep(0.5)
            dr = await cs(page, ".g-drawer")
            print(show(".g-drawer", dr))
        except Exception as e:
            print(".g-drawer: open-skip", str(e)[:60])

        await page.screenshot(path=SHOT, full_page=False)
        print("SCREENSHOT:", SHOT)
        print("CONSOLE ERRORS:", len(errors))
        for e in errors[:10]:
            print("  -", e[:160])
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
