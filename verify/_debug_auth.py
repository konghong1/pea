"""Debug auth state after login."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://localhost:8088/login", timeout=15000)
        await page.wait_for_timeout(2000)

        inputs = await page.locator("input").all()
        await inputs[0].fill("v3test@test.com")
        await inputs[1].fill("Test123456")
        await inputs[1].press("Enter")
        await page.wait_for_timeout(5000)

        print(f"URL: {page.url}")

        # Check cookies
        cookies = await page.context.cookies()
        print(f"Cookies ({len(cookies)}):")
        for c in cookies:
            v = c["value"][:40]
            print(f"  {c['name']}: {v}")

        # Check localStorage
        ls = await page.evaluate("""() => {
            var keys = Object.keys(localStorage);
            var result = {keys: keys};
            for (var i = 0; i < keys.length; i++) {
                result[keys[i]] = localStorage.getItem(keys[i]).substring(0, 50);
            }
            return result;
        }""")
        print(f"LocalStorage: {json.dumps(ls, indent=2)}")

        # Screenshot home
        await page.screenshot(path=r"C:\workspace\pea\verify\shot_v3_home.png")
        await browser.close()

asyncio.run(main())
