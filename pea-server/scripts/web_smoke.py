import json, time
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/"
OUT_PNG = "/d/workspace/pea/pea-server/scripts/web_smoke.png"

console_errors = []
page_errors = []
failed_reqs = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 900})

        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("requestfailed", lambda r: failed_reqs.append(f"{r.method} {r.url} -> {r.failure}"))

        t0 = time.time()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2500)
        t_load = round(time.time() - t0, 2)

        title = page.title()
        root_children = page.eval_on_selector("#root", "el => el.childElementCount") if page.query_selector("#root") else -1
        body_text = (page.inner_text("body") or "")[:1400]

        page.screenshot(path=OUT_PNG, full_page=False)

        browser.close()

        result = {
            "url": URL,
            "load_seconds": t_load,
            "title": title,
            "root_child_count": root_children,
            "console_errors": console_errors,
            "page_errors": page_errors,
            "failed_requests": failed_reqs,
            "body_text_sample": body_text,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
