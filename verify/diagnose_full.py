"""全面诊断：截图显示节点被截断（只露标签），需排查：
1. 节点 DOM 完整性：body-card 是否存在、尺寸、是否被 clip
2. 父容器 overflow：react-flow__viewport / __renderer / __nodes 的 overflow 和高度
3. NodeChatPrompt 输入栏位置和 z-index 是否遮挡节点
4. handle z-index 改动是否有副作用
5. 连线状态：react-flow__connecting 类是否存在及其影响
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time, json

SHOTS = Path("C:/workspace/pea/verify/shots")

def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        # 注册登录
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"diag_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "DIAG")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        # 添加两个节点
        def add_at(label, x, y):
            page.mouse.dblclick(x, y); page.wait_for_timeout(350)
            page.locator(".pea-add-menu-item", has_text=label).first.click(); page.wait_for_timeout(600)
        add_at("文本", 300, 260)
        add_at("图片", 1080, 260)
        page.wait_for_timeout(800)

        # 截图当前状态
        page.screenshot(path=str(SOTS := SHOTS / "diag_00_initial.png"))
        print(f"[shot] {SOTS}")

        # ====== 诊断1: 节点 DOM 结构与可见性 ======
        diag1 = page.evaluate("""() => {
    const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
    return nodes.map((n, i) => {
        const pea = n.querySelector('.pea-node');
        const body = n.querySelector('.pea-node-body-card');
        const tag = n.querySelector('.pea-node-tag-pill');
        const handleSrc = n.querySelector('.react-flow__handle.source');
        const handleTgt = n.querySelector('.react-flow__handle.target');
        const nRect = n.getBoundingClientRect();
        const bodyRect = body ? body.getBoundingClientRect() : null;
        const tagRect = tag ? tag.getBoundingClientRect() : null;
        return {
            idx: i,
            id: n.getAttribute('data-id'),
            kind: pea?.getAttribute('data-kind'),
            nodeRect: { x: Math.round(nRect.x), y: Math.round(nRect.y), w: Math.round(nRect.width), h: Math.round(nRect.height) },
            bodyExists: !!body,
            bodyRect: bodyRect ? { x: Math.round(bodyRect.x), y: Math.round(bodyRect.y), w: Math.round(bodyRect.width), h: Math.round(bodyRect.height) } : null,
            tagRect: tagRect ? { x: Math.round(tagRect.x), y: Math.round(tagRect.y), w: Math.round(tagRect.width), h: Math.round(tagRect.height) } : null,
            handleSrcZ: handleSrc ? getComputedStyle(handleSrc).zIndex : null,
            computedOverflow: getComputedStyle(n).overflow,
            nodeHTML_height: n.offsetHeight,
            nodeScrollHeight: n.scrollHeight,
        };
    });
}""")
        print("\n===== 诊断1: 节点DOM ======")
        print(json.dumps(diag1, indent=2, ensure_ascii=False))

        # ====== 诊断2: ReactFlow 容器链 overflow ======
        diag2 = page.evaluate("""() => {
    const chain = [
        '.react-flow',
        '.react-flow__container',
        '.react-flow__renderer',
        '.react-flow__viewport',
        '.react-flow__nodes',
        '.react-flow__edges',
        '.react-flow__pane',
    ];
    return chain.map(sel => {
        const el = document.querySelector(sel);
        if (!el) return { sel, exists: false };
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {
            sel,
            exists: true,
            rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
            overflow: s.overflow,
            overflowX: s.overflowX,
            overflowY: s.overflowY,
            position: s.position,
            zIndex: s.zIndex,
            height: el.offsetHeight,
            scrollHeight: el.scrollHeight,
        };
    });
}""")
        print("\n===== 诊断2: RF容器链 ======")
        print(json.dumps(diag2, indent=2, ensure_ascii=False))

        # ====== 诊断3: NodeChatPrompt 输入栏状态 ======
        diag3 = page.evaluate("""() => {
    const bar = document.querySelector('.node-chat-prompt');
    if (!bar) return { exists: false };
    const r = bar.getBoundingClientRect();
    const s = getComputedStyle(bar);
    return {
        exists: true,
        visible: s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0,
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        position: s.position,
        zIndex: s.zIndex,
        background: s.background.slice(0, 60),
        dataKind: bar.getAttribute('data-kind'),
    };
}""")
        print("\n===== 诊断3: 输入栏 ======")
        print(json.dumps(diag3, indent=2, ensure_ascii=False))

        # 点击一个节点后再次检查
        nodes = page.locator(".react-flow__node")
        tb = nodes.nth(0).bounding_box()
        page.mouse.click(tb["x"] + tb["width"]/2, tb["y"] + tb["height"]*0.62)
        page.wait_for_timeout(500)
        page.screenshot(path=str(SOTS := SHOTS / "diag_01_after_click.png"))
        print(f"[shot] {SOTS}")

        # 诊断4: 点击后的输入栏+节点关系
        diag4 = page.evaluate("""() => {
    const bar = document.querySelector('.node-chat-prompt');
    const barRect = bar ? bar.getBoundingClientRect() : null;
    const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
    return {
        bar: barRect ? {
            x: Math.round(barRect.x), y: Math.round(barRect.y),
            w: Math.round(barRect.width), h: Math.round(barRect.height),
            bottom: Math.round(barRect.bottom),
        } : null,
        nodes: nodes.map((n, i) => {
            const r = n.getBoundingClientRect();
            const body = n.querySelector('.pea-node-body-card');
            const br = body ? body.getBoundingClientRect() : null;
            return {
                i, id: n.getAttribute('data-id'),
                nodeBottom: Math.round(r.bottom),
                bodyBottom: br ? Math.round(br.bottom) : null,
                barOverlapsBody: barRect && br ? (
                    barRect.left < br.right && barRect.right > br.left &&
                    barRect.top < br.bottom && barRect.bottom > br.top
                ) : false,
            };
        }),
    };
}""")
        print("\n===== 诊断4: 输入栏vs节点重叠 ======")
        print(json.dumps(diag4, indent=2, ensure_ascii=False))

        # ====== 诊断5: 模拟连线中状态 ======
        src = nodes.nth(0).locator(".react-flow__handle.source").first
        hb = src.bounding_box()
        if hb:
            hx, hy = hb["x"] + hb["width"]/2, hb["y"] + hb["height"]/2
            page.mouse.move(hx, hy)
            page.mouse.down()
            page.wait_for_timeout(200)
            page.screenshot(path=str(SOTS := SHOTS / "diag_02_connecting.png"))
            print(f"[shot] {SOTS}")

            diag5 = page.evaluate("""() => {
                const vf = document.querySelector('.react-flow__viewport');
                const connecting = vf?.classList.contains('react-flow__connecting') || false;
                const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
                return {
                    connectingClass: connecting,
                    viewportClasses: vf?.className || '',
                    nodeOpacities: nodes.map(n => ({
                        id: n.getAttribute('data-id'),
                        opacity: getComputedStyle(n).opacity,
                        visibility: getComputedStyle(n).visibility,
                        display: getComputedStyle(n).display,
                        rect: (() => { const r=n.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                    })),
                };
            }""")
            print("\n===== 诊断5: 连线中状态 ======")
            print(json.dumps(diag5, indent=2, ensure_ascii=False))
            page.mouse.up()

        b.close()
        print("\n诊断完成")

if __name__ == "__main__":
    main()
