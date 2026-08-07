import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Dropdown } from 'antd';
import { toast } from '../store/toast';
import { updateCrop, clamp, MIN_CROP, type Rect, type CropDragType } from './cropMath';

export type CropRatio = 'original' | '1:1' | '4:3' | '3:4' | '16:9' | '9:16' | '21:9' | 'custom';

type Disp = { w: number; h: number; scale: number };

interface Props {
  url: string;
  containerRef: React.RefObject<HTMLDivElement | null>;
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

const RATIO_VALUES: Record<Exclude<CropRatio, 'original' | 'custom'>, number> = {
  '1:1': 1,
  '4:3': 4 / 3,
  '3:4': 3 / 4,
  '16:9': 16 / 9,
  '9:16': 9 / 16,
  '21:9': 21 / 9,
};

const INSET = 0.10;

/** Calculate crop image display size.
 *
 *  Core rule: crop image = the node's actual rendered pixel size on screen (×1.0).
 *  We read the container's getBoundingClientRect() to get the real pixel dimensions
 *  the user sees on canvas, then use that directly — no scaling, no viewport ratios.
 *  This means the crop image is ALWAYS the same size as the node the user clicked.
 *
 *  Safety: if container measurement fails, fall back to a reasonable default (400×300)
 *  and clamp to max 90% of viewport to prevent overflow in edge cases.
 */
function fitDisplay(natW: number, natH: number, containerEl: HTMLDivElement | null): Disp {
  const rect = containerEl?.getBoundingClientRect();
  const baseW = rect?.width ?? 400;
  const baseH = rect?.height ?? 300;

  // Use node's actual screen pixels as-is (×1.0 scale factor)
  // But clamp to 90% viewport as safety net for extreme cases
  const viewMaxW = window.innerWidth * 0.90;
  const viewMaxH = window.innerHeight * 0.90;
  const finalW = Math.min(baseW, viewMaxW);
  const finalH = Math.min(baseH, viewMaxH);

  // Scale must map display pixels back to original image coordinates
  const scale = Math.min(finalW / natW, finalH / natH);
  return { w: Math.round(finalW), h: Math.round(finalH), scale };
}

/** Calculate initial crop rectangle position and size. */
function centerFitRect(W: number, H: number, ratio: number | null) {
  if (ratio != null) {
    const byWidth = { w: W, h: W / ratio };
    const byHeight = { w: H * ratio, h: H };
    const use = byWidth.h <= H ? byWidth : byHeight;
    return { x: (W - use.w) / 2, y: (H - use.h) / 2, w: use.w, h: use.h };
  }
  const inset = 1 - INSET * 2;
  let w = clamp(W * inset, MIN_CROP, W);
  let h = clamp(H * inset, MIN_CROP, H);
  return { x: (W - w) / 2, y: (H - h) / 2, w, h };
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

/** Sync crop Rect to DOM node styles (used during drag to bypass React re-render) */
function syncDomStyles(
  rect: Rect,
  W: number,
  H: number,
  frameEl: HTMLDivElement | null,
  masks: { top: HTMLDivElement | null; bottom: HTMLDivElement | null; left: HTMLDivElement | null; right: HTMLDivElement | null },
) {
  if (frameEl) {
    frameEl.style.transform = `translate3d(${rect.x}px, ${rect.y}px, 0)`;
    frameEl.style.width = `${rect.w}px`;
    frameEl.style.height = `${rect.h}px`;
  }
  if (masks.top) masks.top.style.transform = `scale(1, ${rect.y / H})`;
  if (masks.bottom) masks.bottom.style.transform = `translate(0px, ${rect.y + rect.h}px) scale(1, ${(H - rect.y - rect.h) / H})`;
  if (masks.left) masks.left.style.transform = `scale(${rect.x / W}, 1)`;
  if (masks.right) masks.right.style.transform = `translate(${rect.x + rect.w}px, 0) scale(${(W - rect.x - rect.w) / W}, 1)`;
}

/** In-place image crop overlay component.
 *
 *  Design points:
 *  - No createPortal — renders directly inside the node's image container (position:absolute fills parent)
 *  - No full-screen darkening mask — canvas content completely unaffected
 *  - Image centered and enlarged in container, with its own dark background card
 *  - Four-side semi-transparent darkening mask outside crop area (pea-crop-mask)
 *  - Toolbar right below the image
 *  - Single-layer structure: overlay > stage > [image-stage + toolbar]
 */
export default function ImageCropOverlay({ url, containerRef, onClose, onConfirm }: Props) {
  const [disp, setDisp] = useState<Disp | null>(null);
  const [crop, setCrop] = useState<Rect | null>(null);
  const [ratioKey, setRatioKey] = useState<CropRatio>('original');
  const [customRatio, setCustomRatio] = useState<number | null>(null);
  const [originalRatio, setOriginalRatio] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const naturalRef = useRef<{ w: number; h: number } | null>(null);
  const dispRef = useRef<Disp | null>(null);

  // DOM refs for direct style manipulation during drag
  const frameRef = useRef<HTMLDivElement | null>(null);
  const maskTopRef = useRef<HTMLDivElement | null>(null);
  const maskBottomRef = useRef<HTMLDivElement | null>(null);
  const maskLeftRef = useRef<HTMLDivElement | null>(null);
  const maskRightRef = useRef<HTMLDivElement | null>(null);

  const W = disp?.w ?? 0;
  const H = disp?.h ?? 0;

  const ratioValue = useMemo(() => {
    if (ratioKey === 'custom') return customRatio;
    if (ratioKey === 'original') return originalRatio;
    return RATIO_VALUES[ratioKey];
  }, [ratioKey, customRatio, originalRatio]);

  // Load image → measure container via getBoundingClientRect → calc display size → init crop rect
  useEffect(() => {
    let alive = true;
    loadImage(url)
      .then((img) => {
        if (!alive) return;
        const nat = { w: img.naturalWidth, h: img.naturalHeight };
        naturalRef.current = nat;
        setOriginalRatio(nat.w / nat.h);

        const d = fitDisplay(nat.w, nat.h, containerRef.current);
        dispRef.current = d;
        setDisp(d);
      })
      .catch(() => {
        toast.error('图片加载失败，无法裁剪');
        onClose();
      });
    return () => { alive = false; };
  }, [url, onClose, containerRef]);

  // Init crop rect once display size is ready
  useEffect(() => {
    if (!disp || crop) return;
    setCrop(centerFitRect(disp.w, disp.h, null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disp]);

  // Window resize: recalc display size and sync crop rect
  const onResize = useCallback(() => {
    const nat = naturalRef.current;
    if (!nat) return;
    const next = fitDisplay(nat.w, nat.h, containerRef.current);
    const prev = dispRef.current;
    dispRef.current = next;
    setDisp(next);
    if (prev && prev.w > 0 && prev.h > 0) {
      const rx = next.w / prev.w;
      const ry = next.h / prev.h;
      setCrop((c) => (c ? { x: c.x * rx, y: c.y * ry, w: c.w * rx, h: c.h * ry } : c));
    }
  }, [containerRef]);

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
    if (r === 'original') {
      setRatioKey('original');
      setCrop({ x: 0, y: 0, w: W, h: H });
      return;
    }
    if (r === 'custom') {
      setRatioKey('custom');
      const nextCustom = customRatio ?? clamp(crop.w / crop.h, 0.01, 100);
      setCustomRatio(nextCustom);
      setCrop(centerFitRect(W, H, nextCustom));
      return;
    }
    setRatioKey(r);
    setCrop(centerFitRect(W, H, RATIO_VALUES[r]));
  };

  const applyCustomSize = (wVal: number, hVal: number) => {
    if (!W || !H) return;
    if (wVal <= 0 || hVal <= 0) {
      toast.error('宽高必须大于 0');
      return;
    }
    const r = wVal / hVal;
    setCustomRatio(r);
    setRatioKey('custom');
    setCrop(centerFitRect(W, H, r));
  };

  // Drag core: direct DOM manipulation + rAF merge + pointer capture for stable 60fps
  const startDrag = (type: CropDragType, e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!crop) return;

    const startRect = { ...crop };
    const startX = e.clientX;
    const startY = e.clientY;
    const target = e.currentTarget as HTMLElement;

    try { target.setPointerCapture(e.pointerId); } catch { /* noop */ }
    setIsDragging(true);

    const frameEl = frameRef.current;
    const masks = {
      top: maskTopRef.current,
      bottom: maskBottomRef.current,
      left: maskLeftRef.current,
      right: maskRightRef.current,
    };

    let latestX = startX;
    let latestY = startY;
    let rafId = 0;

    const apply = () => {
      rafId = 0;
      const dx = latestX - startX;
      const dy = latestY - startY;
      const next = updateCrop(type, startRect, dx, dy, W, H, ratioValue);
      syncDomStyles(next, W, H, frameEl, masks);
    };
    const schedule = () => {
      if (!rafId) rafId = requestAnimationFrame(apply);
    };

    const move = (ev: PointerEvent) => {
      latestX = ev.clientX;
      latestY = ev.clientY;
      schedule();
    };

    const up = () => {
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      try { target.releasePointerCapture(e.pointerId); } catch { /* noop */ }
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      const dx = latestX - startX;
      const dy = latestY - startY;
      const next = updateCrop(type, startRect, dx, dy, W, H, ratioValue);
      syncDomStyles(next, W, H, frameEl, masks);
      setIsDragging(false);
      setCrop(next);
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
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

  // Block wheel events from bubbling to canvas
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.stopPropagation();
    e.preventDefault();
  }, []);

  // Render: in-place overlay, single layer
  return (
    <div className="pea-crop-overlay" role="dialog" aria-label="图片裁剪" onWheel={onWheel}>
      {/* Centered stage: dark card wrapping image + toolbar */}
      <div className="pea-crop-stage" onClick={stop} onWheel={onWheel}>
        {!isReady ? (
          <div className="pea-crop-loading">
            <span className="pea-crop-loading-text">准备裁剪…</span>
          </div>
        ) : (
          <>
            <div className="pea-crop-image-stage" style={{ width: W, height: H }}>
              {/* Image + four-side masking */}
              <div className="pea-crop-img-clip">
                <img className="pea-crop-image" src={url} alt="裁剪图片" draggable={false} />
                <div ref={maskTopRef} className="pea-crop-mask" style={{ transform: `scale(1, ${crop.y / H})` }} />
                <div ref={maskBottomRef} className="pea-crop-mask" style={{ transform: `translate(0px, ${crop.y + crop.h}px) scale(1, ${(H - crop.y - crop.h) / H})` }} />
                <div ref={maskLeftRef} className="pea-crop-mask" style={{ transform: `scale(${crop.x / W}, 1)` }} />
                <div ref={maskRightRef} className="pea-crop-mask" style={{ transform: `translate(${crop.x + crop.w}px, 0) scale(${(W - crop.x - crop.w) / W}, 1)` }} />
              </div>

              {/* Crop frame */}
              <div
                ref={frameRef}
                className={`pea-crop-frame${isDragging ? ' pea-crop-frame--dragging' : ''}`}
                style={{ transform: `translate3d(${crop.x}px, ${crop.y}px, 0)`, left: 0, top: 0, width: crop.w, height: crop.h }}
                onPointerDown={(e) => startDrag('move', e)}
                role="button"
                aria-label="拖动裁切区"
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

            {/* Toolbar */}
            <div className="pea-crop-toolbar" onClick={stop}>
              <button type="button" className="pea-crop-toolbar-btn" onClick={onClose} aria-label="取消裁剪" title="取消">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M18 6L6 18" />
                  <path d="M 6 6l12 12" />
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
              {ratioKey === 'custom' && <CustomRatioInput current={customRatio} onApply={applyCustomSize} />}
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
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * Custom ratio input
 * ═════════════════════════════════════════════════════════════════════════════ */
function CustomRatioInput({
  current,
  onApply,
}: {
  current: number | null;
  onApply: (w: number, h: number) => void;
}) {
  const wRef = useRef<HTMLInputElement | null>(null);
  const [wDraft, setWDraft] = useState(() => (current ? String(Math.round(current * 1000) / 1000) : '1'));
  const [hDraft, setHDraft] = useState('1');

  useEffect(() => {
    if (current) {
      setWDraft(String(Math.round(current * 1000) / 1000));
    }
  }, [current]);

  const commit = () => {
    const w = parseFloat(wDraft);
    const h = parseFloat(hDraft);
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
      onApply(w, h);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commit();
      wRef.current?.blur();
    }
  };

  return (
    <div className="pea-crop-custom-ratio" onClick={(e) => e.stopPropagation()}>
      <input
        ref={wRef}
        type="number"
        min="0.01"
        step="0.1"
        value={wDraft}
        onChange={(e) => setWDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        placeholder="宽"
        aria-label="自定义宽"
        className="pea-crop-custom-input"
      />
      <span className="pea-crop-custom-colon">:</span>
      <input
        type="number"
        min="0.01"
        step="0.1"
        value={hDraft}
        onChange={(e) => setHDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        placeholder="高"
        aria-label="自定义高"
        className="pea-crop-custom-input"
      />
    </div>
  );
}

/* Crop math extracted to ./cropHash (pure functions, testable). This component handles only DOM/interaction. */

function formatRatio(n: number) {
  if (Math.abs(n - Math.round(n)) < 0.001) return `${Math.round(n)}:1`;
  return `${n.toFixed(2)}:1`;
}
