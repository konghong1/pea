import { updateCrop, clamp, type Rect, type CropDragType } from '../pea-server/web/src/components/cropMath';

// 复刻 ImageCropOverlay.startDrag 的「绝对坐标 + stageRect 反算」方案
function simulateDrag(
  type: CropDragType,
  startRect: Rect,
  W: number,
  H: number,
  zoom: number,
  startClient: { x: number; y: number },
  moveClient: { x: number; y: number },
) {
  // 真实 DOM 实测：stage 的屏幕矩形（裁切框容器在 scale(zoom) 内）
  const stageRect = { left: 0, top: 0, width: W * zoom, height: H * zoom };
  const sx = stageRect.width / W;
  const sy = stageRect.height / H;
  const startMouseFx = (startClient.x - stageRect.left) / sx;
  const startMouseFy = (startClient.y - stageRect.top) / sy;
  const grabX = startMouseFx - startRect.x;
  const grabY = startMouseFy - startRect.y;
  const curFx = (moveClient.x - stageRect.left) / sx;
  const curFy = (moveClient.y - stageRect.top) / sy;
  if (type === 'move') {
    const x = clamp(curFx - grabX, 0, W - startRect.w);
    const y = clamp(curFy - grabY, 0, H - startRect.h);
    return { next: { x, y, w: startRect.w, h: startRect.h }, startMouseFx, startMouseFy };
  }
  const dx = curFx - startMouseFx;
  const dy = curFy - startMouseFy;
  return { next: updateCrop(type, startRect, dx, dy, W, H, null), startMouseFx, startMouseFy };
}

let pass = 0;
let fail = 0;

for (const zoom of [0.5, 1, 2]) {
  const W = 400;
  const H = 300;
  const startRect: Rect = { x: 100, y: 80, w: 200, h: 150 };
  const ox = 50; // 鼠标在裁切框内 flow 偏移
  const oy = 30;
  const startClient = { x: (startRect.x + ox) * zoom, y: (startRect.y + oy) * zoom };
  const dxScreen = 40;
  const dyScreen = 20;
  const moveClient = { x: startClient.x + dxScreen, y: startClient.y + dyScreen };

  // move：鼠标相对裁切框屏幕偏移必须全程恒定 = ox*zoom, oy*zoom
  const r = simulateDrag('move', startRect, W, H, zoom, startClient, moveClient);
  const relX = moveClient.x - r.next.x * zoom;
  const relY = moveClient.y - r.next.y * zoom;
  const okMove = Math.abs(relX - ox * zoom) < 1e-6 && Math.abs(relY - oy * zoom) < 1e-6;
  okMove ? pass++ : fail++;
  console.log(`[zoom=${zoom}] move 相对位置保持: ${okMove ? 'PASS' : 'FAIL'} (rel=${relX.toFixed(1)},${relY.toFixed(1)} 期望=${ox * zoom},${oy * zoom})`);

  // edge 'e'：右边屏幕位移必须 = 鼠标屏幕位移（边跟随鼠标的移动量）
  const re = simulateDrag('e', startRect, W, H, zoom, startClient, moveClient);
  const edgeDeltaScreen = (re.next.w - startRect.w) * zoom;
  const okE = Math.abs(edgeDeltaScreen - dxScreen) < 1e-6;
  okE ? pass++ : fail++;
  console.log(`[zoom=${zoom}] edge-e 右边跟随鼠标位移: ${okE ? 'PASS' : 'FAIL'} (Δ边=${edgeDeltaScreen.toFixed(1)} Δ鼠标=${dxScreen})`);

  // edge 'n'：顶边屏幕位移必须 = 鼠标屏幕位移
  const rn = simulateDrag('n', startRect, W, H, zoom, startClient, moveClient);
  const edgeDeltaScreenY = (rn.next.y - startRect.y) * zoom;
  const okN = Math.abs(edgeDeltaScreenY - dyScreen) < 1e-6;
  okN ? pass++ : fail++;
  console.log(`[zoom=${zoom}] edge-n 顶边跟随鼠标位移: ${okN ? 'PASS' : 'FAIL'} (Δ边=${edgeDeltaScreenY.toFixed(1)} Δ鼠标=${dyScreen})`);
}

console.log(`\n结果: ${pass} PASS / ${fail} FAIL`);
process.exit(fail === 0 ? 0 : 1);
