// 全面的裁切框拖拽测试：验证 zoom≠1 场景下修复后的正确性
import { updateCrop, clamp, type Rect } from '../pea-server/web/src/components/cropMath';

let pass = 0, fail = 0;
function check(cond: boolean, msg: string) {
  if (cond) { pass++; console.log('  PASS  ', msg); }
  else { fail++; console.error('  FAIL  ', msg); }
}
function approx(a: number, b: number, eps = 1) { return Math.abs(a - b) <= eps; }

/**
 * 模拟修复后的 startDrag compute 闭包（与 ImageCropOverlay 一致）。
 * cx/cy 是相对于 initialFrameRect.left/top 的屏幕坐标。
 */
function makeComputeFixed(
  type: 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w',
  startFlow: Rect,
  startRectScreen: Rect,
  offX: number, offY: number,
  W: number, H: number, ratio: number | null,
  zoom: number,
) {
  return (cx: number, cy: number): Rect => {
    if (type === 'move') {
      const flowDx = (cx - offX - startRectScreen.x) / zoom;
      const flowDy = (cy - offY - startRectScreen.y) / zoom;
      return {
        x: clamp(Math.round(startFlow.x + flowDx), 0, W - Math.round(startFlow.w)),
        y: clamp(Math.round(startFlow.y + flowDy), 0, H - Math.round(startFlow.h)),
        w: Math.round(startFlow.w),
        h: Math.round(startFlow.h),
      };
    }
    const dx = (cx - offX - startRectScreen.x) / zoom;
    const dy = (cy - offY - startRectScreen.y) / zoom;
    return updateCrop(type as any, startFlow, dx, dy, W, H, ratio);
  };
}

function makeStartDragFixed(
  type: 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w',
  crop: Rect,
  initialFrameRect: { left: number; top: number; width: number; height: number },
  startScreen: { x: number; y: number },
  W: number, H: number, ratio: number | null,
  zoom: number,
) {
  const startFlow: Rect = {
    x: initialFrameRect.left / zoom,
    y: initialFrameRect.top / zoom,
    w: initialFrameRect.width  / zoom,
    h: initialFrameRect.height / zoom,
  };
  const startRectScreen: Rect = {
    x: Math.round(initialFrameRect.left),
    y: Math.round(initialFrameRect.top),
    w: Math.round(initialFrameRect.width),
    h: Math.round(initialFrameRect.height),
  };
  // startScreen is absolute; make it relative to frame
  const relStartX = startScreen.x - initialFrameRect.left;
  const relStartY = startScreen.y - initialFrameRect.top;
  const offX = relStartX - startRectScreen.x;
  const offY = relStartY - startRectScreen.y;
  return makeComputeFixed(type, startFlow, startRectScreen, offX, offY, W, H, ratio, zoom);
}

function buildFrameRect(crop: Rect, zoom: number): { left: number; top: number; width: number; height: number } {
  return { left: crop.x * zoom, top: crop.y * zoom, width: crop.w * zoom, height: crop.h * zoom };
}

console.log('=== zoom=1（基准）===');
{
  const W = 400, H = 300, zoom = 1;
  const crop: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const frameRect = buildFrameRect(crop, zoom); // left=100, top=80
  const compute = makeStartDragFixed('se', crop, frameRect,
    { x: 300, y: 230 }, W, H, null, zoom);
  // screen (340,260) → relative (240,180); start relative=(200,150) → +40/+30 flow
  const result = compute(240, 180);
  check(result.w === 240 && result.h === 180,
    `se zoom=1: w=240, h=180 (got w=${result.w}, h=${result.h})`);
  const computeMove = makeStartDragFixed('move', crop, frameRect,
    { x: 150, y: 130 }, W, H, null, zoom);
  // screen (190, 140) → relative (90, 60); start relative=(50,50) → +40/+10 flow
  const rMove = computeMove(90, 60);
  check(rMove.x === 140 && rMove.y === 90,
    `move zoom=1: x=140, y=90 (got x=${rMove.x}, y=${rMove.y})`);
}

console.log('\n=== zoom=2（修复后）===');
{
  const W = 400, H = 300, zoom = 2;
  const crop: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const frameRect = buildFrameRect(crop, zoom); // left=200, top=160
  // click at se corner: flow (300, 230) → screen (600, 460)
  const compute = makeStartDragFixed('se', crop, frameRect,
    { x: 600, y: 460 }, W, H, null, zoom);
  // screen (645, 505) → relative (445, 345); start relative=(400,300) → +45/+45 screen = +22.5/+22.5 flow
  const result = compute(445, 345);
  check(
    approx(result.w, 222.5, 1) && approx(result.h, 172.5, 1),
    `se zoom=2: w≈222.5, h≈172.5 (got w=${result.w}, h=${result.h})`
  );
  // move: click at screen (300, 260) → relative (100, 100); move to (345, 260) → relative (145, 100)
  const computeMove = makeStartDragFixed('move', crop, frameRect,
    { x: 300, y: 260 }, W, H, null, zoom);
  const rMove = computeMove(145, 100);
  check(approx(rMove.x, 122.5, 1), `move zoom=2: x≈122.5 (got ${rMove.x})`);
  check(approx(rMove.x - 100, 22.5, 1), `move zoom=2: 框移动 22.5 flow px（鼠标 45px / zoom=2）`);
}

console.log('\n=== zoom=0.5（修复后）===');
{
  const W = 400, H = 300, zoom = 0.5;
  const crop: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const frameRect = buildFrameRect(crop, zoom); // left=50, top=40
  // click at se corner: flow (300, 230) → screen (150, 115)
  const compute = makeStartDragFixed('se', crop, frameRect,
    { x: 150, y: 115 }, W, H, null, zoom);
  // screen (170, 135) → relative (120, 95); start relative=(100,75) → +20/+20 screen = +40/+40 flow
  const result = compute(120, 95);
  check(
    approx(result.w, 240, 1) && approx(result.h, 190, 1),
    `se zoom=0.5: w≈240, h≈190 (got w=${result.w}, h=${result.h})`
  );
}

console.log('\n=== move 速度一致性（zoom=2）===');
{
  const W = 400, H = 300, zoom = 2;
  const crop: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const frameRect = buildFrameRect(crop, zoom); // left=200, top=160
  const computeMove = makeStartDragFixed('move', crop, frameRect,
    { x: 300, y: 260 }, W, H, null, zoom);
  // screen (340, 260) → relative (140, 100); start relative=(100,100) → +40 screen = +20 flow
  const rMove = computeMove(140, 100);
  check(rMove.x === 120,
    `move zoom=2: 框移动 20 flow px（鼠标 40px / zoom=2）(got x=${rMove.x})`);
}

console.log('\n=== resize 速度一致性（zoom=2）===');
{
  const W = 400, H = 300, zoom = 2;
  const crop: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const frameRect = buildFrameRect(crop, zoom); // left=200, top=160
  const computeSe = makeStartDragFixed('se', crop, frameRect,
    { x: 600, y: 460 }, W, H, null, zoom);
  // screen (640, 500) → relative (440, 340); start relative=(400,300) → +40/+40 screen = +20/+20 flow
  const rSe = computeSe(440, 340);
  check(rSe.w === 220 && rSe.h === 170,
    `se zoom=2: dx=20 flow px → w=220, h=170 (got w=${rSe.w}, h=${rSe.h})`);
}

console.log('\n=== 所有方向 resize 速度测试（zoom=2）===');
{
  const W = 400, H = 300, zoom = 2;
  const crop: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const frameRect = buildFrameRect(crop, zoom); // left=200, top=160
  const types: Array<'nw'|'ne'|'sw'|'se'> = ['nw', 'ne', 'sw', 'se'];
  for (const dir of types) {
    const flowClick = dir === 'nw' ? { x: 100, y: 80 } :
      dir === 'ne' ? { x: 300, y: 80 } :
      dir === 'sw' ? { x: 100, y: 230 } :
      { x: 300, y: 230 };
    const screenClick = { x: flowClick.x * zoom, y: flowClick.y * zoom };
    const compute = makeStartDragFixed(dir, crop, frameRect,
      screenClick, W, H, null, zoom);
    const screenDx = dir === 'nw' || dir === 'ne' ? 30 : -30;
    const screenDy = dir === 'nw' || dir === 'sw' ? 20 : -20;
    const moveScreen = { x: screenClick.x + screenDx, y: screenClick.y + screenDy };
    // convert to relative coords
    const result = compute(moveScreen.x - 200, moveScreen.y - 160);
    const flowDx = screenDx / zoom;
    const flowDy = screenDy / zoom;
    if (dir === 'se') {
      check(approx(result.w, 200 + flowDx, 1) && approx(result.h, 150 + flowDy, 1),
        `se zoom=2: w≈${200+flowDx}, h≈${150+flowDy} (got w=${result.w}, h=${result.h})`);
    } else if (dir === 'sw') {
      check(approx(result.x, 100 + flowDx, 1) && approx(result.w, 200 - flowDx, 1) && approx(result.h, 150 + flowDy, 1),
        `sw zoom=2: x=${result.x} w=${result.w} h=${result.h}`);
    } else if (dir === 'ne') {
      check(approx(result.y, 80 + flowDy, 1) && approx(result.w, 200 + flowDx, 1) && approx(result.h, 150 - flowDy, 1),
        `ne zoom=2: y=${result.y} w=${result.w} h=${result.h}`);
    } else {
      check(approx(result.x, 100 + flowDx, 1) && approx(result.y, 80 + flowDy, 1) &&
            approx(result.w, 200 - flowDx, 1) && approx(result.h, 150 - flowDy, 1),
        `nw zoom=2: x=${result.x} y=${result.y} w=${result.w} h=${result.h}`);
    }
  }
}

console.log('\n=== Bug 2 验证：startRect 来自 DOM rect（非 crop state）===');
{
  const W = 400, H = 300, zoom = 1;
  const cropFuzzy: Rect = { x: 100.3, y: 80.7, w: 200.2, h: 150.8 };
  const frameRect = { left: 100, top: 81, width: 200, height: 151 };
  const compute = makeStartDragFixed('move', cropFuzzy, frameRect,
    { x: 200, y: 156 }, W, H, null, zoom);
  // screen (200, 156) → relative (100, 75); start relative=(100,75) → no movement
  const r = compute(100, 75);
  check(r.x === 100 && r.y === 81,
    `Bug2 fix: 鼠标不动时框位置不变 (got x=${r.x}, y=${r.y})`);
}

console.log('\n=== 结论 ===');
console.log(`${pass} PASS / ${fail} FAIL`);
process.exit(fail === 0 ? 0 : 1);
