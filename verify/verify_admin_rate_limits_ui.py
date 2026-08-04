"""
验证：管理员控制台「速率限制」Tab 的真实渲染与交互。

为什么用 mock 后端：本机 BFF(4100) 跑的是旧编译产物，/admin/rate-limits 路由尚未生效
(实测返回 404)，且 provider_rate_limits 表未建。本脚本用 Playwright route mock 把这三个
接口喂成确定数据，专注验证【前端 UI 层】是否正确渲染、联动、提交 —— 后端逻辑另有
verify_rate_limit.py 用真实代码覆盖。

跑之前需要 Vite dev server 在 5173 运行 (npm run dev)，因为它带 HMR，改完即生效；
8088 是生产 bundle，未重新 build 时看不到新代码。

用法: python verify/verify_admin_rate_limits_ui.py
"""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://localhost:5173"
SHOT = Path(__file__).parent / "shot_admin_rate_limits.png"
SHOT_MODAL = Path(__file__).parent / "shot_admin_rate_limits_modal.png"

ME = {
    "id": 1,
    "email": "admin@pea.ai",
    "displayName": "Admin",
    "isAdmin": True,
    "balance": 9999,
    "planLevel": 3,
    "effectivePlanLevel": 3,
    "planExpiresAt": None,
}

PROVIDERS = [
    {
        "id": "prov_agnes", "name": "Agnes", "providerType": "openai-compatible",
        "protocol": "openai-compatible", "vendor": "agnes",
        "baseUrl": "https://apihub.agnes-ai.com/v1", "apiKeyMasked": "sk-***",
        "hasApiKey": True, "kind": "image", "enabled": True, "isDefault": True, "config": {},
    },
    {
        "id": "prov_minimax", "name": "MiniMax", "providerType": "openai-compatible",
        "protocol": "openai-compatible", "vendor": "minimax",
        "baseUrl": "https://api.minimax.chat", "apiKeyMasked": "sk-***",
        "hasApiKey": True, "kind": "video", "enabled": True, "isDefault": False, "config": {},
    },
]

MODELS = [
    {
        "id": "agnes-image-v2", "providerId": "prov_agnes", "modelName": "agnes-image-v2",
        "displayName": "Agnes 图像 v2", "modelType": "image", "enabled": True,
        "isDefault": True, "minPlanLevel": 0, "pricing": None, "paramsSchema": None,
        "description": "", "sortOrder": 0,
    },
    {
        "id": "minimax-video", "providerId": "prov_minimax", "modelName": "minimax-video",
        "displayName": "MiniMax 视频", "modelType": "video", "enabled": True,
        "isDefault": False, "minPlanLevel": 1, "pricing": None, "paramsSchema": None,
        "description": "", "sortOrder": 1,
    },
]

RULES = [
    # 厂商级 + 4K 档：正是本次 429 事故要配的那条
    {"id": 1, "provider_id": "prov_agnes", "model_id": None, "tier": "4K",
     "limit_n": 1, "window_s": 60, "enabled": True},
    # 模型级：验证维度隔离在 UI 上能区分展示
    {"id": 2, "provider_id": "prov_agnes", "model_id": "agnes-image-v2", "tier": None,
     "limit_n": 10, "window_s": 3600, "enabled": False},
]

results: list[tuple[bool, str]] = []
posted_body: dict | None = None


def check(ok: bool, label: str) -> None:
    results.append((bool(ok), label))
    print(f"{'PASS' if ok else 'FAIL'} {label}")


async def main() -> int:
    global posted_body
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 950})

        async def json_route(route, payload, status=200):
            await route.fulfill(
                status=status,
                content_type="application/json",
                body=json.dumps(payload),
            )

        async def handle_rate_limits(route):
            global posted_body
            req = route.request
            if req.method == "POST":
                posted_body = json.loads(req.post_data or "{}")
                await json_route(route, {**posted_body, "id": 99})
            else:
                await json_route(route, RULES)

        # 统一 API 拦截：按 URL 分发到对应 mock 数据，避免 Vite 模块加载被误拦截
        async def handle_api(route):
            url = route.request.url
            if route.request.resource_type not in ("fetch", "xhr"):
                await route.continue_()
                return
            if "/users/me" in url:
                await json_route(route, ME)
            elif "rate-limits" in url:
                await asyncio.create_task(handle_rate_limits(route))
            elif "admin/providers" in url:
                await json_route(route, PROVIDERS)
            elif "admin/models" in url:
                await json_route(route, MODELS)
            elif "auth/refresh" in url:
                await json_route(route, {"token": "new-fake"})
            elif "billing" in url:
                await json_route(route, {"balance": 9999})
            else:
                await json_route(route, [])

        ctx = page.context
        await ctx.route("**/api/**", lambda r: asyncio.create_task(handle_api(r)))

        # 首次加载：先到首页拿到 origin，写入 token 和路由
        await page.goto(BASE, timeout=25000)
        await page.evaluate(
            """() => {
                localStorage.setItem('pea_token', 'fake-admin-token');
                localStorage.setItem('pea_ui_route',
                    JSON.stringify({ active: 'admin', canvasId: null }));
            }"""
        )
        # 重载：此时 token 已就位、路由已指向 admin、API 已被 mock 拦截
        await page.goto(BASE, timeout=25000)
        await page.wait_for_timeout(4000)

        # 1) 控制台可见 + 新 Tab 存在
        tab = page.get_by_role("tab", name="速率限制")
        check(await tab.count() > 0, "管理员控制台出现「速率限制」Tab")
        if await tab.count() == 0:
            await page.screenshot(path=str(SHOT))
            print(f"\n页面无该 Tab，截图见 {SHOT}")
            await browser.close()
            return 1

        await tab.click()
        await page.wait_for_timeout(1200)

        # 2) 规则列表正确渲染（含维度与配额的人话表述）
        body = await page.locator("body").inner_text()
        check("Agnes" in body, "表格展示提供商名称（而非裸 id）")
        check("4K" in body, "展示分辨率档位 4K")
        check("全部模型" in body, "model_id 为空时显示「全部模型」而非空白")
        check("全部档位" in body, "tier 为空时显示「全部档位」而非空白")
        check("每 1 分钟" in body, "window_s=60 渲染为「每 1 分钟」")
        check("每 1 小时" in body, "window_s=3600 渲染为「每 1 小时」")
        check("30 秒内自动生效" in body, "顶部说明提示了热生效，避免用户误重启")

        rows = await page.locator(".ant-table-tbody tr.ant-table-row-level-0").count()
        if rows == 0:
            rows = await page.locator(".ant-table-tbody tr").count()
        check(rows >= 2, f"表格渲染 ≥2 条规则 (实际 {rows})")

        await page.screenshot(path=str(SHOT), full_page=True)

        # 3) 新建弹窗：提供商必选 + 模型随提供商联动
        await page.get_by_role("button", name="新建规则").click()
        await page.wait_for_timeout(700)
        modal = page.locator(".ant-modal-content")
        check(await modal.count() > 0, "点击「新建规则」弹出表单")

        mbody = await modal.inner_text()
        check("提供商" in mbody and "分辨率档位" in mbody, "表单含提供商 / 档位字段")
        check("留空 = 全部模型" in mbody or "全部模型" in mbody, "模型字段说明了留空语义")

        # 选 Agnes -> 模型下拉应只出现 Agnes 的模型（跨厂商错配防呆）
        await modal.locator(".ant-select-selector").first.click()
        await page.wait_for_timeout(500)
        opts = await page.locator(".ant-select-dropdown:visible .ant-select-item-option").all_inner_texts()
        check(any("Agnes" in o for o in opts), f"提供商下拉可选 Agnes (选项: {opts})")
        for o in opts:
            if "Agnes" in o:
                await page.get_by_text(o, exact=True).first.click()
                break
        await page.wait_for_timeout(500)

        await modal.locator(".ant-select-selector").nth(1).click()
        await page.wait_for_timeout(500)
        mopts = await page.locator(".ant-select-dropdown:visible .ant-select-item-option").all_inner_texts()
        joined = " ".join(mopts)
        check("Agnes 图像 v2" in joined, f"模型下拉联动出 Agnes 的模型 ({mopts})")
        check("MiniMax" not in joined, "模型下拉已过滤掉其他厂商的模型（防跨厂商错配）")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        await page.screenshot(path=str(SHOT_MODAL))

        # 4) 提交载荷字段名与 BFF DTO 对齐 (snake_case)
        await modal.locator(".ant-select-selector").nth(2).click()  # 档位
        await page.wait_for_timeout(400)
        await page.locator(".ant-select-dropdown:visible .ant-select-item-option")\
            .filter(has_text="4K").first.click()
        await page.wait_for_timeout(300)
        await page.get_by_role("button", name="保 存").click()
        await page.wait_for_timeout(1200)

        check(posted_body is not None, "表单提交发出了 POST 请求")
        if posted_body:
            keys = set(posted_body)
            check({"provider_id", "limit_n", "window_s"} <= keys,
                  f"提交字段为 snake_case，与 BFF DTO 对齐 ({sorted(keys)})")
            check(posted_body.get("tier") == "4K", f"档位提交值正确 ({posted_body.get('tier')})")
            check(posted_body.get("provider_id") == "prov_agnes",
                  f"提供商提交的是 id 而非名称 ({posted_body.get('provider_id')})")

        await browser.close()

    failed = [l for ok, l in results if not ok]
    print("\n" + "=" * 62)
    print(f"RESULT: {len(results) - len(failed)}/{len(results)} PASS")
    print(f"截图: {SHOT}\n      {SHOT_MODAL}")
    if failed:
        for l in failed:
            print(f"  FAILED: {l}")
        return 1
    return 0


sys.exit(asyncio.run(main()))
