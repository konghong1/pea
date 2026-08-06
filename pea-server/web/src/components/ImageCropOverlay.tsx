import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Dropdown } from 'antd';
import { toast } from '../store/toast';

export type CropRatio = 'original' | '1:1' | '4:3' | '3:4' | '16:9' | '9:16' | '21:9' | 'custom';

type Rect = { x: number; y: number; w: number; h: number };
type Disp = { w: number; h: number; scale: number };

interface Props {
  url: string;
  onClose: () => void;
  onConfirm: (dataUrl: string, size: { width: number; height: number }) => void;
}

const RATIO_LABELS: Record<CropRatio, string> = {
  original: '原图比例',
  '1:1': '1 : 1',
  '4:3': '4 : 3',
  '3:4': '3 : 4',
  '16:9': '16 : 9',
  '9:16': '9 : 16',
  '21:9': '21 : 9',
  custom: '自定义…',
};

const RATIO_VALUES: Record<CropRatio, number | null> = {
  original: null,
  '1:1': 1,
  '4:3': 4 / 3,
  '3:4': 3 / 4,
  '16:9': 16 / 9,
  '9:16': 9 / 16,
  '21:9': 21 / 9,
  custom: null,
};

const MIN_CROP = 32;
const INSET = 0.10;

/** 计算图片在视口中的显示尺寸：等比 contain 到 (0.84vw, 0.72vh) 区域内。
 *  显示矩形与图片原图严格同比例（scale 均匀），因此裁剪坐标可按 scale 直接映射回原图。 */
function fitDisplay(natW: number, natH: number): Disp {
  const maxW = Math.min(window.innerWidth * 0.84, 1100);
  const maxH = window.innerHeight * 0.72;
  const scale = Math.min(maxW / natW, maxH / natH);
  return { w: Math.round(natW * scale), h: Math.round(natH * scale), scale };
}

/** 计算裁剪框初始位置和尺寸。
 *  - ratio=null（自由模式）：留 INSET 边距，居中显示
 *  - ratio!=null（锁定比例）：contain 到图片全尺寸，占满宽度或高度（取较小溢出方向）
 */
function centerFitRect(W: number, H: number, ratio: number | null) {
  if (ratio != null) {
    // 比例模式：裁剪框尽可能大，contain 在图片边界内，占满一边
    const byWidth = { w: W, h: W / ratio };   // 以宽为准
    const byHeight = { w: H * ratio, h: H };   // 以高为准
    // 选那个能完整放进图片的方案
    const use = byWidth.h <= H ? byWidth : byHeight;
    return { x: (W - use.w) / 2, y: (H - use.h) / 2, w: use.w, h: use.h };
  }
  // 自由模式：留 10% 边距
  const inset = 1 - INSET * 2; // 0.8
  let w = clamp(W * inset, MIN_CROP, W);
  let h = clamp(H * inset, MIN_CROP, H);
  return { x: (W - w) / 2, y: (H - h) / 2, w, h };
}

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => {
      fetch(url, { mode: 'cors' })
        .then((r) => {
          if (!r.ok) throw new Error('fetch failed');
          return r.blob();
        })
        .then((blob) => {
          const objectUrl = URL.createObjectURL(blob);
          const img2 = new Image();
          img2.onload = () => resolve(img2);
          img2.onerror = () => reject(new Error('load failed'));
          img2.src = objectUrl;
        })
        .catch(() => reject(new Error('load failed')));
    };
    img.src = url;
  });
}

/** 将裁剪 Rect 同步到 DOM 节点的 style（拖动期间使用，绕过 React 重渲染） */
function syncDomStyles(
  rect: Rect,
  W: number,
  H: number,
  frameEl: HTMLDivElement | null,
  masks: { top: HTMLDivElement | null; bottom: HTMLDivElement | null; left: HTMLDivElement | null; right: HTMLDivElement | null },
) {
  if (frameEl) {
    frameEl.style.left = `${rect.x}px`;
    frameEl.style.top = `${rect.y}px`;
    frameEl.style.width = `${rect.w}px`;
    frameEl.style.height = `${rect.h}px`;
  }
  if (masks.top) masks.top.style.height = `${rect.y}px`;
  if (masks.bottom) masks.bottom.style.height = `${H - rect.y - rect.h}px`;
  if (masks.left) {
    masks.left.style.width = `${rect.x}px`;
    masks.left.style.top = `${rect.y}px`;
    masks.left.style.height = `${rect.h}px`;
  }
  if (masks.right) {
    masks.right.style.width = `${W - rect.x - rect.w}px`;
    masks.right.style.top = `${rect.y}px`;
    masks.right.style.height = `${rect.h}px`;
  }
}

export default function ImageCropOverlay({ url, onClose, onConfirm }: Props) {
  const [disp, setDisp] = useState<Disp | null>(null);
  const [crop, setCrop] = useState<Rect | null>(null);
  const [ratioKey, setRatioKey] = useState<CropRatio>('original');
  const [customRatio, setCustomRatio] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const naturalRef = useRef<{ w: number; h: number } | null>(null);
  const dispRef = useRef<Disp | null>(null);

  // ── DOM refs：拖动期间直接操作 style，绕过 React 重渲染 ──
  const frameRef = useRef<HTMLDivElement | null>(null);
  const maskTopRef = useRef<HTMLDivElement | null>(null);
  const maskBottomRef = useRef<HTMLDivElement | null>(null);
  const maskLeftRef = useRef<HTMLDivElement | null>(null);
  const maskRightRef = useRef<HTMLDivElement | null>(null);
  // 拖动标记：拖动期间跳过 React 渲染的 DOM 同步（避免闪回）
  const draggingRef = useRef(false);

  const W = disp?.w ?? 0;
  const H = disp?.h ?? 0;

  const ratioValue = useMemo(() => {
    if (ratioKey === 'custom') return customRatio;
    return RATIO_VALUES[ratioKey];
  }, [ratioKey, customRatio]);

  // 加载图片 → 计算显示尺寸 → 初始化裁剪框
  useEffect(() => {
    let alive = true;
    loadImage(url)
      .then((img) => {
        if (!alive) return;
        const nat = { w: img.naturalWidth, h: img.naturalHeight };
        naturalRef.current = nat;
        const d = fitDisplay(nat.w, nat.h);
        dispRef.current = d;
        setDisp(d);
      })
      .catch(() => {
        toast.error('图片加载失败，无法裁剪');
        onClose();
      });
    return () => { alive = false; };
  }, [url, onClose]);

  // 显示尺寸就绪后，默认展示「图片 + 居中的裁剪框」
  useEffect(() => {
    if (!disp || crop) return;
    setCrop(centerFitRect(disp.w, disp.h, ratioValue));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disp, ratioValue]);

  // 窗口缩放：等比重算显示尺寸，并同步缩放当前裁剪框，避免坐标错位
  const onResize = useCallback(() => {
    const nat = naturalRef.current;
    if (!nat) return;
    const next = fitDisplay(nat.w, nat.h);
    const prev = dispRef.current;
    dispRef.current = next;
    setDisp(next);
    if (prev && prev.w > 0 && prev.h > 0) {
      const rx = next.w / prev.w;
      const ry = next.h / prev.h;
      setCrop((c) => (c ? { x: c.x * rx, y: c.y * ry, w: c.w * rx, h: c.h * ry } : c));
    }
  }, []);

  useLayoutEffect(() => {
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [onResize]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const applyRatio = (r: CropRatio) => {
    if (!crop || !W || !H) return;
    if (r === 'custom') {
      const raw = window.prompt('请输入自定义宽高比，例如 2:1 或 1.85:1', customRatio ? formatRatio(customRatio) : '');
      if (raw == null) return;
      const parsed = parseRatio(raw);
      if (parsed == null || parsed <= 0) {
        toast.error('宽高比格式错误');
        return;
      }
      setCustomRatio(parsed);
      setRatioKey('custom');
      setCrop(centerFitRect(W, H, parsed));
      return;
    }
    setRatioKey(r);
    setCrop(centerFitRect(W, H, RATIO_VALUES[r]));
  };

  // ── 拖动核心：直接操作 DOM，绕过 React 重渲染实现 60fps 丝滑体验 ──
  const startDrag = (type: 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w', e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!crop) return;

    const startRect = { ...crop };
    const startX = e.clientX;
    const startY = e.clientY;

    draggingRef.current = true;

    const masks = {
      top: maskTopRef.current,
      bottom: maskBottomRef.current,
      left: maskLeftRef.current,
      right: maskRightRef.current,
    };

    const move = (ev: PointerEvent) => {
      if (!draggingRef.current) return;
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      const next = updateCrop(type, startRect, dx, dy, W, H, ratioValue);
      // 直接写 DOM → 跳过 React 调度管线 → 无闪动
      syncDomStyles(next, W, H, frameRef.current, masks);
    };

    const up = () => {
      draggingRef.current = false;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      // 松手后才同步到 React state → 触发一次性重渲染
      if (!crop) return;
      // 从 DOM 读取最终位置（更准确，避免闭包陈旧）
      const f = frameRef.current;
      if (f) {
        const rect = f.getBoundingClientRect();
        const parent = f.parentElement?.getBoundingClientRect();
        if (parent) {
          const finalX = rect.left - parent.left;
          const finalY = rect.top - parent.top;
          setCrop({ x: finalX, y: finalY, w: rect.width, h: rect.height });
          return;
        }
      }
      // fallback：用最后一次计算的值
      // 注意：这里用不到最新的 dx/dy，所以直接保持当前 crop 即可
      // （因为 DOM 已经被直接更新了，React state 需要同步）
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const handleConfirm = async () => {
    if (!crop || !disp || !naturalRef.current) return;
    setLoading(true);
    try {
      const img = await loadImage(url);
      const { scale } = disp;
      let sx = crop.x / scale;
      let sy = crop.y / scale;
      let sw = crop.w / scale;
      let sh = crop.h / scale;
      const nat = naturalRef.current;
      sx = clamp(sx, 0, nat.w);
      sy = clamp(sy, 0, nat.h);
      sw = clamp(sw, 0, nat.w - sx);
      sh = clamp(sh, 0, nat.h - sy);
      if (sw < 1 || sh < 1) {
        toast.error('裁剪区域过小');
        return;
      }
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(sw));
      canvas.height = Math.max(1, Math.round(sh));
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('canvas context');
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
      onConfirm(canvas.toDataURL('image/png'), { width: canvas.width, height: canvas.height });
    } catch {
      toast.error('裁剪失败');
    } finally {
      setLoading(false);
    }
  };

  const dropdownItems = (Object.keys(RATIO_LABELS) as CropRatio[]).map((key) => ({
    key,
    label: RATIO_LABELS[key],
    onClick: () => applyRatio(key),
  }));

  const ratioLabel = ratioKey === 'custom' && customRatio ? formatRatio(customRatio) : RATIO_LABELS[ratioKey];

  const stop = (e: React.MouseEvent) => e.stopPropagation();

  const isReady = W > 0 && H > 0 && crop != null;

  return createPortal(
    <div className="pea-crop-overlay" role="dialog" aria-label="图片裁剪">
      {/* 全屏遮罩：盖住整个画布，只展示图片本身（节点边框/连接点/徽章全部被遮住） */}
      <div className="pea-crop-backdrop" onClick={onClose} aria-hidden />

      {/* 居中舞台：图片在上，功能条在下（独立 bar，不压在裁剪框内） */}
      <div className="pea-crop-stage" onClick={stop}>
        {!isReady ? (
          <div className="pea-crop-loading">
            <span className="pea-crop-loading-text">准备裁剪…</span>
          </div>
        ) : (
          <>
            <div className="pea-crop-image-stage" style={{ width: W, height: H }}>
              {/* 图片 + 遮罩裁剪在内部，避免描边/把手被裁切 */}
              <div className="pea-crop-img-clip">
                <img className="pea-crop-image" src={url} alt="裁剪图片" draggable={false} />
                <div ref={maskTopRef} className="pea-crop-mask pea-crop-mask-top" style={{ top: 0, left: 0, right: 0, height: crop.y }} />
                <div ref={maskBottomRef} className="pea-crop-mask pea-crop-mask-bottom" style={{ bottom: 0, left: 0, right: 0, height: H - crop.y - crop.h }} />
                <div ref={maskLeftRef} className="pea-crop-mask pea-crop-mask-left" style={{ top: crop.y, left: 0, width: crop.x, height: crop.h }} />
                <div ref={maskRightRef} className="pea-crop-mask pea-crop-mask-right" style={{ top: crop.y, right: 0, width: W - crop.x - crop.w, height: crop.h }} />
              </div>

              {/* 裁剪框：可拖动，四角可自由缩放（与图片同级，把手不被裁切） */}
              <div
                ref={frameRef}
                className="pea-crop-frame"
                style={{ left: crop.x, top: crop.y, width: crop.w, height: crop.h }}
                onPointerDown={(e) => startDrag('move', e)}
                role="button"
                aria-label="拖动裁剪区"
                tabIndex={0}
              >
                {(['nw', 'ne', 'sw', 'se'] as const).map((h) => (
                  <span
                    key={h}
                    className={`pea-crop-handle ${h}`}
                    onPointerDown={(e) => startDrag(h, e)}
                    role="button"
                    aria-label={`调整 ${h}`}
                    tabIndex={-1}
                  />
                ))}
                {/* 四边中点拖拽把手 */}
                {(['n', 's', 'e', 'w'] as const).map((h) => (
                  <span
                    key={h}
                    className={`pea-crop-handle edge ${h}`}
                    onPointerDown={(e) => startDrag(h, e)}
                    role="button"
                    aria-label={`调整 ${h} 边`}
                    tabIndex={-1}
                  />
                ))}
              </div>
            </div>

            {/* 裁剪功能条：图片正下方的独立 bar */}
            <div className="pea-crop-toolbar" onClick={stop}>
              <button type="button" className="pea-crop-toolbar-btn" onClick={onClose} aria-label="取消裁剪" title="取消">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M18 6L6 18" />
                  <path d="M6 6l12 12" />
                </svg>
              </button>
              <div className="pea-crop-toolbar-sep" />
              <Dropdown menu={{ items: dropdownItems }} placement="top" arrow overlayClassName="pea-crop-dropdown">
                <button type="button" className="pea-crop-toolbar-btn pea-crop-ratio-btn" aria-label="选择裁剪比例" title="裁剪比例">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <path d="M3 9h18" />
                    <path d="M9 21V9" />
                  </svg>
                  <span className="pea-crop-ratio-label">{ratioLabel}</span>
                </button>
              </Dropdown>
              <div className="pea-crop-toolbar-sep" />
              <button
                type="button"
                className="pea-crop-toolbar-btn pea-crop-confirm"
                onClick={handleConfirm}
                disabled={loading}
                aria-label="确认裁剪"
                title="确认裁剪"
              >
                {loading ? (
                  <span className="pea-crop-spinner" aria-hidden />
                ) : (
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                )}
                <span className="pea-crop-confirm-text">确认裁剪</span>
              </button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}

/* ──── 裁剪框拖拽/缩放逻辑 ──── */
function updateCrop(
  type: 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w',
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

  const next: Rect = { ...start };
  const free = ratio == null;

  // 自由模式：每条边/角独立移动
  if (free) {
    switch (type) {
      case 'n':
        next.y = clamp(start.y + dy, 0, start.y + start.h - MIN_CROP);
        next.h = start.h + start.y - next.y;
        break;
      case 's':
        next.h = clamp(start.h + dy, MIN_CROP, H - start.y);
        break;
      case 'w':
        next.x = clamp(start.x + dx, 0, start.x + start.w - MIN_CROP);
        next.w = start.w + start.x - next.x;
        break;
      case 'e':
        next.w = clamp(start.w + dx, MIN_CROP, W - start.x);
        break;
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

  // 锁定比例模式
  // 边拖拽（n/s/e/w）：以该边方向为主轴，等比调整
  // 角拖拽（nw/ne/sw/se）：以水平拖动为准，等比调整宽高
  let w = start.w;
  switch (type) {
    case 'n':
    case 'nw':
    case 'sw':
      w = clamp(start.w - dx, MIN_CROP, Math.min(start.x + start.w, W));
      break;
    case 's':
    case 'ne':
    case 'se':
      w = clamp(start.w + dx, MIN_CROP, W - start.x);
      break;
    case 'e':
      w = clamp(start.w + dx, MIN_CROP, W - start.x);
      break;
    case 'w':
      w = clamp(start.w - dx, MIN_CROP, Math.min(start.x + start.w, W));
      break;
  }
  let h = w / ratio;

  if (h > H) {
    h = H;
    w = h * ratio;
  }

  switch (type) {
    case 'nw':
      next.x = start.x + start.w - w;
      next.y = start.y + start.h - h;
      break;
    case 'n':
    case 'ne':
      next.y = start.y + start.h - h;
      break;
    case 'w':
    case 'sw':
      next.x = start.x + start.w - w;
      break;
    case 's':
    case 'e':
    case 'se':
      break;
  }
  next.w = w;
  next.h = h;

  next.x = clamp(next.x, 0, W - MIN_CROP);
  next.y = clamp(next.y, 0, H - MIN_CROP);
  next.w = clamp(next.w, MIN_CROP, W - next.x);
  next.h = clamp(next.h, MIN_CROP, H - next.y);
  return next;
}

function formatRatio(n: number) {
  if (Math.abs(n - Math.round(n)) < 0.001) return `${Math.round(n)}:1`;
  return `${n.toFixed(2)}:1`;
}

function parseRatio(raw: string): number | null {
  const s = raw.replace(/\s+/g, '');
  const parts = s.split(':');
  if (parts.length === 2) {
    const w = parseFloat(parts[0]);
    const h = parseFloat(parts[1]);
    if (w > 0 && h > 0) return w / h;
  }
  const n = parseFloat(s);
  if (n > 0) return n;
  return null;
}
