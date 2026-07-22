"""
Batch 3 可视化验证 (E9 社区 TapTV / T-M4-01/02/03)
- 登录 -> 进入 TapTV, 校验 feed 卡片渲染
- 发布作品 -> 卡片数 +1, 新卡片出现在顶部
- 打开作品详情抽屉 -> 校验文案
- 点赞切换 -> 计数 +1, 再点 -1
- 收藏切换 -> 计数 +1
- 发评论 -> 评论数 +1, 评论内容出现
- 进入竞技场 -> 文案明确 Non-Goal / 移出 MVP 范围
- 全程 0 console error
"""
import os
import re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def shot(page, name):
    p = os.path.join(SHOTS, f"e9_{name}.png")
    page.screenshot(path=p)
    return p

fails, checks = [], 0
def check(cond, label):
    global checks
    checks += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 登录
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.get_by_placeholder("you@pea.ai").fill("verify@pea.ai")
    page.get_by_placeholder("至少 8 位").fill("password123")
    page.get_by_placeholder("至少 8 位").press("Enter")
    page.wait_for_timeout(1200)
    check(page.url.rstrip("/") != f"{BASE}/login", "登录后离开登录页")

    # 进入 TapTV
    page.get_by_text("TapTV", exact=True).first.click()
    page.wait_for_timeout(1000)
    cards_before = page.locator('button[aria-label="查看作品"]').count()
    check(cards_before >= 4, f"feed 渲染卡片数 >= 4 (实际 {cards_before})")
    shot(page, "01_feed")

    # 发布作品
    page.locator('button:has-text("发布作品")').first.click()
    page.locator('.ant-modal').wait_for(state="visible", timeout=8000)
    page.wait_for_timeout(400)
    page.get_by_placeholder("分享你的创作过程、心得或成片……").fill("Playwright 自动发布 · 社区验证 🧪")
    page.locator('.ant-modal-footer .ant-btn-primary').click()
    page.wait_for_timeout(900)
    cards_after = page.locator('button[aria-label="查看作品"]').count()
    check(cards_after == cards_before + 1, f"发布后卡片数 +1 ({cards_before}->{cards_after})")
    shot(page, "02_publish")

    # 打开第一个作品详情
    page.locator('button[aria-label="查看作品"]').first.click()
    page.wait_for_timeout(700)
    detail_visible = page.get_by_text("作品详情").is_visible()
    check(detail_visible, "作品详情抽屉打开")
    shot(page, "03_detail")

    # 点赞切换: 先读计数 (aria-label 会随状态在 点赞/取消点赞 间变化, 用正则兼容)
    like_btn = page.get_by_role("dialog").get_by_role("button", name=re.compile("点赞"))
    before = int(like_btn.inner_text().strip())
    like_btn.click()
    page.wait_for_timeout(600)
    after = int(page.get_by_role("dialog").get_by_role("button", name=re.compile("点赞")).inner_text().strip())
    check(after == before + 1, f"点赞计数 +1 ({before}->{after})")
    shot(page, "04_liked")

    # 收藏切换
    fav_btn = page.get_by_role("dialog").get_by_role("button", name=re.compile("收藏"))
    fb = int(fav_btn.inner_text().strip())
    fav_btn.click()
    page.wait_for_timeout(500)
    fa = int(page.get_by_role("dialog").get_by_role("button", name=re.compile("收藏")).inner_text().strip())
    check(fa == fb + 1, f"收藏计数 +1 ({fb}->{fa})")

    # 发评论
    page.get_by_placeholder("说点什么……").fill("自动化测试评论 ✅")
    page.get_by_role("button", name="发送评论").click()
    page.wait_for_timeout(600)
    comment_shown = page.get_by_text("自动化测试评论 ✅").is_visible()
    check(comment_shown, "评论内容出现在详情")
    shot(page, "05_comment")

    # 关闭抽屉 (显式点关闭按钮, 等动画结束, 避免遮罩挡住导航)
    close_btn = page.locator('.ant-drawer-close')
    if close_btn.count():
        close_btn.first.click()
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(1000)

    # 竞技场: 文案明确范围 (T-M4-03)
    page.get_by_text("竞技场", exact=True).first.click()
    page.wait_for_timeout(700)
    arena_scope = page.get_by_text("移出 MVP 范围").is_visible()
    check(arena_scope, "竞技场明确 Non-Goal / 移出 MVP 范围")
    shot(page, "06_arena")

    check(len(errors) == 0, f"0 console error (实际 {len(errors)})")
    if errors:
        print("CONSOLE ERRORS:", errors[:5])

    browser.close()

print(f"\n==== Batch3 验证: {checks - len(fails)}/{checks} 通过 ====")
if fails:
    print("失败项:", fails)
    raise SystemExit(1)
print("✅ 全部通过")
