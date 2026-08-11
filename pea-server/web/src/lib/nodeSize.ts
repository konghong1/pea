/**
 * 节点尺寸计算：所有节点按「最长边恒定 + 比例决定宽高」锁定框尺寸，
 * 避免内容加载后节点框跳动。本 helper 在 PeaNode 与 CanvasEditor 之间共享，
 * 保证聚焦/落点等逻辑与渲染完全一致。
 */

export const LONG_EDGE = 340;

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
  if (!w || !h) return { width: LONG_EDGE, height: LONG_EDGE };
  return w >= h
    ? { width: LONG_EDGE, height: Math.round(LONG_EDGE * (h / w)) }
    : { width: Math.round(LONG_EDGE * (w / h)), height: LONG_EDGE };
}

/** 把浮点宽高归约为最简整数比（如 1920×1080 → "16:9"）。 */
export function simplifyRatio(w: number, h: number) {
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
  const g = gcd(Math.round(w), Math.round(h));
  if (!g) return '1:1';
  return `${Math.round(w) / g}:${Math.round(h) / g}`;
}
