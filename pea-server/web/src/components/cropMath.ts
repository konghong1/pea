// cropMath.ts — 裁剪几何计算的纯函数（与 React / DOM 解耦，可单测）
// 设计要点：
//   - 角点(nw/ne/sw/se)：缩放。自由模式双轴独立；锁定比例时以对角为锚点等比缩放。
//   - 边线(n/s/e/w)：【只沿法线方向移动】，对边固定，且【该边自身长度（垂直方向尺寸）不变】。
//     此行为在任何比例模式下都生效 —— 边线拖拽故意忽略比例锁，保证单方向、长度不变，符合直觉。

export type Rect = { x: number; y: number; w: number; h: number };
export type CropDragType = 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w';

export const MIN_CROP = 32;

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
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
      next.y = clamp(start.y + dy, 0, start.y + start.h - MIN_CROP);
      next.h = start.h + start.y - next.y;
    } else if (type === 's') {
      // 底边上下移动：x / w 不变
      next.h = clamp(start.h + dy, MIN_CROP, H - start.y);
    } else if (type === 'w') {
      // 左边左右移动：y / h（竖线长度）不变
      next.x = clamp(start.x + dx, 0, start.x + start.w - MIN_CROP);
      next.w = start.w + start.x - next.x;
    } else {
      // e 右边左右移动：y / h 不变
      next.w = clamp(start.w + dx, MIN_CROP, W - start.x);
    }
    return next;
  }

  // 角点：自由模式双轴独立缩放
  if (ratio == null) {
    const next: Rect = { ...start };
    switch (type) {
      case 'nw':
        next.x = clamp(start.x + dx, 0, start.x + start.w - MIN_CROP);
        next.y = clamp(start.y + dy, 0, start.y + start.h - MIN_CROP);
        next.w = start.w + start.x - next.x;
        next.h = start.h + start.y - next.y;
        break;
      case 'ne':
        next.y = clamp(start.y + dy, 0, start.y + start.h - MIN_CROP);
        next.w = clamp(start.w + dx, MIN_CROP, W - start.x);
        next.h = start.h + start.y - next.y;
        break;
      case 'sw':
        next.x = clamp(start.x + dx, 0, start.x + start.w - MIN_CROP);
        next.w = start.w + start.x - next.x;
        next.h = clamp(start.h + dy, MIN_CROP, H - start.y);
        break;
      case 'se':
        next.w = clamp(start.w + dx, MIN_CROP, W - start.x);
        next.h = clamp(start.h + dy, MIN_CROP, H - start.y);
        break;
    }
    return next;
  }

  // 角点 + 锁定比例：以对角为锚点等比缩放
  const fitByWidth = (w: number, maxW: number, maxH: number) => {
    const safeW = clamp(w, MIN_CROP, maxW);
    let h = safeW / ratio;
    if (h > maxH) h = clamp(maxH, MIN_CROP, maxH);
    return { w: h * ratio, h };
  };
  const fitByHeight = (h: number, maxH: number, maxW: number) => {
    const safeH = clamp(h, MIN_CROP, maxH);
    let w = safeH * ratio;
    if (w > maxW) w = clamp(maxW, MIN_CROP, maxW);
    return { w, h: w / ratio };
  };

  switch (type) {
    case 'se': {
      const { w, h } = fitByWidth(start.w + dx, W - start.x, H - start.y);
      return { ...start, w, h };
    }
    case 'sw': {
      const { w, h } = fitByWidth(start.w - dx, start.x + start.w, H - start.y);
      return { x: start.x + start.w - w, y: start.y, w, h };
    }
    case 'ne': {
      const { w, h } = fitByWidth(start.w + dx, W - start.x, start.y + start.h);
      return { ...start, y: start.y + start.h - h, w, h };
    }
    case 'nw': {
      const { w, h } = fitByWidth(start.w - dx, start.x + start.w, start.y + start.h);
      return { x: start.x + start.w - w, y: start.y + start.h - h, w, h };
    }
    default:
      return start;
  }
}
