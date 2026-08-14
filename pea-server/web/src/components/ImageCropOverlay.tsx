import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useStore } from 'reactflow';
import { Dropdown } from 'antd';
import { toast } from '../store/toast';
import { updateCrop, clamp, MIN_CROP, type Rect, type CropDragType } from './cropMath';
import { resolveDragType } from '../lib/cropDrag';
import { computeCropExportPlan } from './cropExport';

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
 *  Core rule: crop image's visual size = the node's actual rendered pixel size
 *  on screen (×1.0). We read the container's getBoundingClientRect() to get the
 *  real screen pixels the user sees on canvas, then use that directly — no
 *  scaling, no viewport ratios.
 *
 *  ⚠️ Critical: getBoundingClientRect() returns *visual* (post-transform)
 *  pixels. The container lives inside ReactFlow's viewport which applies
 *  `transform: scale(zoom)`, so a CSS pixel we write as inline `width: W`
 *  will be visually multiplied by zoom. To make the crop image visually equal
 *  to the node (i.e. visualSize = baseW × zoom / zoom = baseW), we convert
 *  the visual pixel target back to a flow coordinate by dividing by zoom.
 *  This is purely a coordinate-space conversion, NOT a "scale factor"
 *  amplification — it cancels the transform ReactFlow would otherwise apply.
 *
 *  Safety: clamp to max 90% of viewport as safety net for extreme cases.
 */
function fitDisplay(natW: number, natH: number, containerEl: HTMLDivElement | null, zoom: number): Disp {
  const rect = containerEl?.getBoundingClientRect();
  const baseW = rect?.width ?? 400;
  const baseH = rect?.height ?? 300;

  // Preserve the original image aspect ratio. The crop UI shows the full,
  // uncropped image, so its display bounds must match the image ratio — not
  // the node's ratio. Fit the largest such rectangle inside the node bounds.
  const imageRatio = natW / natH;
  const nodeRatio = baseW / baseH;
  let visualW: number;
  let visualH: number;
  if (nodeRatio > imageRatio) {
    // Node is wider than the image -> height is the limiting axis.
    visualH = baseH;
    visualW = visualH * imageRatio;
  } else {
    // Node is taller than or equal to the image -> width is the limiting axis.
    visualW = baseW;
    visualH = visualW / imageRatio;
  }

  // Clamp to 90% viewport as safety net, maintaining aspect ratio.
  const viewMaxW = window.innerWidth * 0.90;
  const viewMaxH = window.innerHeight * 0.90;
  if (visualW > viewMaxW) {
    visualW = viewMaxW;
    visualH = visualW / imageRatio;
  }
  if (visualH > viewMaxH) {
    visualH = viewMaxH;
    visualW = visualH * imageRatio;
  }

  // Convert visual pixel target to flow coordinate (÷ zoom) so the rendered
  // size after ReactFlow's `transform: scale(zoom)` equals the intended visual
  // pixels. Guard zoom=0 just in case.
  const safeZoom = zoom > 0 ? zoom : 1;
  const finalW = visualW / safeZoom;
  const finalH = visualH / safeZoom;

  // Scale maps display pixels back to original image coordinates.
  // Because aspect ratio is preserved, visualW/natW == visualH/natH.
  const scale = visualW / natW;
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

/** Default crop rectangle on first open: preserve image ratio with a small inset,
 *  so the frame does not hug the image edges (matches the reference design). */
function initialCropRect(W: number, H: number, ratio: number | null) {
  const inset = 1 - INSET * 2; // 80% of the display area
  if (ratio == null) {
    const w = clamp(W * inset, MIN_CROP, W);
    const h = clamp(H * inset, MIN_CROP, H);
    return { x: (W - w) / 2, y: (H - h) / 2, w, h };
  }
  // Fit a ratio-locked rectangle inside the 80% display area.
  let w = W * inset;
  let h = w / ratio;
  if (h > H * inset) {
    h = H * inset;
    w = h * ratio;
  }
  return { x: (W - w) / 2, y: (H - h) / 2, w: clamp(w, MIN_CROP, W), h: clamp(h, MIN_CROP, H) };
}

/** 根据按下点在裁切框内的相对位置，判定拖拽类型（实现见 ./lib/cropDrag，纯函数便于单测）。
 *  band：边框命中带宽度（屏幕 px），任意缩放下都用屏幕 px 判定，抓取手感一致。
 *  - 同时贴近两条边 → 角点(nw/ne/sw/se)
 *  - 仅贴近一条边 → 对应边(n/s/e/w)（整条边都可抓，不再只有中点把手）
 *  - 都不贴近 → 整体平移(move)
 * 这样「点哪条边，就拖哪条边」，鼠标始终锁在按下那条边上。 */
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
  _W: number,
  _H: number,
  frameEl: HTMLDivElement | null,
) {
  if (frameEl) {
    frameEl.style.transform = `translate3d(${rect.x}px, ${rect.y}px, 0)`;
    frameEl.style.width = `${rect.w}px`;
    frameEl.style.height = `${rect.h}px`;
  }
  // Masks removed: v4 uses box-shadow vignette on .pea-crop-frame instead of
  // 4 independent mask divs (no corner overlap / alpha doubling issues).
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

  // Subscribe to ReactFlow viewport zoom so the crop image's visual size matches
  // the node's visual size regardless of canvas zoom level.
  const zoom = useStore((s) => s.transform[2]) || 1;

  const naturalRef = useRef<{ w: number; h: number } | null>(null);
  const dispRef = useRef<Disp | null>(null);

  // DOM refs for direct style manipulation during drag
  const frameRef = useRef<HTMLDivElement | null>(null);

  const W = disp?.w ?? 0;
  const H = disp?.h ?? 0;

  const ratioValue = useMemo(() => {
    if (ratioKey === 'custom') return customRatio;
    if (ratioKey === 'original') return originalRatio;
    return RATIO_VALUES[ratioKey];
  }, [ratioKey, customRatio, originalRatio]);

  // ── Lock canvas while crop overlay is open ────────────────────────────────
  // CanvasEditor listens for `crop-mode-change` to disable canvas pan/zoom and
  // add `.pea-canvas-locked`. We dispatch on mount/unmount so the lock is always
  // released even if the component is unmounted by an external route change.
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

  // Load image → measure container via getBoundingClientRect → calc display size → init crop rect
  useEffect(() => {
    let alive = true;
    loadImage(url)
      .then((img) => {
        if (!alive) return;
        const nat = { w: img.naturalWidth, h: img.naturalHeight };
        naturalRef.current = nat;
        setOriginalRatio(nat.w / nat.h);

        const d = fitDisplay(nat.w, nat.h, containerRef.current, zoom);
        dispRef.current = d;
        setDisp(d);
      })
      .catch(() => {
        toast.error('图片加载失败，无法裁剪');
        onClose();
      });
    return () => { alive = false; };
  }, [url, onClose, containerRef, zoom]);

  // Init crop rect once display size is ready.
  // Default ratio is 'original' -> crop frame preserves the image ratio with a small inset,
  // so it does not hug the image edges on first open.
  useEffect(() => {
    if (!disp || crop) return;
    setCrop(initialCropRect(disp.w, disp.h, originalRatio ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disp, originalRatio]);

  // Window resize: recalc display size and sync crop rect
  const onResize = useCallback(() => {
    const nat = naturalRef.current;
    if (!nat) return;
    const next = fitDisplay(nat.w, nat.h, containerRef.current, zoom);
    const prev = dispRef.current;
    dispRef.current = next;
    setDisp(next);
    if (prev && prev.w > 0 && prev.h > 0) {
      const rx = next.w / prev.w;
      const ry = next.h / prev.h;
      setCrop((c) => (c ? { x: c.x * rx, y: c.y * ry, w: c.w * rx, h: c.h * ry } : c));
    }
  }, [containerRef, zoom]);

  useLayoutEffect(() => {
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [onResize]);

  // Re-fit when canvas zoom changes (covers cases where the user pans/zooms
  // the canvas while crop is open, or zoom is set asynchronously after mount).
  // The crop overlay is locked against canvas panning/zoom, but Pro features
  // (e.g. modal overlays that change viewport) can still trigger a zoom change.
  useEffect(() => {
    const nat = naturalRef.current;
    if (!nat) return;
    const next = fitDisplay(nat.w, nat.h, containerRef.current, zoom);
    const prev = dispRef.current;
    dispRef.current = next;
    setDisp(next);
    if (prev && prev.w > 0 && prev.h > 0) {
      const rx = next.w / prev.w;
      const ry = next.h / prev.h;
      setCrop((c) => (c ? { x: c.x * rx, y: c.y * ry, w: c.w * rx, h: c.h * ry } : c));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Close crop when clicking outside the overlay: other nodes, canvas blank area,
  // or the current node's chrome (badge/toolbar). Keep open for the overlay itself
  // and its antd dropdown menu so ratio selection and drag interactions work.
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

  // Drag core: direct DOM manipulation + rAF merge + pointer capture for stable 60fps
  // Drag core: 直接从真实 DOM 测量 stage 矩形反算 flow 坐标（不依赖 zoom 变量），
  // 并用「鼠标按下时的 grab offset」保持鼠标与裁切框的相对位置恒定 —— 任意画布缩放下都不偏移。
  const startDrag = (type: CropDragType, e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!crop) return;

    const startRect = { ...crop };
    const target = e.currentTarget as HTMLElement;

    try { target.setPointerCapture(e.pointerId); } catch { /* noop */ }
    setIsDragging(true);

    const frameEl = frameRef.current;
    const stageEl = frameEl?.parentElement ?? null;
    if (!frameEl || !stageEl) return;

    // 直接从真实 DOM 测量 stage 的屏幕矩形，反算「屏幕 px → flow px」比例。
    // 关键：不看 useStore 的 zoom 变量，避免其与裁切框实际渲染 scale 不同步导致偏移。
    const stageRect = stageEl.getBoundingClientRect();
    const sx = W > 0 ? stageRect.width / W : 1;
    const sy = H > 0 ? stageRect.height / H : 1;

    // 鼠标按下瞬间在 stage 坐标系(flow)中的位置
    const startMouseFx = (e.clientX - stageRect.left) / sx;
    const startMouseFy = (e.clientY - stageRect.top) / sy;
    // 鼠标相对裁切框左上角的 flow 偏移（grab offset）—— move 拖拽全程保持此偏移
    const grabX = startMouseFx - startRect.x;
    const grabY = startMouseFy - startRect.y;

    let latestX = e.clientX;
    let latestY = e.clientY;
    let rafId = 0;

    const compute = (clientX: number, clientY: number): Rect => {
      const curFx = (clientX - stageRect.left) / sx;
      const curFy = (clientY - stageRect.top) / sy;
      if (type === 'move') {
        const x = clamp(curFx - grabX, 0, W - startRect.w);
        const y = clamp(curFy - grabY, 0, H - startRect.h);
        return { x, y, w: startRect.w, h: startRect.h };
      }
      // 边/角拖拽：用当前鼠标相对按下点的 flow 位移，走原 updateCrop（保持单方向/比例锁语义）
      const dx = curFx - startMouseFx;
      const dy = curFy - startMouseFy;
      return updateCrop(type, startRect, dx, dy, W, H, ratioValue);
    };

    const apply = () => {
      rafId = 0;
      syncDomStyles(compute(latestX, latestY), W, H, frameEl);
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
      const next = compute(latestX, latestY);
      syncDomStyles(next, W, H, frameEl);
      setIsDragging(false);
      setCrop(next);
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  };

  // 整框按下时，按点击位置判定拖拽类型：
  //  - 落在边框 band 内 → 对应边/角拖拽（整条边都可抓，不再只有中点把手）；
  //  - 否则 → 整体平移(move)。
  // 这样「点哪条边，鼠标就锁在那条边上」：边拖拽用按下点的精确 flow 坐标，
  // 拖动时该边始终跟随鼠标，不会因误触整框 move 而让鼠标跑进框内。
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
    setLoading(true);
    try {
      const img = await loadImage(url);
      const nat = naturalRef.current;

      // ── High-resolution crop export (no upscaling blur) ──────────────────
      // All decision logic lives in ./cropExport (pure, unit-tested in
      // verify/crop_export.test.ts). Here we only execute the plan.
      //
      // Why: 「裁小图后变模糊」的根因不是坐标算错，而是 1:1 导出的位图像素
      // 不足以支撑新节点在画布上的显示尺寸，浏览器只能插值拉伸。方案是从
      // 原图真实像素采样 + 按 DPR 超采样（封顶 2×），同时兜底 canvas 面积
      // 上限，避免 Safari/iOS 上 toDataURL 静默返回空白图。
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
      // High-quality resampling when supersampling.
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(
        img,
        source.sx,
        source.sy,
        source.sw,
        source.sh,
        0,
        0,
        outWidth,
        outHeight,
      );

      // Honest warning: if the crop's own source pixels are already small,
      // no frontend trick can invent detail — only a higher-res source image
      // or AI super-resolution can help. Tell the user instead of silently
      // shipping a blurry node.
      if (plan.lowResSource) {
        toast.warning('裁剪区域在原图中分辨率偏低，放大显示可能仍会模糊（建议选用原图更大区域或更高清的源图）');
      }

      onConfirm(canvas.toDataURL('image/png'), { width: outWidth, height: outHeight });
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

  // 裁切区域内禁止触发节点的右键菜单（复制/添加并连接/删除等），同时阻止浏览器默认菜单。
  // 否则在裁切框内右击会冒泡到 ReactFlow 节点，误弹节点上下文菜单并导致裁切被取消。
  const onCtxMenu = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
  }, []);

  // Render: in-place overlay, single layer
  return (
    <div
      className="pea-crop-overlay"
      data-cropping-overlay="true"
      role="dialog"
      aria-label="图片裁剪"
      onWheel={onWheel}
      onContextMenu={onCtxMenu}
    >
      {/* Stage: transparent container that exactly matches the node wrap */}
      <div className="pea-crop-stage" onClick={stop} onWheel={onWheel}>
        {!isReady ? (
          <div className="pea-crop-loading">
            <span className="pea-crop-loading-text">准备裁剪…</span>
          </div>
        ) : (
          <div className="pea-crop-image-stage" style={{ width: W, height: H }}>
            {/* Image + vignette mask via frame box-shadow */}
            <div className="pea-crop-img-clip">
              <img className="pea-crop-image" src={url} alt="裁剪图片" draggable={false} />
            </div>

            {/* Crop frame */}
            <div
              ref={frameRef}
              className={`pea-crop-frame${isDragging ? ' pea-crop-frame--dragging' : ''}`}
              style={{ transform: `translate3d(${crop.x}px, ${crop.y}px, 0)`, left: 0, top: 0, width: crop.w, height: crop.h }}
              onPointerDown={onFramePointerDown}
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
            </div>
          </div>
        )}
      </div>

      {/* Toolbar: floats below the image stage, outside the node bounds */}
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
      )}
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
