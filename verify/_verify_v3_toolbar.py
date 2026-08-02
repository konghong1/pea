"""Verify toolbar light theme - final version with node creation."""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
OUT = r"C:\workspace\pea\verify"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        # Login
        await page.goto(BASE + "/login", timeout=15000)
        await page.wait_for_timeout(2000)
        inputs = await page.locator("input").all()
        await inputs[0].fill("v3test@test.com")
        await inputs[1].fill("Test123456")
        await inputs[1].press("Enter")
        await page.wait_for_timeout(5000)

        # Go to home and click into a canvas
        await page.goto(BASE + "/", timeout=15000)
        await page.wait_for_timeout(3000)

        # Click on canvas card
        card = page.locator("text=v3-tb-final").first
        if await card.count() > 0:
            await card.click()
            await page.wait_for_timeout(5000)

        print(f"URL: {page.url}")
        await page.screenshot(path=f"{OUT}/shot_v3_editor_view.png", full_page=False)

        # Click the + button in left toolbar
        add_btn = page.locator(".pea-tlb-btn").first
        if await add_btn.count() > 0:
            await add_btn.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f"{OUT}/shot_v3_add_menu_open.png", full_page=False)

            # Click first menu item (image node)
            item = page.locator(".pea-add-menu-item").first
            if await item.count() > 0:
                await item.click()
                await page.wait_for_timeout(2000)
                await page.screenshot(path=f"{OUT}/shot_v3_with_node.png", full_page=False)

                # Click node to select (show toolbar)
                node = page.locator(".pea-node").first
                if await node.count() > 0:
                    await node.click()
                    await page.wait_for_timeout(1000)
                    await page.screenshot(path=f"{OUT}/shot_v3_light_toolbar.png", full_page=False)

                    # Comprehensive style probe
                    probe = await page.evaluate("""(function(){
                        var r={};
                        var el;
                        // 1. Result toolbar (above image)
                        el=document.querySelector('.pea-node-result-toolbar');
                        if(el){var s=getComputedStyle(el); r.resultToolbar={bg:s.background.substring(0,80),border:s.borderColor};}
                        // 2. Toolbar buttons
                        var btns=document.querySelectorAll('.pea-node-toolbar-btn');
                        r.toolbarBtnCount=btns.length;
                        if(btns.length>0){var s=getComputedStyle(btns[0]); r.toolbarBtn={bg:s.background,color:s.color};}
                        // 3. Node body card
                        el=document.querySelector('.pea-node-body-card');
                        if(el){var s=getComputedStyle(el); r.bodyCard={bg:s.background.substring(0,60)};}
                        // 4. Badge (kind tag)
                        el=document.querySelector('.pea-node-badge');
                        if(el){var s=getComputedStyle(el); r.badge={bg:s.background.substring(0,60),color:s.color};}
                        // 5. Star
                        el=document.querySelector('.pea-node-result-star');
                        if(el){var s=getComputedStyle(el); r.star={bg:s.color};}
                        // 6. Left toolbar
                        el=document.querySelector('.pea-toolbar');
                        if(el){var s=getComputedStyle(el); r.leftToolbar={bg:s.background.substring(0,60),border:s.borderColor};}
                        // 7. Canvas controls pill
                        el=document.querySelector('.pea-canvas-controls-pill');
                        if(el){var s=getComputedStyle(el); r.canvasPill={bg:s.background.substring(0,60)};}
                        return r;
                    })()""")
                    print(f"\n=== Light Theme Style Probe ===")
                    print(json.dumps(probe, indent=2))

        # Also screenshot just the left toolbar area for clarity
        await page.screenshot(path=f"{OUT}/shot_v3_left_toolbar.png", full_page=False,
                               clip={"x": 0, "y": 80, "width": 80, "height": 400})

        await browser.close()
        print("\nDone!")

asyncio.run(main())
