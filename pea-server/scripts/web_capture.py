import json, os, random, string, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173/"
captured = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(8000)

        def on_response(resp):
            try:
                body = resp.text()
            except Exception:
                body = ""
            if resp.status >= 400:
                captured.append({
                    "method": resp.request.method,
                    "url": resp.request.url,
                    "status": resp.status,
                    "req_body": (resp.request.post_data or "")[:400],
                    "resp_body": body[:600],
                })

        page.on("response", on_response)

        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        page.locator("text=注册").first.click()
        page.wait_for_timeout(600)

        email = f"cap_{''.join(random.choices(string.ascii_lowercase+string.digits, k=6))}@pea.test"
        pw = "Smoke123!"
        vis = page.locator("input:visible")
        n = vis.count()
        phs = [vis.nth(i).get_attribute("placeholder") or "" for i in range(n)]
        types = [vis.nth(i).get_attribute("type") or "" for i in range(n)]
        for i in range(n):
            if "@" in phs[i] and "password" not in phs[i].lower():
                vis.nth(i).fill(email)
            elif types[i] == "password":
                vis.nth(i).fill(pw)
            elif types[i] == "text":
                vis.nth(i).fill("capuser")
        for btn in page.locator("button:visible").all():
            t = (btn.inner_text() or "").replace(" ", "")
            if "注册" in t or "登录" in t:
                btn.click()
                break
        # wait on dashboard for all lazy requests
        page.wait_for_timeout(4000)
        browser.close()

    print(json.dumps(captured, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
