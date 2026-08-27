// cropMath.ts — 裁剪几何计算的纯函数（与 React / DOM 解耦，可单测）
// 设计要点：
//   - 角点(nw/ne/sw/se)：缩放。自由模式双轴独立；锁定比例时以对角为锚点等比缩放。
//   - 边线(n/s/e/w)：【只沿法线方向移动】，对边固定，且【该边自身长度（垂直方向尺寸）不变】。
//     此行为在任何比例模式下都生效 —— 边线拖拽故意忽略比例锁，保证单方向、长度不变，符合直觉。

export type Rect = { x: number; y: number; w: number; h: number };
export type CropDragType = 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w';

export const MIN_CROP = 64;

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/**
 * 把一次拖拽计算出的浮点 rect 取整，同时保证「不动的那一角/边」像素级固定，
 * 避免对角线角点拖拽时锚点因 x/w、y/h 被独立取整而 1px 跳动（Bug 3）。
 *
 * 思路：对"移动角/边"取整，再用 start 的对角坐标反推对边尺寸，
 * 使锚点 = start 的对角坐标（恒定），拖拽过程中不漂移。
 */
export function snapCropToAnchor(type: CropDragType, start: Rect, next: Rect): Rect {
  switch (type) {
    case 'nw': {
      const x = Math.round(next.x);
      const y = Math.round(next.y);
      return { x, y, w: Math.max(MIN_CROP, start.x + start.w - x), h: Math.max(MIN_CROP, start.y + start.h - y) };
    }
    case 'ne': {
      const y = Math.round(next.y);
      const w = Math.round(next.w);
      return { x: start.x, y, w, h: Math.max(MIN_CROP, start.y + start.h - y) };
    }
    case 'sw': {
      const x = Math.round(next.x);
      const h = Math.round(next.h);
      return { x, y: start.y, w: Math.max(MIN_CROP, start.x + start.w - x), h };
    }
    case 'se': {
      const w = Math.round(next.w);
      const h = Math.round(next.h);
      return { x: start.x, y: start.y, w, h };
    }
    case 'n': {
      const y = Math.round(next.y);
      return { x: start.x, y, w: start.w, h: Math.max(MIN_CROP, start.y + start.h - y) };
    }
    case 's': {
      const h = Math.round(next.h);
      return { x: start.x, y: start.y, w: start.w, h: Math.max(MIN_CROP, h) };
    }
    case 'w': {
      const x = Math.round(next.x);
      return { x, y: start.y, w: Math.max(MIN_CROP, start.x + start.w - x), h: start.h };
    }
    case 'e': {
      const w = Math.round(next.w);
      return { x: start.x, y: start.y, w: Math.max(MIN_CROP, w), h: start.h };
    }
    case 'move':
    default:
      return { x: Math.round(next.x), y: Math.round(next.y), w: Math.round(next.w), h: Math.round(next.h) };
  }
}

export function updateCrop(
  type: CropDragType,
  start: Rect,
  dx: number,
  dy: number,
  W: number,
  H: number,
  ratio: number | null,
): Rect {
  if (type === 'move') {
    return {
      x: clamp(start.x + dx, 0, W - start.w),
      y: clamp(start.y + dy, 0, H - start.h),
      w: start.w,
      h: start.h,
    };
  }

  // 边线：永远单边移动（只改法线方向位置，垂直方向尺寸 = 边长 不变），不受比例锁影响
  if (type === 'n' || type === 's' || type === 'e' || type === 'w') {
    const next: Rect = { ...start };
    if (type === 'n') {
      // 顶边上下移动：x / w（横线长度）不变
      // 若当前高度已至 MIN_CROP，继续同向拖拽 (dy>0) 应锁定 y 不变，防止 next.h 回弹变大
      const maxDy = start.h - MIN_CROP;
      const clampedDy = dy > 0 ? Math.min(dy, maxDy) : dy;
      next.y = clamp(start.y + clampedDy, 0, start.y + start.h - MIN_CROP);
      next.h = start.h + start.y - next.y;
    } else if (type === 's') {
      // 底边上下移动：x / w 不变
      const maxDy = MIN_CROP - start.h; // start.h 已到 MIN_CROP 时，dy<0 应锁定
      const clampedDy = dy < 0 ? Math.max(dy, maxDy) : dy;
      next.h = clamp(start.h + clampedDy, MIN_CROP, H - start.y);
    } else if (type === 'w') {
      // 左边左右移动：y / h（竖线长度）不变
      const maxDx = start.w - MIN_CROP;
      const clampedDx = dx > 0 ? Math.min(dx, maxDx) : dx;
      next.x = clamp(start.x + clampedDx, 0, start.x + start.w - MIN_CROP);
      next.w = start.w + start.x - next.x;
    } else {
      // e 右边左右移动：y / h 不变
      const maxDx = MIN_CROP - start.w;
      const clampedDx = dx < 0 ? Math.max(dx, maxDx) : dx;
      next.w = clamp(start.w + clampedDx, MIN_CROP, W - start.x);
    }
    return next;
  }

  // 角点：自由模式双轴独立缩放
  if (ratio == null) {
    const next: Rect = { ...start };
    switch (type) {
      case 'nw': {
        const nx = clamp(start.x + dx, 0, start.x + start.w - MIN_CROP);
        const ny = clamp(start.y + dy, 0, start.y + start.h - MIN_CROP);
        // 一旦某方向已触底（start 本身被冻结到 MIN_CROP），继续同向拖拽时
        // 对边不应继续外移导致框变大——直接用 start 的冻结尺寸算对边位置
        next.x = nx;
        next.y = ny;
        next.w = start.w + start.x - nx;
        next.h = start.h + start.y - ny;
        break;
      }
      case 'ne': {
        const ny = clamp(start.y + dy, 0, start.y + start.h - MIN_CROP);
        const nw = clamp(start.w + dx, MIN_CROP, W - start.x);
        next.y = ny;
        next.w = nw;
        next.h = start.h + start.y - ny;
        break;
      }
      case 'sw': {
        const nx = clamp(start.x + dx, 0, start.x + start.w - MIN_CROP);
        const nh = clamp(start.h + dy, MIN_CROP, H - start.y);
        next.x = nx;
        next.w = start.w + start.x - nx;
        next.h = nh;
        break;
      }
      case 'se': {
        const nw = clamp(start.w + dx, MIN_CROP, W - start.x);
        const nh = clamp(start.h + dy, MIN_CROP, H - start.y);
        next.w = nw;
        next.h = nh;
        break;
      }
    }
    return next;
  }

  // 角点 + 锁定比例：以对角为锚点等比缩放
  // 先按 dx/dy 方向分别算原始目标宽高，再选更紧的约束维度整体缩放，
  // 保证同一方向拖拽时宽高单调变化、不会出现反弹。
  // dx/dy 限制在 [−start.<axis>, max.<axis>−start.<axis>] 内，防止鼠标越出图像时框无限膨胀。
  let rawW: number, rawH: number;
  switch (type) {
    case 'se':
      rawW = clamp(start.w + dx, 0, W - start.x);
      rawH = clamp(start.h + dy, 0, H - start.y);
      break;
    case 'sw':
      rawW = clamp(start.w - dx, 0, start.x + start.w);
      rawH = clamp(start.h + dy, 0, H - start.y);
      break;
    case 'ne':
      rawW = clamp(start.w + dx, 0, W - start.x);
      rawH = clamp(start.h - dy, 0, start.y + start.h);
      break;
    case 'nw':
      rawW = clamp(start.w - dx, 0, start.x + start.w);
      rawH = clamp(start.h - dy, 0, start.y + start.h);
      break;
    default: return start;
  }
  const maxW = type === 'se' || type === 'ne' ? W - start.x : start.x + start.w;
  const maxH = type === 'se' || type === 'sw' ? H - start.y : start.y + start.h;
  // 选更紧的约束：byW 看宽度方向能否容纳 rawW，byH 看高度方向能否容纳 rawH
  const byW_h = rawW / ratio; // 宽度主导时的高度
  const byH_w = rawH * ratio; // 高度主导时的宽度
  const useW = byW_h <= maxH; // 宽度更紧或两者相近，按宽度缩放
  const w = clamp(useW ? start.w * (rawW / start.w) : byH_w, MIN_CROP, maxW);
  const h = clamp(useW ? byW_h : start.h * (rawH / start.h), MIN_CROP, maxH);
  switch (type) {
    case 'se': return { ...start, w, h };
    case 'sw': return { x: start.x + start.w - w, y: start.y, w, h };
    case 'ne': return { x: start.x, y: start.y + start.h - h, w, h };
    case 'nw': return { x: start.x + start.w - w, y: start.y + start.h - h, w, h };
    default: return start;
  }
}
