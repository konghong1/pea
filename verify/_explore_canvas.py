"""探索：真实 UI 添加节点流程是否可用（验证 React #310 是否真的阻断菜单）"""
import asyncio, json, time
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
BFF = "http://localhost:4100"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context()
        pg = await ctx.new_page()
        errors = []
        pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("PAGEERR: " + str(e)))

        ts = int(time.time() * 1000)
        email = f"exp{ts}@pea.ai"
        reg = await ctx.request.post(f"{BFF}/auth/register",
            data=json.dumps({"email": email, "password": "Test1234!"}),
            headers={"Content-Type": "application/json"})
        regj = await reg.json()
        token = regj.get("token"); user = regj.get("user", {})
        print(f"REGISTER ok uid={user.get('id')}")
        await pg.add_init_script(
            f"localStorage.setItem('pea_token', {json.dumps(token)});"
            f"localStorage.setItem('pea_user', {json.dumps(json.dumps(user))});")
        await pg.goto(BASE + "/", timeout=20000)
        await pg.wait_for_selector(".pea-nav", timeout=15000)
        print("workspace reached")

        # 新建项目
        await pg.get_by_text("新建项目", exact=False).first.click()
        await pg.wait_for_timeout(2500)
        rf = await pg.locator(".react-flow").count()
        empty = await pg.get_by_text("还没有打开画布", exact=False).count()
        print(f"after 新建项目: react-flow={rf} emptyState={empty}")

        # 若仍在 workspace（未自动打开画布），尝试点击第一个项目卡片
        if rf == 0:
            cards = pg.locator(".project-card, .pea-project-card, [class*='project']")
            print(f"project cards found: {await cards.count()}")
            if await cards.count():
                await cards.first.click()
                await pg.wait_for_timeout(2500)
                rf = await pg.locator(".react-flow").count()
                empty = await pg.get_by_text("还没有打开画布", exact=False).count()
                print(f"after click card: react-flow={rf} emptyState={empty}")

        if rf == 0:
            print("CANNOT OPEN CANVAS — stop exploration")
            print("ERRORS:", errors[:10])
            await b.close()
            return

        # 双击画布 pane 打开节点库
        pane = pg.locator(".react-flow__pane").first
        box = await pane.bounding_box()
        cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
        await pg.mouse.dblclick(cx, cy)
        await pg.wait_for_timeout(1500)
        menu = await pg.locator(".pea-add-menu, .node-library, [role='menu']").count()
        print(f"after dblclick: add-menu count={menu}")
        # 打印可见菜单项文本
        items = pg.locator(".pea-add-menu-item, [role='menuitem']")
        n_items = await items.count()
        print(f"menu items: {n_items}")
        for i in range(n_items):
            t = await items.nth(i).inner_text()
            print(f"   item[{i}]={t.strip()}")

        # 点击“图片”项
        clicked = False
        for i in range(n_items):
            t = (await items.nth(i).inner_text()).strip()
            if "图片" in t:
                await items.nth(i).click()
                clicked = True
                print(f"clicked image item [{i}]={t}")
                break
        if not clicked:
            print("no 图片 item found")
        await pg.wait_for_timeout(2000)
        nodes = await pg.locator(".react-flow__node").count()
        print(f"nodes after add: {nodes}")
        print("ERRORS (first 10):")
        for e in errors[:10]:
            print("   !", e[:200])

        await b.close()

asyncio.run(main())
