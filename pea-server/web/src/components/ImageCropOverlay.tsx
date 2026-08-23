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

function measureStage(el: HTMLDivElement | null): { w: number; h: number } | null {
  if (!el) return null;
  const w = el.offsetWidth, h = el.offsetHeight;
  if (w <= 0 || h <= 0) return null;
  return { w, h };
}

function initialCropRect(W: number, H: number, ratio: number | null) {
  const inset = 1 - INSET * 2;
  if (ratio == null) {
    const w = clamp(W * inset, MIN_CROP, W);
    const h = clamp(H * inset, MIN_CROP, H);
    return { x: (W - w) / 2, y: (H - h) / 2, w, h };
  }
  let w = W * inset;
  let h = w / ratio;
  if (h > H * inset) { h = H * inset; w = h * ratio; }
  return { x: (W - w) / 2, y: (H - h) / 2, w: clamp(w, MIN_CROP, W), h: clamp(h, MIN_CROP, H) };
}

function centerFitRect(W: number, H: number, ratio: number): Rect {
  const byW = { w: W, h: W / ratio };
  const byH = { w: H * ratio, h: H };
  const use = byW.h <= H ? byW : byH;
  return { x: (W - use.w) / 2, y: (H - use.h) / 2, w: use.w, h: use.h };
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => {
      fetch(url, { mode: 'cors' })
        .then(r => { if (!r.ok) throw new Error('fetch failed'); return r.blob(); })
        .then(blob => {
          const u = URL.createObjectURL(blob);
          const img2 = new Image();
          img2.onload = () => resolve(img2);
          img2.onerror = () => reject(new Error('load failed'));
          img2.src = u;
        })
        .catch(() => reject(new Error('load failed')));
    };
    img.src = url;
  });
}

function calcVignetteStyles(rect: Rect, W: number, H: number) {
  if (W <= 0 || H <= 0) return null;
  const { x, y, w, h } = rect;
  return {
    top:    { top: 0, left: 0, right: 0, height: `${(y / H * 100).toFixed(3)}%` },
    bottom: { bottom: 0, left: 0, right: 0, height: `${((H - y - h) / H * 100).toFixed(3)}%` },
    left:   { left: 0, top: `${(y / H * 100).toFixed(3)}%`, bottom: `${((H - y - h) / H * 100).toFixed(3)}%`, width: `${(x / W * 100).toFixed(3)}%` },
    right:  { right: 0, top: `${(y / H * 100).toFixed(3)}%`, bottom: `${((H - y - h) / H * 100).toFixed(3)}%`, width: `${((W - x - w) / W * 100).toFixed(3)}%` },
  };
}

export default function ImageCropOverlay({ url, containerRef, onClose, onConfirm }: Props) {
  const [disp, setDisp] = useState<{ w: number; h: number } | null>(null);
  const [crop, setCrop] = useState<Rect | null>(null);
  const [ratioKey, setRatioKey] = useState<CropRatio>('original');
  const [customRatio, setCustomRatio] = useState<number | null>(null);
  const [originalRatio, setOriginalRatio] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const isDraggingRef = useRef(false);
  isDraggingRef.current = isDragging;
  // grid opacity via state — no rAF delay, no flicker
  const [gridOpacity, setGridOpacity] = useState(0);

  const naturalRef = useRef<{ w: number; h: number } | null>(null);
  const dispRef = useRef<{ w: number; h: number } | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const vignetteRefs = useRef<{ top: HTMLDivElement | null; bottom: HTMLDivElement | null; left: HTMLDivElement | null; right: HTMLDivElement | null }>({ top: null, bottom: null, left: null, right: null });

  const W = disp?.w ?? 0;
  const H = disp?.h ?? 0;

  const ratioValue = useMemo(() => {
    if (ratioKey === 'custom') return customRatio;
    if (ratioKey === 'original') return originalRatio;
    return RATIO_VALUES[ratioKey];
  }, [ratioKey, customRatio, originalRatio]);

  useEffect(() => {
    try { window.dispatchEvent(new CustomEvent('crop-mode-change', { detail: { active: true } })); } catch {}
    return () => {
      try { window.dispatchEvent(new CustomEvent('crop-mode-change', { detail: { active: false } })); } catch {}
    };
  }, []);

  useEffect(() => {
    let alive = true;
    loadImage(url).then(img => {
      if (!alive) return;
      naturalRef.current = { w: img.naturalWidth, h: img.naturalHeight };
      setOriginalRatio(img.naturalWidth / img.naturalHeight);
      const measured = measureStage(containerRef.current);
      if (!measured) { toast.error('无法获取图片容器尺寸'); onClose(); return; }
      dispRef.current = measured;
      setDisp(measured);
    }).catch(() => { toast.error('图片加载失败，无法裁剪'); onClose(); });
    return () => { alive = false; };
  }, [url, onClose, containerRef]);

  useEffect(() => {
    if (!disp || crop) return;
    setCrop(initialCropRect(disp.w, disp.h, originalRatio ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disp, originalRatio]);

  // 初始化遮罩
  useLayoutEffect(() => {
    if (!crop || !W || !H) return;
    const s = calcVignetteStyles(crop, W, H);
    if (!s) return;
    const { top, bottom, left, right } = vignetteRefs.current;
    if (top) top.style.cssText = `position:absolute;left:0;right:0;top:0;height:${s.top.height};background:var(--pea-crop-vignette);pointer-events:none;`;
    if (bottom) bottom.style.cssText = `position:absolute;left:0;right:0;bottom:0;height:${s.bottom.height};background:var(--pea-crop-vignette);pointer-events:none;`;
    if (left) left.style.cssText = `position:absolute;left:0;top:${s.left.top};bottom:${s.left.bottom};width:${s.left.width};background:var(--pea-crop-vignette);pointer-events:none;`;
    if (right) right.style.cssText = `position:absolute;right:0;top:${s.right.top};bottom:${s.right.bottom};width:${s.right.width};background:var(--pea-crop-vignette);pointer-events:none;`;
  }, [crop, W, H]);

  const onResize = useCallback(() => {
    if (!naturalRef.current) return;
    const next = measureStage(containerRef.current);
    if (!next) return;
    const prev = dispRef.current;
    dispRef.current = next;
    setDisp(next);
    if (prev && prev.w > 0 && prev.h > 0) {
      setCrop(c => c ? { x: c.x * next.w / prev.w, y: c.y * next.h / prev.h, w: c.w * next.w / prev.w, h: c.h * next.h / prev.h } : c);
    }
  }, [containerRef]);
  useLayoutEffect(() => {
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [onResize]);

  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const fn = (e: PointerEvent) => {
      const t = e.target as HTMLElement | null;
      if (!t || t.closest('[data-cropping-overlay="true"]') || t.closest('.pea-crop-dropdown') || t.closest('.ant-dropdown-menu')) return;
      onCloseRef.current();
    };
    document.addEventListener('pointerdown', fn, true);
    return () => document.removeEventListener('pointerdown', fn, true);
  }, []);

  const applyRatio = (r: CropRatio) => {
    if (!crop || !W || !H) return;
    if (r === 'original') { setRatioKey('original'); setCrop(initialCropRect(W, H, originalRatio ?? null)); return; }
    if (r === 'custom') { setRatioKey('custom'); const v = customRatio ?? clamp(crop.w / crop.h, 0.01, 100); setCustomRatio(v); setCrop(centerFitRect(W, H, v)); return; }
    setRatioKey(r);
    setCrop(centerFitRect(W, H, RATIO_VALUES[r]));
  };

  const applyCustomSize = (wVal: number, hVal: number) => {
    if (!W || !H) return;
    if (wVal <= 0 || hVal <= 0) { toast.error('宽高必须大于 0'); return; }
    const r = wVal / hVal;
    setCustomRatio(r); setRatioKey('custom'); setCrop(centerFitRect(W, H, r));
  };

  // ── Drag ──────────────────────────────────────────────────────────────────
  const startDrag = (type: CropDragType, e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!crop || !W || !H) return;
    const frameEl = frameRef.current;
    const stageEl = frameEl?.parentElement ?? null;
    if (!frameEl || !stageEl) return;
    const target = e.currentTarget as HTMLElement;
    try { target.setPointerCapture(e.pointerId); } catch {}
    setIsDragging(true);
    setGridOpacity(1);
    // 统一用 W/H（与 crop 初始化坐标空间一致）计算拖拽偏移，
    // 避免 sRect.width / sW 因 CSS 缩放/transform 与 crop 坐标系不一致导致位置偏移。
    const startRect = { ...crop };
    const frameRect = frameEl.getBoundingClientRect();
    const offX = e.clientX - frameRect.left - startRect.x;
    const offY = e.clientY - frameRect.top - startRect.y;
    let lx = e.clientX, ly = e.clientY;
    const compute = (cx: number, cy: number): Rect => {
      const fx = cx - frameRect.left;
      const fy = cy - frameRect.top;
      if (type === 'move') {
        return {
          x: clamp(fx - offX, 0, W - startRect.w),
          y: clamp(fy - offY, 0, H - startRect.h),
          w: startRect.w, h: startRect.h,
        };
      }
      return updateCrop(type, startRect, fx - (offX + startRect.x), fy - (offY + startRect.y), W, H, ratioValue);
    };
    const move = (ev: PointerEvent) => {
      lx = ev.clientX; ly = ev.clientY;
      const next = compute(lx, ly);
      frameEl.style.transform = `translate3d(${next.x}px,${next.y}px,0)`;
      frameEl.style.width = `${next.w}px`;
      frameEl.style.height = `${next.h}px`;
      // vignette 由 useLayoutEffect([crop, W, H]) 统一管理，拖拽中无需重复计算
    };
    const up = () => {
      try { target.releasePointerCapture(e.pointerId); } catch {}
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      setCrop(compute(lx, ly));
      setIsDragging(false);
      setGridOpacity(0);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  };

  const onFramePointerDown = (e: React.PointerEvent) => {
    const frameEl = frameRef.current;
    if (!frameEl) { startDrag('move', e); return; }
    const rect = frameEl.getBoundingClientRect();
    startDrag(resolveDragType(rect, e.clientX, e.clientY), e);
  };

  // 只注册一次 mousemove，用 ref 读最新 isDragging，避免每次拖拽状态变化都卸载/重装监听器
  // 卸载时（组件销毁）才清除 cursor，拖拽中途不清
  const THRESHOLD = 12;
  useEffect(() => {
    const applyCursor = (e: MouseEvent) => {
      const frameEl = frameRef.current;
      if (!frameEl || isDraggingRef.current) return;
      const rect = frameEl.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const w = rect.width;
      const h = rect.height;
      const nearLeft   = x <  THRESHOLD;
      const nearRight  = x >  w - THRESHOLD;
      const nearTop    = y <  THRESHOLD;
      const nearBottom = y >  h - THRESHOLD;
      if (nearLeft && nearTop)       frameEl.style.setProperty('cursor', 'nwse-resize', 'important');
      else if (nearRight && nearTop) frameEl.style.setProperty('cursor', 'nesw-resize', 'important');
      else if (nearLeft && nearBottom) frameEl.style.setProperty('cursor', 'nesw-resize', 'important');
      else if (nearRight && nearBottom) frameEl.style.setProperty('cursor', 'nwse-resize', 'important');
      else if (nearLeft || nearRight) frameEl.style.setProperty('cursor', 'ew-resize', 'important');
      else if (nearTop || nearBottom) frameEl.style.setProperty('cursor', 'ns-resize', 'important');
      else if (x >= 0 && x <= w && y >= 0 && y <= h) frameEl.style.setProperty('cursor', 'move', 'important');
      else frameEl.style.removeProperty('cursor');
    };
    document.addEventListener('mousemove', applyCursor);
    return () => {
      const frameEl = frameRef.current;
      if (frameEl) frameEl.style.removeProperty('cursor');
      document.removeEventListener('mousemove', applyCursor);
    };
  }, []);

  const handleConfirm = async () => {
    if (!crop || !disp || !naturalRef.current) return;
    try {
      const img = await loadImage(url);
      const plan = computeCropExportPlan({ crop, disp: { w: disp.w, h: disp.h }, nat: naturalRef.current, dpr: window.devicePixelRatio });
      if (plan.status === 'too-small') { toast.error('裁剪区域过小'); return; }
      const { source, outWidth, outHeight } = plan;
      const canvas = document.createElement('canvas');
      canvas.width = outWidth; canvas.height = outHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error();
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, source.sx, source.sy, source.sw, source.sh, 0, 0, outWidth, outHeight);
      if (plan.lowResSource) toast.warning('裁剪区域在原图中分辨率偏低');
      onConfirm(canvas.toDataURL('image/png'), { width: outWidth, height: outHeight });
    } catch { toast.error('裁剪失败'); }
  };

  const dropdownItems = (Object.keys(RATIO_LABELS) as CropRatio[]).map(k => ({ key: k, label: RATIO_LABELS[k], onClick: () => applyRatio(k) }));
  const ratioLabel = ratioKey === 'custom' && customRatio ? formatRatio(customRatio) : RATIO_LABELS[ratioKey];
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  const isReady = W > 0 && H > 0 && crop != null;
  const onWheel = useCallback((e: React.WheelEvent) => { e.stopPropagation(); e.preventDefault(); }, []);
  const onCtxMenu = useCallback((e: React.MouseEvent) => { e.stopPropagation(); e.preventDefault(); }, []);

  return (
    <div className="pea-crop-overlay" data-cropping-overlay="true" role="dialog" aria-label="图片裁剪" onWheel={onWheel} onContextMenu={onCtxMenu}>
      <div className="pea-crop-stage" onClick={stop} onWheel={onWheel}>
        {!isReady ? (
          <div className="pea-crop-loading"><span className="pea-crop-loading-text">准备裁剪…</span></div>
        ) : (
          <div className="pea-crop-image-stage" style={{ width: W, height: H }}>
            <div className="pea-crop-img-clip">
              <img className="pea-crop-image" src={url} alt="裁剪图片" draggable={false} />
            </div>

            {/* 遮罩 */}
            <div className="pea-crop-vignette pea-crop-vignette-top" ref={el => { vignetteRefs.current.top = el; }} />
            <div className="pea-crop-vignette pea-crop-vignette-bottom" ref={el => { vignetteRefs.current.bottom = el; }} />
            <div className="pea-crop-vignette pea-crop-vignette-left" ref={el => { vignetteRefs.current.left = el; }} />
            <div className="pea-crop-vignette pea-crop-vignette-right" ref={el => { vignetteRefs.current.right = el; }} />

            {/* 裁切框 */}
            <div
              ref={frameRef}
              className={`pea-crop-frame${isDragging ? ' pea-crop-frame--dragging' : ''}`}
              style={{ transform: `translate3d(${crop.x}px,${crop.y}px,0)`, left: 0, top: 0, width: crop.w, height: crop.h }}
              onPointerDown={onFramePointerDown}
              role="button"
              aria-label="拖动裁切区"
              tabIndex={0}
            >
              {/* 九宫格参考线 */}
              <div className="pea-crop-grid" style={{ opacity: gridOpacity }} />
              {/* 四角拖拽区 */}
              {(['nw', 'ne', 'sw', 'se'] as const).map(dir => (
                <div key={dir} className={`pea-crop-resize pea-crop-resize--${dir}`} onPointerDown={e => startDrag(dir, e)} role="button" aria-label={`调整 ${dir}`} tabIndex={-1} />
              ))}
              {/* 四边拖拽区 */}
              {(['n', 's', 'e', 'w'] as const).map(dir => (
                <div key={dir} className={`pea-crop-resize pea-crop-resize--${dir}`} onPointerDown={e => startDrag(dir, e)} role="button" aria-label={`调整 ${dir}边`} tabIndex={-1} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 工具栏 */}
      {isReady && (
        <div className="pea-crop-toolbar" onClick={stop}>
          <button type="button" className="pea-crop-toolbar-btn" onClick={onClose} aria-label="取消裁剪"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M18 6L6 18"/><path d="M 6 6l12 12"/></svg></button>
          <div className="pea-crop-toolbar-sep" />
          <Dropdown menu={{ items: dropdownItems }} placement="top" arrow overlayClassName="pea-crop-dropdown">
            <button type="button" className="pea-crop-toolbar-btn pea-crop-ratio-btn" aria-label="选择裁剪比例">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
              <span className="pea-crop-ratio-label">{ratioLabel}</span>
            </button>
          </Dropdown>
          {ratioKey === 'custom' && <CustomRatioInput current={customRatio} onApply={applyCustomSize} />}
          <div className="pea-crop-toolbar-sep" />
          <button type="button" className="pea-crop-toolbar-btn pea-crop-confirm" onClick={handleConfirm} aria-label="确认裁剪">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 6L9 17l-5-5"/></svg>
            <span className="pea-crop-confirm-text">确认裁剪</span>
          </button>
        </div>
      )}
    </div>
  );
}

function CustomRatioInput({ current, onApply }: { current: number | null; onApply: (w: number, h: number) => void }) {
  const wRef = useRef<HTMLInputElement | null>(null);
  const [wDraft, setWDraft] = useState(() => (current ? String(Math.round(current * 1000) / 1000) : '1'));
  const [hDraft, setHDraft] = useState('1');
  useEffect(() => { if (current) setWDraft(String(Math.round(current * 1000) / 1000)); }, [current]);
  const commit = () => { const w = parseFloat(wDraft); const h = parseFloat(hDraft); if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) onApply(w, h); };
  const onKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); commit(); wRef.current?.blur(); } };
  return (
    <div className="pea-crop-custom-ratio" onClick={e => e.stopPropagation()}>
      <input ref={wRef} type="number" min="0.01" step="0.1" value={wDraft} onChange={e => setWDraft(e.target.value)} onKeyDown={onKeyDown} onBlur={commit} placeholder="宽" aria-label="自定义宽" className="pea-crop-custom-input" />
      <span className="pea-crop-custom-colon">:</span>
      <input type="number" min="0.01" step="0.1" value={hDraft} onChange={e => setHDraft(e.target.value)} onKeyDown={onKeyDown} onBlur={commit} placeholder="高" aria-label="自定义高" className="pea-crop-custom-input" />
    </div>
  );
}

function formatRatio(n: number) {
  if (Math.abs(n - Math.round(n)) < 0.001) return `${Math.round(n)}:1`;
  return `${n.toFixed(2)}:1`;
}
