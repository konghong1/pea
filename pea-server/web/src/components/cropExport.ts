/**
 * cropExport — 裁剪导出的纯计算逻辑（无 DOM / 无副作用，可直接单测）。
 *
 * 背景：「把大图裁成小图后变模糊」的根因不是坐标算错，而是导出位图的
 * 像素数不足以支撑它在画布上的显示尺寸，浏览器只能插值拉伸。
 *
 * 本模块负责回答三个问题：
 *   1. 裁剪框（flow 坐标）对应原图里的哪块**真实像素**？   -> mapCropToSource
 *   2. 输出位图该做多少倍**超采样**才不糊、且不会撑爆 canvas？ -> resolveExportScale / computeCropExportPlan
 *   3. 这次裁剪在目标显示尺寸下**到底会不会糊**？             -> assessDisplaySharpness
 *
 * 渲染副作用（drawImage / toDataURL / toast）留在 ImageCropOverlay 里，
 * 这样这里的每条规则都能被 verify/crop_export.test.ts 直接断言。
 */

import { clamp, type Rect } from './cropMath';

/** 原图像素坐标系下的采样矩形（drawImage 的 sx,sy,sw,sh）。 */
export interface SourceRect {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/** 图片尺寸（naturalWidth / naturalHeight，或舞台显示尺寸）。 */
export interface Size {
  w: number;
  h: number;
}

/** 超采样倍率上限。再高收益递减，却线性推高内存与 dataURL 体积。 */
export const MAX_EXPORT_SCALE = 2;

/**
 * 输出画布的像素面积上限。
 * Safari / iOS 对 canvas 有 16,777,216 px (4096×4096 的 4 倍) 的硬限制，
 * 超过后 toDataURL 会静默返回空白图 —— 比模糊更糟。
 * 超采样会让面积 ×4，所以必须在这里兜底降级。
 */
export const MAX_OUTPUT_PIXELS = 16_777_216;

/** Bug 7: 像素比阈值（而非绝对像素数），用于判断低分辨率 */
export const LOW_RES_RATIO_THRESHOLD = 1.5;

/** 源区域小于 1px 视为无效裁剪。 */
export const MIN_SOURCE_PX = 1;

export type CropExportStatus = 'ok' | 'too-small';

export interface CropExportPlan {
  /** 原图真实像素坐标下的采样矩形。 */
  source: SourceRect;
  /** 输出位图宽（已含超采样与面积降级）。 */
  outWidth: number;
  /** 输出位图高（已含超采样与面积降级）。 */
  outHeight: number;
  /** 实际生效的超采样倍率（可能因面积上限低于请求值）。 */
  exportScale: number;
  /** 是否因触碰 MAX_OUTPUT_PIXELS 而下调了倍率。 */
  downscaledForLimit: boolean;
  /** 源区域本身分辨率是否偏低（前端无法补救，只能换高清源或 AI 超分）。 */
  lowResSource: boolean;
  /** 'too-small' 表示裁剪区无效，调用方应中止导出。 */
  status: CropExportStatus;
  /** Bug 7: 像素比（输出像素/目标物理像素） */
  pixelRatio: number;
}

/**
 * 裁剪框（stage 的 flow 坐标，坐标系尺寸 = disp.w × disp.h）
 * 映射到原图真实像素矩形。
 *
 * 注意是**乘**不是除：disp 是"原图按 scale 缩放后的显示尺寸"，
 * 所以 原图px = flow px × (nat / disp)。并对越界做钳制，
 * 保证 drawImage 不会读到图像边界外（部分浏览器会画出透明边）。
 */
export function mapCropToSource(crop: Rect, disp: Size, nat: Size): SourceRect {
  if (disp.w <= 0 || disp.h <= 0) {
    return { sx: 0, sy: 0, sw: 0, sh: 0 };
  }
  const ratioX = nat.w / disp.w;
  const ratioY = nat.h / disp.h;
  const sx = clamp(crop.x * ratioX, 0, nat.w);
  const sy = clamp(crop.y * ratioY, 0, nat.h);
  const sw = clamp(crop.w * ratioX, 0, nat.w - sx);
  const sh = clamp(crop.h * ratioY, 0, nat.h - sy);
  return { sx, sy, sw, sh };
}

/**
 * 解析超采样倍率：跟随设备像素比，但封顶 MAX_EXPORT_SCALE，且不低于 1。
 * DPR 为 0 / NaN / undefined（非浏览器环境或异常值）时安全回退到 1。
 */
export function resolveExportScale(dpr: number | undefined, maxScale = MAX_EXPORT_SCALE): number {
  const safe = typeof dpr === 'number' && Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
  return Math.min(Math.max(safe, 1), maxScale);
}

/**
 * 计算完整导出方案：源矩形 + 输出尺寸 + 倍率 + 风险标记。
 * 这是 handleConfirm 的全部决策逻辑，DOM 侧只负责照着执行。
 */
export function computeCropExportPlan(params: {
  crop: Rect;
  disp: Size;
  nat: Size;
  dpr?: number;
  maxScale?: number;
  maxOutputPixels?: number;
  targetDisplayCssPx?: number; // Bug 7: 目标显示尺寸
}): CropExportPlan {
  const {
    crop,
    disp,
    nat,
    dpr,
    maxScale = MAX_EXPORT_SCALE,
    maxOutputPixels = MAX_OUTPUT_PIXELS,
    targetDisplayCssPx,
  } = params;

  const source = mapCropToSource(crop, disp, nat);
  const { sw, sh } = source;

  if (sw < MIN_SOURCE_PX || sh < MIN_SOURCE_PX) {
    return {
      source,
      outWidth: 0,
      outHeight: 0,
      exportScale: 1,
      downscaledForLimit: false,
      lowResSource: true,
      status: 'too-small',
      pixelRatio: 0,
    };
  }

  const requested = resolveExportScale(dpr, maxScale);

  // 面积兜底：若 requested 倍率下超过 canvas 上限，按 sqrt 比例回退。
  // 允许回退到 <1（即缩小输出），因为"能出图但略缩"远好于"空白图"。
  let exportScale = requested;
  const requestedPixels = sw * requested * sh * requested;
  let downscaledForLimit = false;
  if (requestedPixels > maxOutputPixels) {
    exportScale = Math.sqrt(maxOutputPixels / (sw * sh));
    downscaledForLimit = true;
  }

  // 取整方向很关键：四舍五入可能让面积反超上限（实测 4730×3547 = 16,777,310
  // > 16,777,216，只差 1 个像素也足以让 Safari 吐出空白图）。超限时改用 floor。
  let outWidth = Math.max(1, Math.round(sw * exportScale));
  let outHeight = Math.max(1, Math.round(sh * exportScale));
  if (outWidth * outHeight > maxOutputPixels) {
    outWidth = Math.max(1, Math.floor(sw * exportScale));
    outHeight = Math.max(1, Math.floor(sh * exportScale));
  }

  // Bug 7: 基于目标显示尺寸计算像素比
  let pixelRatio = Infinity;
  let lowResSource = false;

  if (targetDisplayCssPx && targetDisplayCssPx > 0) {
    const safeDpr = typeof dpr === 'number' && Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
    const targetPhysicalPx = targetDisplayCssPx * safeDpr;
    pixelRatio = outWidth / targetPhysicalPx;
    lowResSource = pixelRatio < LOW_RES_RATIO_THRESHOLD;
  } else {
    // 兜底：使用旧逻辑（绝对像素数判断）
    lowResSource = sw < 200 || sh < 200;
    pixelRatio = Math.min(sw, sh) / 200;
  }

  return {
    source,
    outWidth,
    outHeight,
    exportScale,
    downscaledForLimit,
    lowResSource,
    status: 'ok',
    pixelRatio,
  };
}

export interface SharpnessVerdict {
  /** 位图像素是否足以铺满目标物理像素（>= 1 即不需要插值放大）。 */
  sharp: boolean;
  /** 位图像素 / 目标物理像素。<1 表示会被拉伸，值越小越糊。 */
  ratio: number;
  /** 目标显示所需的物理像素数（CSS px × DPR）。 */
  requiredPhysicalPx: number;
}

/**
 * 判定一张 outPx 宽的位图，在 displayCssPx 宽的容器里、DPR=dpr 的屏幕上
 * 是否会被插值放大（即"会不会糊"）。
 *
 * 这是把「不糊」这件事从主观感受变成可断言不变量的关键函数：
 * CI 里可以直接钉死 —— 给定原图与显示尺寸，导出方案必须 sharp。
 */
export function assessDisplaySharpness(
  outPx: number,
  displayCssPx: number,
  dpr = 1,
): SharpnessVerdict {
  const safeDpr = typeof dpr === 'number' && Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
  const requiredPhysicalPx = Math.max(1, displayCssPx * safeDpr);
  const ratio = outPx / requiredPhysicalPx;
  return { sharp: ratio >= 1, ratio, requiredPhysicalPx };
}
