"""debug: 复刻注册 -> 打开重命名菜单 -> 点击重命名 -> dump DOM 判断模态框为何不出现。"""
import asyncio
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        pg.set_default_timeout(20000)
        errs = []
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        create_calls = []
        pg.on("request", lambda r: create_calls.append(r.url) if r.method == "POST" and "/canvases" in r.url else None)

        # ---- 注册（复刻 verify 脚本逻辑）----
        await pg.goto(f"{BASE}/login")
        for sel in ["text=去注册", "button:has-text('去注册')", "button:has-text('注册')"]:
            el = pg.locator(sel).first
            if await el.count() and await el.is_visible():
                await el.click(); await pg.wait_for_timeout(500); break
        ins = pg.locator("input:visible")
        n = await ins.count()
        phs = [await ins.nth(i).get_attribute("placeholder") or "" for i in range(n)]
        typs = [await ins.nth(i).get_attribute("type") or "" for i in range(n)]
        await ins.nth(0).fill(f"dbg_{asyncio.get_event_loop().time()}@pea.ai")
        await ins.nth(1).fill("Test12345")
        for i in range(n):
            if typs[i] == "text" and "@" not in phs[i]:
                await ins.nth(i).fill("Dbg"); break
        for btn in await pg.locator("button:visible").all():
            t = (await btn.inner_text() or "").replace(" ", "")
            if "注册" in t or "登录" in t:
                await btn.click(); break
        await pg.wait_for_timeout(3000)
        print("URL after register:", pg.url)

        await pg.get_by_role("button", name="主页").first.click()
        await pg.wait_for_timeout(600)
        await pg.locator(".projects-card-create").click()
        await pg.wait_for_timeout(1500)
        await pg.get_by_role("button", name="主页").first.click()
        await pg.wait_for_timeout(800)
        print("cards:", await pg.locator(".projects-card:not(.projects-card-create)").count())
        print("POST /canvases calls so far:", create_calls)

        card = pg.locator(".projects-card:not(.projects-card-create)").first
        await card.hover(); await pg.wait_for_timeout(200)
        await card.locator(".projects-card-more").click()
        await pg.wait_for_timeout(500)

        mi = pg.get_by_role("menuitem", name="重命名")
        print("menuitem '重命名' count:", await mi.count())
        # 检查 menuitem 是否可见
        if await mi.count():
            print("menuitem visible:", await mi.first.is_visible())

        # 点击前 DOM 快照
        before = await pg.evaluate("() => ({modal: document.querySelectorAll('.ant-modal').length, root: document.querySelectorAll('.ant-modal-root').length})")
        print("before click:", before)

        await mi.first.click()
        await pg.wait_for_timeout(1500)

        after = await pg.evaluate("""() => {
          const out = {
            modal: document.querySelectorAll('.ant-modal').length,
            root: document.querySelectorAll('.ant-modal-root').length,
            wrap: document.querySelectorAll('.ant-modal-wrap').length,
            titleHasRename: !!Array.from(document.querySelectorAll('*')).find(e => e.className==='ant-modal-title' && e.textContent.includes('重命名')),
            bodyText: document.body.innerText.slice(0, 300)
          };
          return out;
        }""")
        print("after click:", after)
        # dump modal buttons
        btns = await pg.evaluate("""() => {
          const m = document.querySelector('.ant-modal');
          if (!m) return 'NO MODAL';
          return Array.from(m.querySelectorAll('button')).map(b => ({text: b.innerText, cls: b.className, role: b.getAttribute('role')}));
        }""")
        print("modal buttons:", btns)
        print("errors:", errs)
        await pg.screenshot(path="C:/workspace/pea/verify/_projects/dbg2.png")
        await b.close()


asyncio.run(main())
