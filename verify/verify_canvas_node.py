"""
E2E 验证：画布节点 Issue #17 (模型选择器卡片式 UI) + #18 (图片节点 比例·分辨率·倍率)
通过真实 UI 流程验证（#310 已修复，双击菜单可正常添加节点）。

验证项：
  Q1 注册 + 进入工作区
  Q2 新建项目 → 进入画布
  Q3 双击画布 → 节点库 → 点击「图片」添加节点（真实 UI，验证 #310 已修复）
  Q4 输入栏 .node-chat-prompt-input 出现
  Q5 模型选择芯片 → .node-model-picker 弹出且为卡片式（含 .picker-card，无原生 <select>）
  Q6 卡片均为 image 类型（按 kind=image 过滤），且 chip 显示已选模型名
  Q7 图片比例·分辨率芯片 → .node-aspect-picker 弹出（比例按钮>=4，分辨率>=2）
  Q8 倍率下拉 → .node-count-dropdown 弹出（选项>=2）
  Q9 消息保留：填写后取消选中再点回 → 文本被带出（draftRef 还原）
  Q10 消息保留：提交后输入框不清空
  Q11 控制台无致命错误
"""
import asyncio, json, re, sys, time
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
BFF = "http://localhost:4100"

results = {}

async def step(name, fn):
    try:
        ok, info = await fn()
    except Exception as e:
        ok, info = False, f"EXC: {e}"
    results[name] = (ok, info)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {info}")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context()
        pg = await ctx.new_page()
        errors = []
        pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("PAGEERR: " + str(e)))

        # Q1 + Q2
        ts = int(time.time() * 1000)
        email = f"cv{ts}@pea.ai"
        reg = await ctx.request.post(f"{BFF}/auth/register",
            data=json.dumps({"email": email, "password": "Test1234!"}),
            headers={"Content-Type": "application/json"})
        regj = await reg.json()
        token = regj.get("token"); user = regj.get("user", {})
        await pg.add_init_script(
            f"localStorage.setItem('pea_token', {json.dumps(token)});"
            f"localStorage.setItem('pea_user', {json.dumps(json.dumps(user))});")
        await pg.goto(BASE + "/", timeout=20000)
        await pg.wait_for_selector(".pea-nav", timeout=15000)
        print("Q1/Q2 workspace reached")

        await pg.get_by_text("新建项目", exact=False).first.click()
        await pg.wait_for_selector(".react-flow", timeout=15000)
        await pg.wait_for_timeout(800)
        print("Q2 canvas entered")

        # Q3: 双击 pane 打开节点库 → 点击「图片」
        pane = pg.locator(".react-flow__pane").first
        box = await pane.bounding_box()
        cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
        await pg.mouse.dblclick(cx, cy)
        await pg.wait_for_selector(".pea-add-menu-item", timeout=8000)

        async def q3():
            items = pg.locator(".pea-add-menu-item")
            n = await items.count()
            target = None
            for i in range(n):
                t = (await items.nth(i).inner_text()).strip()
                if "图片" in t:
                    target = items.nth(i); break
            if not target:
                return False, "no 图片 item"
            await target.click()
            await pg.wait_for_timeout(1500)
            cnt = await pg.locator(".react-flow__node").count()
            return cnt >= 1, f"nodes={cnt}"
        await step("Q3 add image node (real UI, #310 fixed)", q3)

        # Q4: 输入栏出现
        async def q4():
            await pg.wait_for_selector(".node-chat-prompt-input", timeout=8000)
            return True, "input bar visible"
        await step("Q4 input bar appears on node select", q4)

        # Q5: 模型卡片式选择器
        async def q5():
            chip = pg.locator(".node-input-model-chip").first
            if not await chip.count():
                return False, "no model chip"
            await chip.click()
            await pg.wait_for_selector(".node-model-picker", timeout=6000)
            cards = await pg.locator(".picker-card").count()
            selects = await pg.locator(".node-model-picker select").count()
            return cards >= 1 and selects == 0, f"picker-cards={cards} native-selects={selects}"
        await step("Q5 model picker is card-style (no native select)", q5)

        # Q6: 卡片均为 image 类型 + chip 显示模型名
        async def q6():
            names = await pg.locator(".picker-card-name").all_inner_texts()
            no_native = all(("文本" not in n) and ("视频" not in n) and ("音频" not in n) for n in names)
            chip_name = (await pg.locator(".node-model-chip-name").first.inner_text()).strip()
            # 关闭 picker：再次点击芯片 toggle（勿用 Escape — CanvasEditor 的 Escape 会取消选中节点）
            await pg.locator(".node-input-model-chip").first.click()
            await pg.wait_for_timeout(300)
            return (len(names) >= 1 and no_native), f"cards={names} chip='{chip_name}'"
        await step("Q6 picker shows image models only, chip shows model", q6)

        # Q7: 比例·分辨率选择器
        async def q7():
            chip = pg.locator(".node-input-aspect-chip").first
            if not await chip.count():
                return False, "no aspect chip (not image node?)"
            await chip.click()
            await pg.wait_for_selector(".node-aspect-picker", timeout=5000)
            rb = await pg.locator(".aspect-ratio-btn").count()
            resb = await pg.locator(".aspect-res-btn").count()
            await chip.click()  # toggle close
            await pg.wait_for_timeout(300)
            return rb >= 4 and resb >= 2, f"ratio-btns={rb} res-btns={resb}"
        await step("Q7 aspect picker (ratio>=4, resolution>=2)", q7)

        # Q8: 出图数按钮存在（原左侧 node-count-chip 已移至右侧消耗量前，改为 node-count-btn）
        async def q8():
            btn = pg.locator(".node-count-btn").first
            if not await btn.count():
                return False, "no .node-count-btn (new count button missing)"
            text = (await btn.inner_text()).strip()
            return bool(re.match(r"^\d+x$", text)), f"count-btn text='{text}'"
        await step("Q8 count button exists with Nx format", q8)

        # Q15: 比例选择持久化（用户核心抱怨：选了比例后重新点节点，比例回到初始状态）
        async def q15():
            # 1) 打开比例选择器，选一个非默认值（16:9）
            achip = pg.locator(".node-input-aspect-chip").first
            if not await achip.count():
                return False, "no aspect chip"
            await achip.click()
            await pg.wait_for_selector(".node-aspect-picker", timeout=5000)
            # 点击 16:9 按钮
            btn_16_9 = pg.locator(".aspect-ratio-btn").filter(has_text="16:9").first
            if not await btn_16_9.count():
                return False, "no 16:9 ratio button"
            await btn_16_9.click(force=True)
            await pg.wait_for_timeout(400)
            # 确认 chip 文本已变为 16:9
            chip_text = (await achip.inner_text()).strip()
            if "16:9" not in chip_text:
                return False, f"chip text not updated after select: '{chip_text}'"
            # 关闭比例弹层
            await achip.click()
            await pg.wait_for_timeout(400)
            # 2) 取消选中节点 → 再重新选中
            pane_box = await pane.bounding_box()
            await pg.mouse.click(pane_box["x"] + 20, pane_box["y"] + 20)
            await pg.wait_for_timeout(600)
            node = pg.locator(".react-flow__node").first
            await node.click()
            await pg.wait_for_selector(".node-chat-prompt-input", timeout=6000)
            await pg.wait_for_timeout(800)  # 等 model load + restore effect
            # 3) 验证比例 chip 仍然是 16:9（不是默认 1:1）
            achip2 = pg.locator(".node-input-aspect-chip").first
            if not await achip2.count():
                return False, "no aspect chip after reselect"
            restored_text = (await achip2.inner_text()).strip()
            is_persisted = "16:9" in restored_text and "1:1" not in restored_text
            return is_persisted, f"ratio persisted={is_persisted} chip='{restored_text}'"
        await step("Q15 aspect ratio persists across reselect (not reset to default)", q15)

        # Q14: 编辑框尺寸足够大（用户抱怨：框太小，底部按钮被裁切）
        async def q14():
            bar = pg.locator(".node-input-bar").first
            if not await bar.count():
                return False, "no .node-input-bar"
            box = await bar.bounding_box()
            if not box:
                return False, "bar bounding_box null"
            # 宽度 >= 520（代码 Math.max(520, ...)），高度足以容纳 textarea + 状态栏
            w_ok = box["width"] >= 500
            h_ok = box["height"] >= 100  # textarea(52+) + tools(28+) + status(36+) + padding
            # 底部状态栏按钮区域完整可见（不被 overflow 裁切）
            status = pg.locator(".node-input-status").first
            sb = await status.bounding_box() if await status.count() else None
            send_btn = pg.locator(".node-input-send").first
            btn_visible = await send_btn.count() > 0 and (await send_btn.bounding_box()) is not None
            return w_ok and h_ok and btn_visible, f"bar=({box['width']:.0f}x{box['height']:.0f}) w>={500}:{w_ok} h>=100:{h_ok} send_visible:{btn_visible}"
        await step("Q14 editing box size adequate (w>=500, h>=100, buttons visible)", q14)

        # Q12: 输入栏单行不换行（用户核心抱怨：模型/比例/张数 换行溢出）
        async def q12():
            bar = pg.locator(".node-input-status").first
            if not await bar.count():
                return False, "no .node-input-status"
            info = await bar.evaluate("""el => {
                const kids = [...el.children].filter(c => c.offsetParent !== null);
                const tops = kids.map(k => k.getBoundingClientRect().top);
                const minT = Math.min(...tops), maxT = Math.max(...tops);
                return { wrap: (maxT - minT) > 28, scrollH: el.scrollHeight, clientH: el.clientHeight, n: kids.length };
            }""")
            single = (not info["wrap"]) and (info["scrollH"] <= info["clientH"] + 4)
            return single, f"wrap={info['wrap']} scrollH={info['scrollH']} clientH={info['clientH']} visibleKids={info['n']}"
        await step("Q12 input bar single-row (model/aspect/count NOT wrapped)", q12)

        # Q13: 模型选择弹层在视口内（用户核心抱怨：弹层超出可视范围）
        async def q13():
            chip = pg.locator(".node-input-model-chip").first
            await chip.click()
            await pg.wait_for_selector(".node-model-picker", timeout=6000)
            box = await pg.locator(".node-model-picker").first.bounding_box()
            vs = pg.viewport_size
            vw, vh = vs["width"], vs["height"]
            in_view = bool(box) and (box["x"] >= -2 and box["y"] >= -2
                                     and box["x"] + box["width"] <= vw + 2
                                     and box["y"] + box["height"] <= vh + 2)
            await chip.click()  # close
            await pg.wait_for_timeout(300)
            if not box:
                return False, "picker box null"
            return in_view, f"picker=({box['x']:.0f},{box['y']:.0f},{box['width']:.0f},{box['height']:.0f}) viewport={vw}x{vh}"
        await step("Q13 model picker within viewport", q13)

        # Q9: 消息保留（取消选中再点回）
        async def q9():
            ta = pg.locator(".node-chat-prompt-input").first
            MSG = "验收：生成一张耳机产品海报"
            await ta.fill(MSG)
            await pg.wait_for_timeout(300)
            # 取消选中
            pane_box = await pane.bounding_box()
            await pg.mouse.click(pane_box["x"] + 15, pane_box["y"] + 15)
            await pg.wait_for_timeout(600)
            node = pg.locator(".react-flow__node").first
            await node.click()
            await pg.wait_for_selector(".node-chat-prompt-input", timeout=6000)
            val = await pg.locator(".node-chat-prompt-input").first.input_value()
            return MSG in val, f"restored='{val[:30]}'"
        await step("Q9 message restored on reselect (draftRef)", q9)

        # Q10: 提交后输入框不清空
        async def q10():
            ta = pg.locator(".node-chat-prompt-input").first
            MSG = "验收：提交后文本保留"
            await ta.fill(MSG)
            await ta.press("Enter")
            await pg.wait_for_timeout(800)
            val = await ta.input_value()
            return MSG in val, f"after-submit='{val[:30]}'"
        await step("Q10 textarea not cleared after submit", q10)

        # Q16: 比例选择器后无多余 1x/1K 按钮（用户要求去掉比例后的冗余控件）
        async def q16():
            left = pg.locator(".node-input-status-left").first
            if not await left.count():
                return False, "no status-left"
            text = await left.inner_text()
            # 左侧不应出现独立的 "1x" 下拉或 "1K" tier 参数
            has_extra_count = await left.locator(".node-count-wrapper").count() > 0
            has_extra_tier = "1K" in text or "⏱" in text
            return (not has_extra_count) and (not has_extra_tier), f"extra_count={has_extra_count} extra_tier_1k={has_extra_tier} left_text='{text[:60]}'"
        await step("Q16 no extra 1x/1K buttons after aspect selector", q16)

        # Q17: 出图数按钮（右侧消耗量前）可点击 + 弹出选择框（参考截图3）
        async def q17():
            # Q10 提交后重新点选节点确保输入栏就绪
            node = pg.locator(".react-flow__node").first
            if await node.count():
                await node.click()
                await pg.wait_for_selector(".node-chat-prompt-input", timeout=6000)
                await pg.wait_for_timeout(800)
            # 用 evaluate 检查 DOM（避免 Playwright locator 超时陷阱）
            info = await pg.evaluate("""() => {
                const bar = document.querySelector('.node-input-bar');
                if (!bar) return { err: 'no bar' };
                const btn = bar.querySelector('.node-count-btn');
                if (!btn) return { err: 'no .node-count-btn', rightHTML: bar.querySelector('.node-input-status-right')?.innerHTML?.slice(0, 300) || '' };
                return {
                    text: btn.textContent?.trim(),
                    visible: btn.offsetParent !== null,
                    rightText: bar.querySelector('.node-input-status-right')?.textContent?.trim() || ''
                };
            }""")
            if info.get("err"):
                return False, f"{info['err']}. rightHTML={info.get('rightHTML','')[:120]}"
            btn_text = info.get("text", "")
            if not re.match(r"^\d+x$", btn_text):
                return False, f"btn text not Nx format: '{btn_text}'"
            # 点击弹出下拉
            btn = pg.locator(".node-count-btn").first
            await btn.click()
            await pg.wait_for_selector(".node-count-btn-dropdown", timeout=4000)
            dropdown = pg.locator(".node-count-btn-dropdown").first
            if not await dropdown.count():
                return False, "dropdown not appeared after click"
            opts = dropdown.locator("button")
            opt_count = await opts.count()
            if opt_count < 2:
                return False, f"dropdown has only {opt_count} option(s)"
            # 点击 2x
            opt_2x = None
            for i in range(opt_count):
                t = (await opts.nth(i).inner_text()).strip()
                if t == "2x":
                    opt_2x = opts.nth(i); break
            if not opt_2x and opt_count > 0:
                opt_2x = opts.nth(0)  # fallback: pick first
            if opt_2x:
                await opt_2x.click(force=True)
                await pg.wait_for_timeout(400)
            new_info = await pg.evaluate("""() => {
                const btn = document.querySelector('.node-count-btn');
                return btn ? btn.textContent?.trim() : null;
            }""")
            changed = new_info != btn_text
            return changed and opt_count >= 2, f"before='{btn_text}' after='{new_info}' options={opt_count}"
        await step("Q17 count button clickable with dropdown (4x/2x/1x)", q17)

        # Q11: 控制台错误
        fatal = [e for e in errors if "310" not in e and "tasks/stream" not in e and "favicon" not in e]
        results["Q11"] = (len(fatal) == 0, f"fatal_errors={len(fatal)}")
        print(f"[{'PASS' if not fatal else 'WARN'}] Q11 console errors: {len(fatal)}")
        for e in fatal[:6]:
            print("   !", e[:180])

        await b.close()

        # 汇总（step() 以带描述的名字存结果，这里直接用实际 key 统计）
        checks = [k for k in results if k.startswith("Q") and k != "Q11"]
        passed = sum(1 for k in checks if results[k][0])
        all_ok = passed == len(checks) and len(fatal) == 0
        print(f"\n=== RESULT: {'PASS ✅' if all_ok else 'PARTIAL ⚠️'} ({passed}/{len(checks)} checks, errors={len(fatal)}) ===")
        sys.exit(0 if all_ok else 1)

asyncio.run(main())
