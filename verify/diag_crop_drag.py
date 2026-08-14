"""
Crop drag white-bug diagnostic v2:
- Open canvas, add image node, enter crop mode
- DRAG the crop frame (move operation)
- Capture MULTIPLE frames DURING drag to catch the "white" moment
- Dump computed styles at each frame
- Save all frames as individual PNGs for analysis
"""
import asyncio
import json
import os
import time

from playwright.async_api import async_playwright

BASE = "http://localhost:5173"
OUT = os.path.join(os.path.dirname(__file__), "shots", "drag_frames")
os.makedirs(OUT, exist_ok=True)

TEST_IMG = os.path.join(os.path.dirname(__file__), "test_crop.jpg")
# If no test image, download one
if not os.path.exists(TEST_IMG):
    import urllib.request
    # Use a portrait image (taller than wide) to maximize letterbox effect
    urllib.request.urlretrieve(
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600&h=800&fit=crop",
        TEST_IMG,
    )


async def main():
    print("=== Crop Drag Frame Capture ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        page.set_default_timeout(30000)

        # Step 1: Register & login
        print("[1] Registering...")
        await page.goto(f"{BASE}/register", wait_until="networkidle")
        await page.fill('input[name="username"]', "dragdiag_user")
        await page.fill('input[name="password"]', "DragTest123!")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)
        # Check if already logged in or need to login
        if page.url.endswith("/canvas") or "/workspace" in page.url:
            print("  -> Already on canvas (auto-login)")
        else:
            print(f"  -> Current URL: {page.url}")
            # Try login
            await page.goto(f"{BASE}/login", wait_until="networkidle")
            await page.fill('input[name="username"]', "dragdiag_user")
            await page.fill('input[name="password"]', "DragTest123!")
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(3000)
            print(f"  -> After login URL: {page.url}")

        # Navigate to canvas
        if "/canvas" not in page.url and "/workspace" not in page.url:
            await page.goto(f"{BASE}/canvas", wait_until="networkidle")
            await page.wait_for_timeout(2000)

        # Step 2: Add an image node via API
        print("[2] Adding image node...")
        # Get token from localStorage
        token = await page.evaluate("localStorage.getItem('pea_token')")
        if not token:
            # Try to get from cookies or other storage
            cookies = await page.context.cookies()
            cookie_map = {c["name"]: c["value"] for c in cookies}
            token = cookie_map.get("pea_token", "")
        print(f"  Token: {token[:20]}..." if token else "  NO TOKEN FOUND!")

        # Use fetch API to add image node
        node_id = await page.evaluate("""async () => {
            try {
                // Read test image as base64
                const resp = await fetch('/test_crop.jpg');
                const blob = await resp.blob();
                // Upload via the app's upload mechanism
                const formData = new FormData();
                formData.append('file', blob, 'test.jpg');
                const uploadResp = await fetch('/api/upload/image', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + localStorage.getItem('pea_token') },
                    body: formData
                });
                if (!uploadResp.ok) {
                    return { error: 'upload failed: ' + uploadResp.status };
                }
                const { url } = await uploadResp.json();
                
                // Add image node to current canvas
                const canvasId = localStorage.getItem('pea_active_canvas_id') || localStorage.getItem('pea_canvas_id');
                const addResp = await fetch('/api/nodes', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + localStorage.getItem('pea_token')
                    },
                    body: JSON.stringify({
                        canvasId,
                        type: 'image',
                        data: { url }
                    })
                });
                if (!addResp.ok) {
                    return { error: 'add node failed: ' + addResp.status };
                }
                const node = await addResp.json();
                return { nodeId: node.id, url };
            } catch(e) {
                return { error: e.message };
            }
        }""")

        print(f"  Node result: {json.dumps(node_id)[:200]}")

        if "error" in node_id and node_id["error"]:
            print("  !! API approach failed, trying UI-only approach...")
            # Fallback: just use existing nodes or manual approach
            pass

        await page.wait_for_timeout(3000)
        
        # Take a snapshot of current state
        await page.screenshot(path=os.path.join(OUT, "00_before_crop.png"))
        print("  -> Saved: 00_before_crop.png")

        # Step 3: Find image node and click crop button
        print("[3] Looking for crop button...")
        
        # Try to find crop/trim button in toolbar
        crop_btn = await page.query_selector('.pea-node-result-toolbar [title*="裁剪"], .pea-node-result-toolbar [title*="crop"], .pea-btn-crop')
        
        if not crop_btn:
            # Try finding any image node first
            image_nodes = await page.query_selector_all('.pea-node.has-media')
            print(f"  Found {len(image_nodes)} image nodes")
            
            if image_nodes:
                # Click the first image node to select it
                await image_nodes[0].click()
                await page.wait_for_timeout(500)
                
                # Look for toolbar inside this node
                crop_btn = await image_nodes[0].query_selector('[title*="裁剪"], [title*="crop"], .pea-btn-crop')
                
                if not crop_btn:
                    # Try all buttons in toolbar
                    toolbar = await image_nodes[0].query_selector('.pea-node-result-toolbar')
                    if toolbar:
                        buttons = await toolbar.query_selector_all('button, [role="button"]')
                        print(f"  Toolbar has {len(buttons)} buttons:")
                        for i, btn in enumerate(buttons):
                            title = await btn.get_attribute('title') or ''
                            aria_label = await btn.get_attribute('aria-label') or ''
                            cls = await btn.get_attribute('class') or ''
                            print(f"    [{i}] title={title} aria={aria_label} class={cls[:40]}")

        if crop_btn:
            print("  -> Found crop button, clicking...")
            await crop_btn.click()
            await page.wait_for_timeout(1500)
        else:
            print("  !! No crop button found via selector, trying coordinate-based click...")
            # Try clicking where the toolbar usually appears
            # For now, let's check what's on screen
            await page.screenshot(path=os.path.join(OUT, "01_no_crop_btn.png"))

        # Check if crop overlay appeared
        overlay = await page.query_selector('.pea-crop-overlay')
        if not overlay:
            print("  !! Crop overlay NOT found. Dumping page state...")
            await page.screenshot(path=os.path.join(OUT, "99_no_overlay.png"))
            
            # Debug: check what's rendered
            html = await page.content()
            with open(os.path.join(OUT, "page_debug.html"), "w", encoding="utf-8") as f:
                f.write(html)
            print("  Saved page HTML for debugging")
            
            await browser.close()
            return

        print("  -> Crop overlay is visible!")
        await page.screenshot(path=os.path.join(OUT, "02_crop_opened.png"))

        # Step 4: Dump initial state of all crop layers
        print("\n[4] Initial crop layer dump:")
        init_state = await page.evaluate("""() => {
            const overlay = document.querySelector('.pea-crop-overlay');
            const stage = document.querySelector('.pea-crop-stage');
            const imgStage = document.querySelector('.pea-crop-image-stage');
            const imgClip = document.querySelector('.pea-crop-img-clip');
            const img = document.querySelector('.pea-crop-image');
            const frame = document.querySelector('.pea-crop-frame');
            
            const elInfo = (el, name) => {
                if (!el) return { name, exists: false };
                const cs = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return {
                    name,
                    bg: cs.backgroundColor,
                    visibility: cs.visibility,
                    display: cs.display,
                    rect: { x: r.x, y: r.y, w: r.width, h: r.height },
                    zIndex: cs.zIndex,
                    position: cs.position,
                    classes: el.className,
                };
            };
            
            return {
                overlay: elInfo(overlay, 'overlay'),
                stage: elInfo(stage, 'stage'),
                imgStage: elInfo(imgStage, 'imgStage'),
                imgClip: elInfo(imgClip, 'imgClip'),
                img: elInfo(img, 'img'),
                frame: elInfo(frame, 'frame'),
                imgNaturalWidth: img?.naturalWidth,
                imgNaturalHeight: img?.naturalHeight,
                imgComplete: img?.complete,
                imgSrc: img?.src?.substring(0, 80),
            };
        }""")
        print(json.dumps(init_state, indent=2))

        # Step 5: Perform DRAG and capture frames
        print("\n[5] Starting drag capture...")
        frame_el = await page.query_selector('.pea-crop-frame')
        if not frame_el:
            print("  !! No frame element found!")
            await browser.close()
            return

        frame_box = await frame_el.bounding_box()
        if not frame_box:
            print("  !! Cannot get frame bounding box!")
            await browser.close()
            return

        print(f"  Frame box: x={frame_box['x']:.1f}, y={frame_box['y']:.1f}, w={frame_box['width']:.1f}, h={frame_box['height']:.1f}")

        # Start drag from center of frame
        start_x = frame_box['x'] + frame_box['width'] / 2
        start_y = frame_box['y'] + frame_box['height'] / 2
        
        # Drag down-right (move the frame to see the white area appear)
        drag_dx = 80
        drag_dy = 50
        
        # Capture frame BEFORE drag
        await page.screenshot(path=os.path.join(OUT, "03_pre_drag.png"))
        print("  -> Saved: 03_pre_drag.png")

        # Start the drag
        print(f"  Starting mouse drag from ({start_x:.0f}, {start_y:.0f}) to ({start_x+drag_dx:.0f}, {start_y+drag_dy:.0f})...")
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()

        # Capture DURING drag (multiple frames)
        num_frames = 8
        for i in range(num_frames):
            progress = (i + 1) / num_frames
            move_x = start_x + drag_dx * progress
            move_y = start_y + drag_dy * progress
            
            await page.mouse.move(move_x, move_y)
            await page.wait_for_timeout(80)  # Small delay between moves
            
            # Screenshot during drag
            frame_path = os.path.join(OUT, f"04_drag_frame_{i+1:02d}.png")
            await page.screenshot(path=frame_path)
            
            # Also dump key styles during drag
            drag_info = await page.evaluate("""() => {
                const frame = document.querySelector('.pea-crop-frame');
                const imgStage = document.querySelector('.pea-crop-image-stage');
                const img = document.querySelector('.pea-crop-image');
                const overlay = document.querySelector('.pea-crop-overlay');
                
                return {
                    frameClasses: frame?.className,
                    frameBg: getComputedStyle(frame).backgroundColor,
                    frameBoxShadow: getComputedStyle(frame).boxShadow,
                    frameTransform: frame?.style.transform,
                    frameInlineStyle: frame?.getAttribute('style'),
                    imgStageRect: imgStage?.getBoundingClientRect(),
                    imgRect: img?.getBoundingClientRect(),
                    overlayBg: getComputedStyle(overlay).backgroundColor,
                    isDragging: !!document.querySelector('.pea-crop-frame--dragging'),
                    // Check for ANY white/large background in the crop area
                    imgClipBg: getComputedStyle(document.querySelector('.pea-crop-img-clip')).backgroundColor,
                };
            }""")
            print(f"  Frame {i+1}/{num_frames}: dragging={drag_info['isDragging']} "
                  f"frameShadow={drag_info['frameBoxShadow'][:40]} "
                  f"overlayBg={drag_info['overlayBg']} "
                  f"imgClipBg={drag_info['imgClipBg']}")
            print(f"    -> Saved: {frame_path}")

        # Release mouse
        await page.mouse.up()
        await page.wait_for_timeout(500)

        # Capture AFTER drag (should be normal per user report)
        await page.screenshot(path=os.path.join(OUT, "05_post_drag.png"))
        print("  -> Saved: 05_post_drag.png")

        # Final state dump
        post_state = await page.evaluate("""() => {
            const frame = document.querySelector('.pea-crop-frame');
            return {
                frameClasses: frame?.className,
                frameBoxShadow: getComputedStyle(frame).boxShadow,
                isDragging: !!document.querySelector('.pea-crop-frame--dragging'),
            };
        }""")
        print(f"\n[6] Post-drag state: {json.dumps(post_state)}")

        await browser.close()
        print(f"\n=== Done! All frames saved to {OUT} ===")


if __name__ == "__main__":
    asyncio.run(main())
