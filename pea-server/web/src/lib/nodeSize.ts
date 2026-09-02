/**
 * 节点尺寸计算：横屏时宽度恒 340px（height = 340 * h/w），竖屏时高度恒 340px（width = 340 * w/h）。
 * 保证不同比例在视觉上形成明显差异，一眼可辨。
 * 本 helper 在 PeaNode 与 CanvasEditor 之间共享，保证聚焦/落点等逻辑与渲染完全一致。
 */

export const FIXED_EDGE = 340;

export const KIND_DEFAULT_ASPECT: Record<string, string> = {
  image: '9:16',
  video: '16:9',
  audio: '16:9',
  text: '1:1',
  generate: '1:1',
  ref: '1:1',
  agent: '1:1',
  story: '1:1',
  world3d: '1:1',
  camera: '1:1',
  light: '1:1',
  playlist: '1:1',
  replace: '1:1',
  prompt: '1:1',
};

export function getNodeSize(aspectRatio?: string, kind?: string) {
  const ar = aspectRatio || (kind ? KIND_DEFAULT_ASPECT[kind] : undefined) || '1:1';
  const [w, h] = ar.split(':').map(Number);
  if (!w || !h) return { width: FIXED_EDGE, height: FIXED_EDGE };
  return w >= h
    ? { width: FIXED_EDGE, height: Math.round(FIXED_EDGE * (h / w)) }
    : { width: Math.round(FIXED_EDGE * (w / h)), height: FIXED_EDGE };
}

/** 把浮点宽高归约为最简整数比（如 1920×1080 → "16:9"）。 */
export function simplifyRatio(w: number, h: number) {
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
  const g = gcd(Math.round(w), Math.round(h));
  if (!g) return '1:1';
  return `${Math.round(w) / g}:${Math.round(h) / g}`;
}
