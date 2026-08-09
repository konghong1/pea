// cropDrag.ts — 裁切框拖拽类型判定（纯函数，可单测，不依赖 React/DOM 运行时）
//
// 根据鼠标按下点在裁切框内的相对位置，判定应触发哪种拖拽：
//   - 同时贴近两条边 → 角点(nw/ne/sw/se)
//   - 仅贴近一条边 → 对应边(n/s/e/w)（整条边都可抓，不再只有中点把手）
//   - 都不贴近     → 整体平移(move)
// 配合 startDrag 用「按下点的精确 flow 坐标」计算位移，保证「点哪条边，鼠标就锁在那条边上」。
import type { CropDragType } from '../components/cropMath';

/**
 * @param rect 裁切框的屏幕矩形（getBoundingClientRect 结果）
 * @param clientX / clientY 鼠标按下点的屏幕坐标
 * @param band 边框命中带宽度（屏幕 px）。任意画布缩放下都用屏幕 px 判定，抓取手感一致。
 */
export function resolveDragType(
  rect: { left: number; top: number; width: number; height: number },
  clientX: number,
  clientY: number,
  band = 12,
): CropDragType {
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  const w = rect.width;
  const h = rect.height;
  const left = x <= band;
  const right = x >= w - band;
  const top = y <= band;
  const bottom = y >= h - band;
  if (top && left) return 'nw';
  if (top && right) return 'ne';
  if (bottom && left) return 'sw';
  if (bottom && right) return 'se';
  if (top) return 'n';
  if (bottom) return 's';
  if (left) return 'w';
  if (right) return 'e';
  return 'move';
}
