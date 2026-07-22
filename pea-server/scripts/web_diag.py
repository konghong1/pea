import json, random, string
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173/"
con = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(8000)

        def on_console(msg):
            if msg.type() == "error":
                con.append(msg.text[:200])

        page.on("console", on_console)
        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(800)
        page.locator("text=注册").first.click()
        page.wait_for_timeout(500)
        email = f"diag_{''.join(random.choices(string.ascii_lowercase+string.digits, k=6))}@pea.test"
        vis = page.locator("input:visible")
        n = vis.count()
        phs = [vis.nth(i).get_attribute("placeholder") or "" for i in range(n)]
        types = [vis.nth(i).get_attribute("type") or "" for i in range(n)]
        for i in range(n):
            if "@" in phs[i] and "password" not in phs[i].lower():
                vis.nth(i).fill(email)
            elif types[i] == "password":
                vis.nth(i).fill("Smoke123!")
            elif types[i] == "text":
                vis.nth(i).fill("diaguser")
        for btn in page.locator("button:visible").all():
            t = (btn.inner_text() or "").replace(" ", "")
            if "注册" in t:
                btn.click(); break
        page.wait_for_timeout(4000)
        browser.close()
    print(json.dumps(con, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
