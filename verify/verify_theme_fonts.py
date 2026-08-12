"""验证：主题切换/字体可见性/表面令牌级联（无需后端，基于 vite preview 的公开 /login 页）。

用法：
  python verify_theme_fonts.py <preview_base_url>
例如：
  python verify_theme_fonts.py http://localhost:4173
"""
import os, sys, re
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def lum(rgb):
    r, g, b = [c / 255 for c in rgb]
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def parse_rgb(s):
    m = re.findall(r"(\d+\.?\d*)", s)
    return [int(round(float(x))) for x in m[:3]]

def contrast(c1, c2):
    l1, l2 = lum(c1), lum(c2)
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)

def get_var(page, name, el="document.body"):
    return page.evaluate(
        f"getComputedStyle({el}).getPropertyValue('{name}').trim()",
    )

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    page = ctx.new_page()
    page.goto(BASE + "/login", wait_until="networkidle")
    page.wait_for_timeout(800)

    # A) 主题切换改变令牌（precision 表面）
    bg_light = get_var(page, "--pea-bg-deep")
    page.evaluate("document.documentElement.classList.add('dark')")
    page.wait_for_timeout(200)
    bg_dark = get_var(page, "--pea-bg-deep")
    check(bg_light.lower() != bg_dark.lower(), f"主题切换改变 --pea-bg-deep: light={bg_light} dark={bg_dark}")
    page.evaluate("document.documentElement.classList.remove('dark')")
    page.wait_for_timeout(150)

    # B) 字体可见性：登录页主要文字与背景对比度
    # 取页面上若干文本节点，比较其 color 与最近可见背景色
    texts = page.evaluate(
        """() => {
            const out = [];
            const els = document.querySelectorAll('h1,h2,h3,p,button,label,input,span,a');
            for (const el of els) {
                const cs = getComputedStyle(el);
                const txt = (el.innerText || el.placeholder || '').trim();
                if (!txt || cs.visibility === 'hidden' || cs.display === 'none') continue;
                if (parseFloat(cs.fontSize) < 10) continue;
                // 背景：沿 offsetParent 链向上找第一个非透明背景
                let bg = cs.backgroundColor;
                let node = el;
                while (node && (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {
                    bg = getComputedStyle(node).backgroundColor;
                    node = node.parentElement;
                }
                out.push({ text: txt.slice(0, 24), color: cs.color, bg });
            }
            return out.slice(0, 40);
        }"""
    )
    low_contrast = []
    for t in texts:
        try:
            c_fg = parse_rgb(t["color"]); c_bg = parse_rgb(t["bg"])
        except Exception:
            continue
        ratio = contrast(c_fg, c_bg)
        if ratio < 2.0:
            low_contrast.append((t["text"], t["color"], t["bg"], round(ratio, 2)))
    check(len(low_contrast) == 0, f"登录页文字对比度(>=2.0)：发现 {len(low_contrast)} 处低对比度")
    for lc in low_contrast[:10]:
        print("   LOW:", lc)

    # B2) 暗色模式下 antd 组件文字可见（用登录页实际渲染的 antd 元素）
    page.evaluate("document.documentElement.classList.add('dark')")
    page.wait_for_timeout(300)
    dark_texts = page.evaluate(
        """() => {
            const out = [];
            const els = document.querySelectorAll('h1,h2,h3,p,button,label,span,a');
            for (const el of els) {
                const cs = getComputedStyle(el);
                const txt = (el.innerText || '').trim();
                if (!txt || parseFloat(cs.fontSize) < 10) continue;
                let bg = 'rgba(0, 0, 0, 0)'; let node = el;
                while (node && (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {
                    bg = getComputedStyle(node).backgroundColor; node = node.parentElement;
                }
                out.push({ text: txt.slice(0,24), color: cs.color, bg });
            }
            return out.slice(0, 40);
        }"""
    )
    dark_low = []
    for t in dark_texts:
        try:
            c_fg = parse_rgb(t["color"]); c_bg = parse_rgb(t["bg"])
        except Exception:
            continue
        if contrast(c_fg, c_bg) < 2.0:
            dark_low.append((t["text"], t["color"], t["bg"], round(contrast(c_fg, c_bg), 2)))
    check(len(dark_low) == 0, f"暗色模式文字对比度(>=2.0)：发现 {len(dark_low)} 处低对比度")
    for lc in dark_low[:10]:
        print("   DARK-LOW:", lc)
    page.evaluate("document.documentElement.classList.remove('dark')")

    # C) 表面令牌级联：cinematic=黑底, figma=白底
    page.evaluate("document.documentElement.className='dark'; document.body.dataset.surface='cinematic'")
    page.wait_for_timeout(200)
    cin_bg = get_var(page, "--pea-bg-deep")
    page.evaluate("document.documentElement.className='light'; document.body.dataset.surface='figma'")
    page.wait_for_timeout(200)
    fig_bg = get_var(page, "--pea-bg-deep")
    check(cin_bg.lower() in ("#000000", "rgb(0, 0, 0)"), f"cinematic 表面 --pea-bg-deep={cin_bg} (期望 #000000)")
    check(fig_bg.lower() in ("#ffffff", "rgb(255, 255, 255)"), f"figma 表面 --pea-bg-deep={fig_bg} (期望 #ffffff)")
    page.evaluate("document.documentElement.className=''; delete document.body.dataset.surface")
    page.wait_for_timeout(150)

    # 截图（人工核对）
    page.evaluate("document.documentElement.classList.remove('dark')")
    page.wait_for_timeout(150)
    page.screenshot(path=os.path.join(SHOTS, "vf_login_light.png"))
    page.evaluate("document.documentElement.classList.add('dark')")
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS, "vf_login_dark.png"))
    page.evaluate("document.documentElement.classList.remove('dark')")

    browser.close()

print("\n==== 结果 ====")
if fails:
    print(f"{len(fails)} 项失败:")
    for f in fails:
        print(" - " + f)
    sys.exit(1)
else:
    print("全部通过 ✅")
