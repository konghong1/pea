// 裁切几何逻辑单测：直接验证 ./pea-server/web/src/components/cropMath 的 updateCrop
// 运行：esbuild 打包后 node 执行（见下方命令）
import { updateCrop, MIN_CROP } from '../pea-server/web/src/components/cropMath';

let failures = 0;
function check(cond: boolean, msg: string) {
  if (cond) {
    console.log('  PASS  ', msg);
  } else {
    console.error('  FAIL  ', msg);
    failures++;
  }
}
function approx(a: number, b: number, eps = 1e-6) {
  return Math.abs(a - b) <= eps;
}

const W = 800;
const H = 600;
const ratio = 4 / 3; // 锁定比例场景
const rect = { x: 100, y: 80, w: 400, h: 300 };

console.log('— 边线拖拽：长度不变、只沿法线单方向变化（忽略比例锁）—');
let r = updateCrop('n', rect, 0, 50, W, H, ratio);
check(r.w === rect.w, `n: 宽度(横线长度)不变 = ${r.w}`);
check(r.x === rect.x, `n: x 不变 = ${r.x}`);
check(r.y === rect.y + 50, `n: 顶边下移 50 -> y=${r.y}`);
check(r.h === rect.h - 50, `n: 框高收缩 50 -> h=${r.h}`);

r = updateCrop('n', rect, 0, -30, W, H, ratio);
check(r.w === rect.w, `n(上移, 锁定比例): 宽度仍不变 = ${r.w}`); // 关键回归点
check(r.y === rect.y - 30, `n: 顶边上移 30 -> y=${r.y}`);

r = updateCrop('e', rect, 30, 0, W, H, ratio);
check(r.h === rect.h, `e: 高度(竖线长度)不变 = ${r.h}`);
check(r.y === rect.y, `e: y 不变 = ${r.y}`);
check(r.w === rect.w + 30, `e: 右边右移 30 -> w=${r.w}`);

r = updateCrop('w', rect, -20, 0, W, H, ratio);
check(r.h === rect.h, `w: 高度不变 = ${r.h}`);
check(r.w === rect.w + 20 && r.x === rect.x - 20, `w: 左边左移 20 -> x=${r.x}, w=${r.w}`);

r = updateCrop('s', rect, 0, 40, W, H, ratio);
check(r.w === rect.w, `s: 宽度不变 = ${r.w}`);
check(r.h === rect.h + 40, `s: 底边下移 40 -> h=${r.h}`);

console.log('— 边界钳制 —');
r = updateCrop('n', rect, 0, -10000, W, H, ratio); // 顶边顶到最上
check(r.y === 0 && r.h === rect.y + rect.h, `n 上越界: y=0, h=${r.h}`);
r = updateCrop('s', rect, 0, 10000, W, H, ratio); // 底边顶到最下
check(approx(r.h, H - rect.y), `s 下越界: h≈H-y=${r.h}`);
r = updateCrop('n', rect, 0, 10000, W, H, ratio); // 顶边顶到底（最小裁切）
check(r.h === MIN_CROP && approx(r.y, rect.y + rect.h - MIN_CROP), `n 下越界: h=MIN_CROP=${r.h}`);

console.log('— 角点缩放 —');
r = updateCrop('se', rect, 30, 10, W, H, null);
check(r.w === rect.w + 30 && r.h === rect.h + 10, `se(自由): 双轴独立 w=${r.w}, h=${r.h}`);
r = updateCrop('se', rect, 0, 60, W, H, ratio);
check(approx(r.w / r.h, ratio), `se(锁定比例): 比例保持 w/h=${ (r.w / r.h).toFixed(4) } ≈ ${ratio}`);

console.log('— 整框平移 —');
r = updateCrop('move', rect, 20, -15, W, H, ratio);
check(r.x === rect.x + 20 && r.y === rect.y - 15 && r.w === rect.w && r.h === rect.h, `move: 仅平移 x=${r.x}, y=${r.y}`);

console.log(failures === 0 ? '\n✅ ALL PASS' : `\n❌ ${failures} FAILED`);
if (failures > 0) process.exit(1);
