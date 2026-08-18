import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Dropdown } from 'antd';
import { toast } from '../store/toast';
import { updateCrop, clamp, MIN_CROP, type Rect, type CropDragType } from './cropMath';
import { resolveDragType } from '../lib/cropDrag';
import { computeCropExportPlan } from './cropExport';

export type CropRatio = 'original' | '1:1' | '4:3' | '3:4' | '16:9' | '9:16' | '21:9' | 'custom';

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

/**
 * 测量图片容器的「布局尺寸」（未经 ReactFlow viewport scale 放大的原始像素）。
 *
 * 关键：裁切浮层渲染在节点内部，会被 ReactFlow 的 `transform: scale(zoom)` 一起缩放。
 * 因此舞台尺寸只需写成容器的 layout 尺寸（offsetWidth/offsetHeight），渲染后自然与节点
 * 图片视觉等大 —— 完全不需要手动 ÷zoom，也避免了 store zoom 与真实缩放不同步导致的
 * 「裁切图被二次放大 / 与节点不一致」问题。
 *
 * 节点图片容器已被 CSS 锁定为「图片原始比例」，故裁切图用 object-fit: contain 可完整铺满，
 * 与节点 cover 图在比例一致时视觉完全一致。
 */
function measureStage(containerEl: HTMLDivElement | null): { w: number; h: number } | null {
  if (!containerEl) return null;
  const w = containerEl.offsetWidth;
  const h = containerEl.offsetHeight;
  if (w <= 0 || h <= 0) return null;
  return { w, h };
}

/** Initial crop rectangle: preserve image ratio with a small inset so the frame
 *  does not hug the image edges on first open. */
function initialCropRect(W: number, H: number, ratio: number | null) {
  const inset = 1 - INSET * 2; // 80% of the display area
  if (ratio == null) {
    const w = clamp(W * inset, MIN_CROP, W);
    const h = clamp(H * inset, MIN_CROP, H);
    return { x: (W - w) / 2, y: (H - h) / 2, w, h };
  }
  let w = W * inset;
  let h = w / ratio;
  if (h > H * inset) {
    h = H * inset;
    w = h * ratio;
  }
  return { x: (W - w) / 2, y: (H - h) / 2, w: clamp(w, MIN_CROP, W), h: clamp(h, MIN_CROP, H) };
}

/** 居中按比例的裁切框（比例锁定时用） */
function centerFitRect(W: number, H: number, ratio: number): Rect {
  const byWidth = { w: W, h: W / ratio };
  const byHeight = { w: H * ratio, h: H };
  const use = byWidth.h <= H ? byWidth : byHeight;
  return { x: (W - use.w) / 2, y: (H - use.h) / 2, w: use.w, h: use.h };
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
function syncDomStyles(rect: Rect, frameEl: HTMLDivElement | null) {
  if (frameEl) {
    frameEl.style.transform = `translate3d(${rect.x}px, ${rect.y}px, 0)`;
    frameEl.style.width = `${rect.w}px`;
    frameEl.style.height = `${rect.h}px`;
  }
}

export default function ImageCropOverlay({ url, containerRef, onClose, onConfirm }: Props) {
  const [disp, setDisp] = useState<{ w: number; h: number } | null>(null);
  const [crop, setCrop] = useState<Rect | null>(null);
  const [ratioKey, setRatioKey] = useState<CropRatio>('original');
  const [customRatio, setCustomRatio] = useState<number | null>(null);
  const [originalRatio, setOriginalRatio] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const naturalRef = useRef<{ w: number; h: number } | null>(null);
  const dispRef = useRef<{ w: number; h: number } | null>(null);

  const frameRef = useRef<HTMLDivElement | null>(null);

  const W = disp?.w ?? 0;
  const H = disp?.h ?? 0;

  const ratioValue = useMemo(() => {
    if (ratioKey === 'custom') return customRatio;
    if (ratioKey === 'original') return originalRatio;
    return RATIO_VALUES[ratioKey];
  }, [ratioKey, customRatio, originalRatio]);

  // ── Lock canvas while crop overlay is open ────────────────────────────────
  useEffect(() => {
    try {
      window.dispatchEvent(new CustomEvent('crop-mode-change', { detail: { active: true } }));
    } catch { /* noop */ }
    return () => {
      try {
        window.dispatchEvent(new CustomEvent('crop-mode-change', { detail: { active: false } }));
      } catch { /* noop */ }
    };
  }, []);

  // Load image → measure container layout size → init crop rect
  useEffect(() => {
    let alive = true;
    loadImage(url)
      .then((img) => {
        if (!alive) return;
        const nat = { w: img.naturalWidth, h: img.naturalHeight };
        naturalRef.current = nat;
        setOriginalRatio(nat.w / nat.h);

        const measured = measureStage(containerRef.current);
        if (!measured) {
          toast.error('无法获取图片容器尺寸');
          onClose();
          return;
        }
        dispRef.current = measured;
        setDisp(measured);
      })
      .catch(() => {
        toast.error('图片加载失败，无法裁剪');
        onClose();
      });
    return () => { alive = false; };
  }, [url, onClose, containerRef]);

  // Init crop rect once display size is ready.
  useEffect(() => {
    if (!disp || crop) return;
    setCrop(initialCropRect(disp.w, disp.h, originalRatio ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disp, originalRatio]);

  // Window resize: re-measure stage and rescale crop proportionally.
  const onResize = useCallback(() => {
    const nat = naturalRef.current;
    if (!nat) return;
    const next = measureStage(containerRef.current);
    if (!next) return;
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

  // Close crop when clicking outside the overlay.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      if (
        target.closest('[data-cropping-overlay="true"]') ||
        target.closest('.pea-crop-dropdown') ||
        target.closest('.ant-dropdown-menu')
      ) {
        return;
      }
      onCloseRef.current();
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, []);

  const applyRatio = (r: CropRatio) => {
    if (!crop || !W || !H) return;
    if (r === 'original') {
      setRatioKey('original');
      setCrop(initialCropRect(W, H, originalRatio ?? null));
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

  // ── Drag core ────────────────────────────────────────────────────────────
  // 直接用 stage 的真实渲染矩形反算「屏幕 px → flow px」比例（不依赖 store zoom），
  // 任意画布缩放下都能稳定抓取；指针捕获落在真实按下元素上，move/边/角走同一管线。
  const startDrag = (type: CropDragType, e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!crop || !W || !H) return;

    const frameEl = frameRef.current;
    const stageEl = frameEl?.parentElement ?? null;
    if (!frameEl || !stageEl) return;

    const target = e.currentTarget as HTMLElement;
    try { target.setPointerCapture(e.pointerId); } catch { /* noop */ }
    setIsDragging(true);

    // 用 stageEl 自身的 offsetWidth/offsetHeight 计算「屏幕 px → flow px」比例，
    // 而非外部传入的 W/H，避免 containerRef 与 stageEl 尺寸不一致导致坐标转换错误。
    const stageRect = stageEl.getBoundingClientRect();
    const stageW = stageEl.offsetWidth || W;
    const stageH = stageEl.offsetHeight || H;
    const sx = stageRect.width / stageW || 1;
    const sy = stageRect.height / stageH || 1;

    const startRect = { ...crop };
    const startMouseFx = (e.clientX - stageRect.left) / sx;
    const startMouseFy = (e.clientY - stageRect.top) / sy;
    const grabX = startMouseFx - startRect.x;
    const grabY = startMouseFy - startRect.y;

    let latestX = e.clientX;
    let latestY = e.clientY;

    const compute = (clientX: number, clientY: number): Rect => {
      const curFx = (clientX - stageRect.left) / sx;
      const curFy = (clientY - stageRect.top) / sy;
      if (type === 'move') {
        const x = clamp(curFx - grabX, 0, W - startRect.w);
        const y = clamp(curFy - grabY, 0, H - startRect.h);
        return { x, y, w: startRect.w, h: startRect.h };
      }
      const dx = curFx - startMouseFx;
      const dy = curFy - startMouseFy;
      return updateCrop(type, startRect, dx, dy, W, H, ratioValue);
    };

    // 直接更新 DOM，不用 requestAnimationFrame 节流，避免快速拖拽时裁切框滞后鼠标
    const move = (ev: PointerEvent) => {
      latestX = ev.clientX;
      latestY = ev.clientY;
      syncDomStyles(compute(latestX, latestY), frameEl);
    };
    const up = () => {
      try { target.releasePointerCapture(e.pointerId); } catch { /* noop */ }
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      const next = compute(latestX, latestY);
      syncDomStyles(next, frameEl);
      setIsDragging(false);
      setCrop(next);
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  };

  const onFramePointerDown = (e: React.PointerEvent) => {
    const frameEl = frameRef.current;
    if (!frameEl) {
      startDrag('move', e);
      return;
    }
    const rect = frameEl.getBoundingClientRect();
    const type = resolveDragType(rect, e.clientX, e.clientY);
    startDrag(type, e);
  };

  const handleConfirm = async () => {
    if (!crop || !disp || !naturalRef.current) return;
    try {
      const img = await loadImage(url);
      const nat = naturalRef.current;

      const plan = computeCropExportPlan({
        crop,
        disp: { w: disp.w, h: disp.h },
        nat,
        dpr: window.devicePixelRatio,
      });

      if (plan.status === 'too-small') {
        toast.error('裁剪区域过小');
        return;
      }

      const { source, outWidth, outHeight } = plan;
      const canvas = document.createElement('canvas');
      canvas.width = outWidth;
      canvas.height = outHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('canvas context');
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, source.sx, source.sy, source.sw, source.sh, 0, 0, outWidth, outHeight);

      if (plan.lowResSource) {
        toast.warning('裁剪区域在原图中分辨率偏低，放大显示可能仍会模糊（建议选用原图更大区域或更高清的源图）');
      }

      onConfirm(canvas.toDataURL('image/png'), { width: outWidth, height: outHeight });
    } catch {
      toast.error('裁剪失败');
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

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.stopPropagation();
    e.preventDefault();
  }, []);

  const onCtxMenu = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
  }, []);

  // 裁切框手柄类型列表
  const EDGES = ['n', 's', 'e', 'w'] as const;
  const CORNERS = ['nw', 'ne', 'sw', 'se'] as const;

  return (
    <div
      className="pea-crop-overlay"
      data-cropping-overlay="true"
      role="dialog"
      aria-label="图片裁剪"
      onWheel={onWheel}
      onContextMenu={onCtxMenu}
    >
      <div className="pea-crop-stage" onClick={stop} onWheel={onWheel}>
        {!isReady ? (
          <div className="pea-crop-loading">
            <span className="pea-crop-loading-text">准备裁剪…</span>
          </div>
        ) : (
          <div className="pea-crop-image-stage" style={{ width: W, height: H }}>
            <div className="pea-crop-img-clip">
              <img className="pea-crop-image" src={url} alt="裁剪图片" draggable={false} />
            </div>

            <div
              ref={frameRef}
              className={`pea-crop-frame${isDragging ? ' pea-crop-frame--dragging' : ''}`}
              style={{ transform: `translate3d(${crop.x}px, ${crop.y}px, 0)`, left: 0, top: 0, width: crop.w, height: crop.h }}
              onPointerDown={onFramePointerDown}
              role="button"
              aria-label="拖动裁切区"
              tabIndex={0}
            >
              {CORNERS.map((h) => (
                <span
                  key={h}
                  className={`pea-crop-handle pea-crop-corner ${h}`}
                  onPointerDown={(e) => startDrag(h, e)}
                  role="button"
                  aria-label={`调整 ${h}`}
                  tabIndex={-1}
                />
              ))}
              {EDGES.map((h) => (
                <span
                  key={h}
                  className={`pea-crop-handle pea-crop-edge ${h}`}
                  onPointerDown={(e) => startDrag(h, e)}
                  role="button"
                  aria-label={`调整 ${h}边`}
                  tabIndex={-1}
                />
              ))}
              <div className="pea-crop-grid" aria-hidden="true">
                <span className="pea-crop-grid-line v1" />
                <span className="pea-crop-grid-line v2" />
                <span className="pea-crop-grid-line h1" />
                <span className="pea-crop-grid-line h2" />
              </div>
            </div>
          </div>
        )}
      </div>

      {isReady && (
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
            aria-label="确认裁剪"
            title="确认裁剪"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            <span className="pea-crop-confirm-text">确认裁剪</span>
          </button>
        </div>
      )}
    </div>
  );
}

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

function formatRatio(n: number) {
  if (Math.abs(n - Math.round(n)) < 0.001) return `${Math.round(n)}:1`;
  return `${n.toFixed(2)}:1`;
}
