import json, os, random, string, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173/"
# Use Windows-absolute paths (managed python is native Windows python; /d/... != D:/...)
SHOT_DIR = "D:/workspace/pea/pea-server/scripts/shots"
os.makedirs(SHOT_DIR, exist_ok=True)

console_errors, page_errors, failed_reqs = [], [], []

def shot(page, name):
    path = os.path.join(SHOT_DIR, name)
    try:
        page.screenshot(path=path, full_page=False)
        ok = os.path.exists(path)
        print(f"[shot] {name} -> {'OK' if ok else 'MISSING'} {os.path.getsize(path) if ok else 0}B @ {path}")
    except Exception as e:
        print(f"[shot] {name} FAILED: {e}")

def rand_email():
    s = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"smoke_{s}@pea.test"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(8000)
        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("requestfailed", lambda r: failed_reqs.append(f"{r.method} {r.url} -> {r.failure}"))

        # Stage 1: load
        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1200)
        shot(page, "01_login.png")

        # Stage 2: switch to register tab
        reg_clicked = False
        for sel in ["text=注册", "button:has-text('注册')", "a:has-text('注册')"]:
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible():
                    el.click()
                    reg_clicked = True
                    page.wait_for_timeout(700)
                    break
            except Exception:
                pass
        print("[stage2] register tab clicked:", reg_clicked)
        shot(page, "02_register_form.png")

        # Stage 3: fill VISIBLE inputs by placeholder/type
        email = rand_email()
        pw = "Smoke123!"
        uname = "smoke" + ''.join(random.choices(string.digits, k=4))
        visible_inputs = page.locator("input:visible")
        n = visible_inputs.count()
        phs = [visible_inputs.nth(i).get_attribute("placeholder") or "" for i in range(n)]
        types = [visible_inputs.nth(i).get_attribute("type") or "" for i in range(n)]
        print(f"[stage3] visible inputs n={n} types={types} placeholders={phs}")

        def fill_by(predicate, value, label):
            for i in range(n):
                if predicate(i):
                    visible_inputs.nth(i).fill(value)
                    print(f"[fill] {label} -> input#{i} ({types[i]}, ph='{phs[i]}')")
                    return True
            print(f"[fill] {label} -> NOT FOUND")
            return False

        fill_by(lambda i: "@" in phs[i] and "password" not in phs[i].lower(), email, "email")
        fill_by(lambda i: types[i] == "password", pw, "password")
        fill_by(lambda i: types[i] == "text" and "@" not in phs[i], uname, "displayName/nickname")
        shot(page, "03_filled.png")
        print("[stage3] credentials:", uname, email, pw)

        # Stage 4: submit — match button whose normalized text contains 注册/登录
        submit_clicked = False
        for btn in page.locator("button:visible").all():
            try:
                txt = (btn.inner_text() or "").replace(" ", "")
                if "注册" in txt or "登录" in txt:
                    btn.click()
                    submit_clicked = True
                    print(f"[stage4] clicked submit button text='{txt}'")
                    break
            except Exception:
                pass
        print("[stage4] submit clicked:", submit_clicked)
        page.wait_for_timeout(3500)

        # Stage 5: inspect result
        shot(page, "04_after_submit.png")
        after_text = (page.inner_text("body") or "")[:1800]
        after_url = page.url
        marker = any(k in after_text for k in ["余额", "积分", "Tapies", "1000", "控制台", "仪表", "工作台", "画布", "canvas", "退出", "个人中心", "欢迎"])
        print("[stage5] url:", after_url)
        print("[stage5] auth/dashboard marker:", marker)
        print("[stage5] body sample:\n", after_text)

        # bonus: try to read localStorage token to prove auth handshake
        token = page.evaluate("() => localStorage.getItem('token') || localStorage.getItem('access_token') || sessionStorage.getItem('token') || ''")
        print("[stage5] token in storage:", bool(token), "len:", len(token) if token else 0)

        browser.close()

    result = {
        "console_errors": console_errors,
        "page_errors": page_errors,
        "failed_requests": failed_reqs,
        "registered_email": email,
        "register_tab_clicked": reg_clicked,
        "submit_clicked": submit_clicked,
        "auth_or_dashboard_marker": marker,
        "token_in_storage": bool(token),
        "final_url": after_url,
    }
    print("\n=== RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
