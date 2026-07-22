import json, random, string, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173/"
log = {}

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(10000)

        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))

        # ---- register ----
        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(600)
        page.locator("text=注册").first.click()
        page.wait_for_timeout(400)
        email = f"gen_{''.join(random.choices(string.ascii_lowercase+string.digits, k=6))}@pea.test"
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
                vis.nth(i).fill("genuser")
        for btn in page.locator("button:visible").all():
            t = (btn.inner_text() or "").replace(" ", "")
            if "注册" in t:
                btn.click(); break
        page.wait_for_timeout(2500)
        log["after_register_url"] = page.url

        # capture balance before
        bal_before = page.locator("text=Tapies").first.inner_text()
        log["balance_before"] = bal_before

        # ---- add generate node via toolbar ----
        add_btn = page.locator("div.absolute.z-10 button", has_text="⚡ 生成")
        log["toolbar_add_visible"] = add_btn.count() > 0 and add_btn.first.is_visible()
        add_btn.first.click()
        page.wait_for_timeout(1200)

        # ---- select the node ----
        node = page.locator(".react-flow__node").first
        log["node_count"] = page.locator(".react-flow__node").count()
        node.click()
        page.wait_for_timeout(800)

        # ---- fill prompt ----
        ta = page.locator("textarea").first
        log["prompt_textarea_visible"] = ta.count() > 0 and ta.is_visible()
        ta.fill("a red apple on white background, product shot")
        page.wait_for_timeout(300)

        # ---- click Inspector generate ----
        insp_btn = page.locator("div.border-l button", has_text="⚡ 生成")
        log["inspector_generate_visible"] = insp_btn.count() > 0 and insp_btn.first.is_visible()
        insp_btn.first.click()
        log["generate_clicked"] = True
        page.wait_for_timeout(800)

        # ---- poll for done ----
        status = None
        for _ in range(30):
            # Inspector shows status text in a Tag
            try:
                txt = page.locator("div.border-l").inner_text()
            except Exception:
                txt = ""
            for s in ["done", "failed", "running", "queued"]:
                if s in txt:
                    status = s
                    break
            if status in ("done", "failed"):
                break
            time.sleep(1)
        log["final_job_status"] = status

        # balance after (WS may update)
        try:
            bal_after = page.locator("text=Tapies").first.inner_text()
        except Exception:
            bal_after = "(n/a)"
        log["balance_after"] = bal_after
        log["console_errors"] = console_errors
        browser.close()

    print(json.dumps(log, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
