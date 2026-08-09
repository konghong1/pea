// 验证裁切框拖拽判定（问题2修复）：
//  1) 整条边（含非中点位置）点击都判定为对应边拖拽，而非整体 move；
//  2) 边拖拽时，被拖的那条边始终跟随鼠标——鼠标锁在按下那条边上，不再跑进框内。
//
// 坐标约定（与真实组件一致）：
//  - resolveDragType 接收【裁切框自身的屏幕矩形】(frame.getBoundingClientRect) + 鼠标绝对屏幕坐标；
//  - 拖拽数学用【舞台矩形】把 flow 坐标 ↔ 屏幕坐标互转（与 startDrag 内一致）。
import { resolveDragType } from '../pea-server/web/src/lib/cropDrag';
import { updateCrop } from '../pea-server/web/src/components/cropMath';

let failures = 0;
function check(cond: boolean, msg: string) {
  if (cond) console.log('  PASS  ', msg);
  else { console.error('  FAIL  ', msg); failures++; }
}
function approx(a: number, b: number, eps = 1e-6) { return Math.abs(a - b) <= eps; }

const ZOOM = 1.5;
// 舞台（stage）屏幕矩形
const stage = { left: 500, top: 300, width: 400 * ZOOM, height: 300 * ZOOM };
const W = 400, H = 300;            // 舞台 flow 尺寸
const sx = stage.width / W;        // = ZOOM
const sy = stage.height / H;       // = ZOOM
// 裁切框在舞台内的 flow 位置（必须合法：x+w<=W, y+h<=H）
const frameFlow = { x: 100, y: 60, w: 200, h: 180 };
// 裁切框自身屏幕矩形（传给 resolveDragType 的 rect）
const frameScreen = {
  left: stage.left + frameFlow.x * sx,
  top: stage.top + frameFlow.y * sy,
  width: frameFlow.w * sx,
  height: frameFlow.h * sy,
};

// flow(舞台内) → 绝对屏幕坐标（用于构造点击点与拖拽数学）
const toScreenX = (fx: number) => stage.left + fx * sx;
const toScreenY = (fy: number) => stage.top + fy * sy;
// 在裁切框内、以框自身为原点的偏移 → 绝对屏幕坐标
const onFrame = (ox: number, oy: number) => ({
  x: frameScreen.left + ox * sx,
  y: frameScreen.top + oy * sy,
});

console.log('— 判定：整条边（含非中点）点击都应得到边拖拽 —');
check(resolveDragType(frameScreen, onFrame(frameFlow.w, frameFlow.h / 2).x, onFrame(frameFlow.w, frameFlow.h / 2).y) === 'e',
  '右边缘中点 → e');
check(resolveDragType(frameScreen, onFrame(frameFlow.w, 30).x, onFrame(frameFlow.w, 30).y) === 'e',
  '右边缘非中点(框内偏移30) → e（修复点：过去这里会触发整体 move）');
check(resolveDragType(frameScreen, onFrame(0, 90).x, onFrame(0, 90).y) === 'w',
  '左边缘非中点(框内偏移90) → w');
check(resolveDragType(frameScreen, onFrame(120, 0).x, onFrame(120, 0).y) === 'n',
  '顶边非中点 → n');
check(resolveDragType(frameScreen, onFrame(100, frameFlow.h).x, onFrame(100, frameFlow.h).y) === 's',
  '底边非中点 → s');
check(resolveDragType(frameScreen, onFrame(0, 0).x, onFrame(0, 0).y) === 'nw', '左上角 → nw');
check(resolveDragType(frameScreen, onFrame(frameFlow.w, 0).x, onFrame(frameFlow.w, 0).y) === 'ne', '右上角 → ne');
check(resolveDragType(frameScreen, onFrame(frameFlow.w, frameFlow.h).x, onFrame(frameFlow.w, frameFlow.h).y) === 'se', '右下角 → se');
// 框内（远离边）→ move
check(resolveDragType(frameScreen, onFrame(100, 90).x, onFrame(100, 90).y) === 'move',
  '框内远离边 → move（整体平移）');

console.log('— 拖拽数学：被拖的边始终跟随鼠标（鼠标锁在边上）—');
function simulateEdgeDrag(startClient: {x:number;y:number}, moveClient: {x:number;y:number}, type: string) {
  const startFx = (startClient.x - stage.left) / sx;
  const startFy = (startClient.y - stage.top) / sy;
  const curFx = (moveClient.x - stage.left) / sx;
  const curFy = (moveClient.y - stage.top) / sy;
  const dx = curFx - startFx;
  const dy = curFy - startFy;
  return updateCrop(type as any, { ...frameFlow }, dx, dy, W, H, null);
}

// 在右边缘【非中点】(框内 y=30) 按下，向右拖动 50 flow px
{
  const start = onFrame(frameFlow.w, 30);
  const move = onFrame(frameFlow.w + 50, 30);
  const r = simulateEdgeDrag(start, move, 'e');
  const rightEdge = r.x + r.w;
  const mouseFlowX = (move.x - stage.left) / sx;
  check(approx(rightEdge, mouseFlowX), `右键拖右50px：右边界=鼠标flowX(${rightEdge.toFixed(1)}≈${mouseFlowX.toFixed(1)})，鼠标贴在右边上`);
  check(r.h === frameFlow.h, 'e 拖拽：高度(竖线长度)不变');
}

// 在顶边【非中点】(框内 x=120) 按下，向上拖动 40 flow px
{
  const start = onFrame(120, 0);
  const move = onFrame(120, -40);
  const r = simulateEdgeDrag(start, move, 'n');
  const topEdge = r.y;
  const mouseFlowY = (move.y - stage.top) / sy;
  check(approx(topEdge, mouseFlowY), `顶边拖上40px：顶边界=鼠标flowY(${topEdge.toFixed(1)}≈${mouseFlowY.toFixed(1)})，鼠标贴在顶边上`);
  check(r.w === frameFlow.w, 'n 拖拽：宽度(横线长度)不变');
}

// 关键对照：在右边缘非中点按下，若误判为 move 则鼠标会跑进框内；现在判定为 e，鼠标锁定在边
{
  const start = onFrame(frameFlow.w, 30);
  const move = onFrame(frameFlow.w + 70, 30);
  const type = resolveDragType(frameScreen, start.x, start.y);
  check(type === 'e', `贴右边缘非中点按下 → 判定为 e（不是 move），从而鼠标锁定在边`);
  if (type === 'e') {
    const r = simulateEdgeDrag(start, move, 'e');
    check(approx(r.x + r.w, (move.x - stage.left) / sx), '鼠标始终在右边线上（未跑进框内）');
  }
}

console.log(failures === 0 ? '\n✅ ALL PASS' : `\n❌ ${failures} FAILED`);
if (failures > 0) process.exit(1);
