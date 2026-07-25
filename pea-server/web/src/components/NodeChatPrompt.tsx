import { useEffect, useRef, useState, useCallback, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';
import { useAgent } from '../store/agent';
import { toast } from '../store/toast';
import { listAvailableModels, estimateCost, acceptGenerationJob } from '../api/catalog';
import type { AvailableModel, PricingRule } from '../api/catalog';

interface KindCfg {
  label: string;
  placeholder: string;
  modelIcon: string;
}

/** 图片比例选项 */
const ASPECT_RATIOS = [
  { label: '1:1', value: '1:1', w: 1024, h: 1024 },
  { label: '4:3', value: '4:3', w: 1024, h: 768 },
  { label: '3:4', value: '3:4', w: 768, h: 1024 },
  { label: '16:9', value: '16:9', w: 1344, h: 768 },
  { label: '9:16', value: '9:16', w: 768, h: 1344 },
  { label: '3:2', value: '3:2', w: 1152, h: 768 },
  { label: '2:3', value: '2:3', w: 768, h: 1152 },
  { label: '21:9', value: '21:9', w: 1536, h: 640 },
];

/** 分辨率档位 */
const RESOLUTIONS = [
  { label: '1K', value: '1k', scale: 1024 },
  { label: '2K', value: '2k', scale: 2048 },
  { label: '3K', value: '3k', scale: 3072 },
];

/** 倍率选项 */
const COUNT_OPTIONS = [1, 2, 3, 4].map((n) => ({ label: `${n}x`, value: n }));

/**
 * 节点下方全宽输入栏（对齐参考截图 2~5）。
 * 选中单个节点时在节点正下方浮现与节点同宽的输入栏。
 *
 * 定位策略（关键修复 2026-07-24）：
 *  - 不再用 document.querySelector 实时查询节点 DOM（React 重渲期间会返回 null → 输入栏闪退）。
 *  - 改为基于节点 DOM getBoundingClientRect + rAF 循环，确定性计算 fixed 视口坐标。
 *
 * 生成接入（2026-07-25）：
 *  - 按节点 kind 动态加载 /models/available，模型名/参数均动态，不再硬编码。
 *  - 模型选择器为卡片式富交互 UI（非原生 select），显示名称/标签/耗时/锁定状态。
 *  - 图片节点额外提供 比例(1:1/4:3/…) + 分辨率(1K/2K/3K) + 倍率(1x~4x) 选择。
 *  - 提交真实 POST /generation/jobs（带 model + params + 幂等键）；通过 WS
 *    job.updated 事件 + canvas.jobNodeMap 把 resultUrl 异步回填到触发节点。
 */
const KIND_CFG: Record<string, KindCfg> = {
  text: { label: '文本', placeholder: '描述任何你想要生成的内容', modelIcon: '✦' },
  image: { label: '图片', placeholder: '描述任何你想要生成的内容', modelIcon: '📊' },
  video: { label: '视频', placeholder: '描述你想生成的内容，或输入 /@ 唤出素材库与快捷操作', modelIcon: '📊' },
  audio: { label: '音频', placeholder: '描述你想要生成的任何内容', modelIcon: '🌊' },
  generate: { label: '生成', placeholder: '描述你想生成的内容', modelIcon: '✦' },
};

/** 节点 kind → 生成类型（后端仅支持 image/video/text；audio 暂未接入生成）。 */
const GEN_TYPE: Record<string, 'image' | 'video' | 'text' | null> = {
  text: 'text',
  image: 'image',
  video: 'video',
  generate: 'image',
  audio: null,
};

/* ──────────────── 视口感知弹出定位辅助 ──────────────── */

interface PopupPosition { left: number; top: number | 'auto'; bottom: number | 'auto'; placement: 'top' | 'bottom' }

/** 计算弹出层位置：优先在 anchor 上方展开（抽拉式效果）；若上方空间不足则翻转到下方。同时处理水平边界。 */
function usePopupPosition(anchorRect: { left: number; top: number; width: number; bottom?: number }, popupHeight: number, popupWidth?: number): PopupPosition {
  const [pos, setPos] = useState<PopupPosition>({ left: anchorRect.left, top: anchorRect.top, bottom: 'auto', placement: 'top' });

  useEffect(() => {
    const vh = window.innerHeight;
    const vw = window.innerWidth;
    const gap = 10;  // 统一间距 10px：所有弹出框（模型/比例/数量）一致，不紧贴按钮
    const anchorTop = anchorRect.top;
    const anchorBottom = anchorRect.bottom ?? (anchorTop + 40);  // 默认按钮高度 40px
    const anchorLeft = anchorRect.left;
    const anchorWidth = anchorRect.width;

    // 计算垂直位置：优先上方（抽拉式效果）
    const spaceBelow = vh - anchorBottom;   // 锚点底部到视口底
    const spaceAbove = anchorTop;           // 视口顶到锚点顶
    let top: number | 'auto';
    let bottom: number | 'auto';
    let placement: 'top' | 'bottom';
    
    // 用 bottom 定位：弹窗底边 = 按钮底边 - gap，间距恒为 gap，与预估高度无关
    if (spaceAbove >= popupHeight + gap) {
      top = 'auto';
      bottom = vh - (anchorBottom - gap);   // 弹窗底边固定在按钮底边上方 gap
      placement = 'top';
    } else if (spaceBelow >= popupHeight + gap) {
      top = anchorBottom + gap;             // 下方：弹窗顶边在按钮底边下方 gap
      bottom = 'auto';
      placement = 'bottom';
    } else {
      if (spaceAbove >= spaceBelow) {
        top = 'auto';
        bottom = Math.max(gap, vh - (anchorBottom - gap));
        placement = 'top';
      } else {
        top = Math.max(gap, anchorBottom + gap);
        bottom = 'auto';
        placement = 'bottom';
      }
    }

    // 计算水平位置：默认左对齐，若超出右边界则右对齐或夹紧
    let left: number;
    const effectiveWidth = popupWidth ?? anchorWidth;
    if (anchorLeft + effectiveWidth > vw - gap) {
      // 右对齐
      left = Math.max(gap, vw - effectiveWidth - gap);
    } else {
      // 左对齐
      left = anchorLeft;
    }

    setPos({ left, top, bottom, placement });
  }, [anchorRect.left, anchorRect.top, anchorRect.bottom, anchorRect.width, popupHeight, popupWidth]);

  return pos;
}

/* ──────────────── 模型选择弹出层（视口感知） ──────────────── */

interface ModelPickerPopupProps {
  rect: { left: number; top: number; width: number; bottom?: number };
  models: AvailableModel[];
  modelId: string;
  selectedModel: AvailableModel | null;
  est: { cost: number; allowed: boolean; minPlanLevel: number } | null;
  onPick: (id: string) => void;
  onClose: () => void;
}

const ModelPickerPopup = forwardRef<HTMLDivElement, ModelPickerPopupProps>((props, ref) => {
  const { rect, models, modelId, selectedModel, est, onPick, onClose } = props;

  // 弹出层固定宽度 340px，预估高度 ~223px（实际测量）
  const popupWidth = 340;
  const popupHeight = 223;
  const pos = usePopupPosition({ ...rect, bottom: (rect as any).bottom ?? rect.top + 200 }, popupHeight, popupWidth);

  const modelIconFor = (m: AvailableModel): string => {
    const n = m.displayName.toLowerCase();
    if (n.includes('gemini')) return '💎';
    if (n.includes('deepseek')) return '🔍';
    if (n.includes('agnes')) return '✦';
    if (n.includes('seedream') || n.includes('seed')) return '🌾';
    return '✦';
  };

  const modelTags = useCallback((m: AvailableModel): string[] => {
    const tags: string[] = [];
    if (m.modelType === 'text') {
      if (m.displayName.toLowerCase().includes('flash') || m.displayName.toLowerCase().includes('lite')) tags.push('轻量快速', '低成本');
      else if (m.displayName.toLowerCase().includes('pro')) tags.push('增强推理', '高质量');
      else tags.push('通用');
    } else if (m.modelType === 'image') {
      if (m.displayName.toLowerCase().includes('flash') || m.displayName.toLowerCase().includes('lite')) tags.push('快速出图', '低成本');
      else tags.push('高质量', '精细');
    } else { tags.push('通用'); }
    tags.push(m.modelType === 'text' ? (m.displayName.toLowerCase().includes('pro') ? '10 ~ 20s' : '5 ~ 10s') : '10 ~ 20s');
    return tags;
  }, []);

  return (
      <div
        ref={ref}
        className="node-model-picker"
        style={{
          position: 'fixed',
          left: pos.left,
          top: pos.top,
          bottom: pos.bottom,
          width: popupWidth,
        }}
      role="dialog"
      aria-label="选择模型"
    >
      <div className="picker-scroll">
        {models.map((m) => {
          const isActive = m.id === modelId;
          return (
            <button key={m.id} type="button"
              className={`picker-card${isActive ? ' picker-card-active' : ''}${!m.allowed ? ' picker-card-locked' : ''}`}
              onClick={() => { if (m.allowed) { onPick(m.id); } }}
              disabled={!m.allowed}
            >
              <div className="picker-card-head">
                <span className="picker-card-icon">{modelIconFor(m)}</span>
                <span className="picker-card-name">{m.displayName}</span>
                {m.isDefault && <span className="picker-badge picker-badge-new">DEFAULT</span>}
                {!m.allowed && <span className="picker-lock">🔒</span>}
                {isActive && <svg className="picker-check" width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
              </div>
              <div className="picker-card-tags">
                {modelTags(m).map((tag, i) => <span key={i} className="picker-tag">{tag}</span>)}
              </div>
              {!m.allowed && <div className="picker-card-lock-hint">需 Lv.{m.minPlanLevel}</div>}
            </button>
          );
        })}
        {models.length === 0 && <div className="picker-empty">暂无可用模型</div>}
      </div>
      <div className="picker-footer">
        {selectedModel && (
          <div className="picker-selected-row">
            <span className="picker-sel-icon">{modelIconFor(selectedModel)}</span>
            <span className="picker-sel-name">{selectedModel.displayName}</span>
          </div>
        )}
        <div className="picker-est">
          预计消耗 <b>💎 {est?.cost ?? '…'}</b> Tapies
          {est && !est.allowed && <span className="picker-warn">需套餐 ≥ Lv.{est.minPlanLevel}</span>}
        </div>
      </div>
    </div>
  );
});
ModelPickerPopup.displayName = 'ModelPickerPopup';

/* ──────────────── 比例/分辨率弹出层（视口感知） ──────────────── */

interface AspectPickerPopupProps {
  rect: { left: number; top: number; width: number; bottom?: number };
  resolution: string;
  aspectRatio: string;
  onResolution: (v: string) => void;
  onAspectRatio: (v: string) => void;
  onClose: () => void;
}

const AspectPickerPopup = forwardRef<HTMLDivElement, AspectPickerPopupProps>((props, ref) => {
  const { rect, resolution, aspectRatio, onResolution, onAspectRatio } = props;

  // 弹出层固定宽度 200px，预估高度 ~240px
  const popupWidth = 200;
  const pos = usePopupPosition({ ...rect, bottom: (rect as any).bottom ?? rect.top + 160 }, 260, popupWidth);

  return (
      <div ref={ref} className="node-aspect-picker" style={{
        position: 'fixed', left: pos.left, top: pos.top, bottom: pos.bottom, width: popupWidth,
      }} role="dialog" aria-label="画幅设置">
      <div className="aspect-section">
        <div className="aspect-label">画质</div>
        <div className="aspect-res-btns">
          {RESOLUTIONS.map((r) => (
            <button key={r.value} type="button"
              className={`aspect-res-btn${resolution === r.value ? ' active' : ''}`}
              onClick={() => onResolution(r.value)}
            >{r.label}</button>
          ))}
        </div>
      </div>
      <div className="aspect-section">
        <div className="aspect-label">比例</div>
        <div className="aspect-grid">
          {ASPECT_RATIOS.map((ar) => (
            <button key={ar.value} type="button"
              className={`aspect-ratio-btn${aspectRatio === ar.value ? ' active' : ''}`}
              onClick={() => onAspectRatio(ar.value)}
              title={`${ar.label} (${ar.w}×${ar.h})`}
            >
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                <rect x={(28 - 22 * (ar.w / Math.max(ar.w, ar.h))) / 2}
                  y={(28 - 22 * (ar.h / Math.max(ar.w, ar.h))) / 2}
                  width={22 * (ar.w / Math.max(ar.w, ar.h))}
                  height={22 * (ar.h / Math.max(ar.w, ar.h))}
                  rx="2.5" stroke="currentColor" strokeWidth="1.4" fill="none"/>
              </svg>
              <span>{ar.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
});
AspectPickerPopup.displayName = 'AspectPickerPopup';

export default function NodeChatPrompt() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const selectedId = useCanvas((s) => s.selectedId);
  const nodes = useCanvas((s) => s.nodes);
  const update = useCanvas((s) => s.updateNodeData);
  const push = useAgent((s) => s.push);
  const setOpen = useAgent((s) => s.setOpen);
  const viewport = useViewport();

  const single = selectedIds.length === 1 ? selectedIds[0] : selectedId;
  const sel = single ? nodes.find((n) => n.id === single) : null;

  const [rect, setRect] = useState<{ left: number; top: number; width: number; bottom: number } | null>(null);
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const prevSingleRef = useRef<string | null>(null);
  // 按节点 id 缓存输入草稿：切换节点再切回时"接着上次编辑的内容继续写"
  const draftRef = useRef<Record<string, string>>({});
  // rAF 循环保持位置实时同步（拖动/缩放/平移时输入栏跟随节点）
  const rafRef = useRef<number>();
  const lastRectRef = useRef('');

  // ── 生成态（模型/参数/预估）──
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [modelId, setModelId] = useState('');
  const [tierVals, setTierVals] = useState<Record<string, string>>({});
  const [count, setCount] = useState(1);
  const [est, setEst] = useState<{ cost: number; allowed: boolean; minPlanLevel: number } | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  // 触发按钮的位置（用于弹出层定位）
  const [triggerRect, setTriggerRect] = useState<{ left: number; top: number; width: number; bottom: number } | null>(null);

  // 图片节点特有：比例 / 分辨率 / 倍率浮层
  const [aspectOpen, setAspectOpen] = useState(false);
  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [resolution, setResolution] = useState('2k');
  const [countOpen, setCountOpen] = useState(false);
  const aspectRef = useRef<HTMLDivElement>(null);
  const countRef = useRef<HTMLDivElement>(null);
  const aspectBtnRef = useRef<HTMLButtonElement>(null);
  const [aspectTriggerRect, setAspectTriggerRect] = useState<{ left: number; top: number; width: number; bottom: number } | null>(null);

  const kind = sel?.data.kind ?? 'text';
  const genType = GEN_TYPE[kind] ?? null;
  const selectedModel = models.find((m) => m.id === modelId) ?? null;
  const tiers = (selectedModel?.pricing as PricingRule | null)?.tiers ?? {};
  const dimKeys = Object.keys(tiers);
  const multiplier = (selectedModel?.pricing as PricingRule | null)?.multiplier ?? null;
  const params: Record<string, unknown> = { ...tierVals };
  if (multiplier) params[multiplier] = count;

  // 图片节点：把比例和分辨率映射为 width/height
  if (genType === 'image') {
    const ar = ASPECT_RATIOS.find((a) => a.value === aspectRatio) ?? ASPECT_RATIOS[0];
    const res = RESOLUTIONS.find((r) => r.value === resolution) ?? RESOLUTIONS[1];
    // 以长边对齐分辨率档位，短边按比例缩放
    const scale = res.scale;
    const longSide = Math.max(ar.w, ar.h);
    const shortSide = Math.min(ar.w, ar.h);
    const ratio = scale / longSide;
    params.width = Math.round(ar.w * ratio);
    params.height = Math.round(ar.h * ratio);
    params.size = res.value; // 供后端 _map_size 使用
    // 持久化比例/分辨率选择：写入 genParams 以便重新选中节点时还原（修复 #26）
    params.aspectRatio = aspectRatio;
    params.resolution = resolution;
  }

  // ── WS 监听：job.updated → 通过 jobNodeMap 回填结果（仅挂载一次）──
  useEffect(() => {
    const onEvent = (e: Event) => {
      const ev = (e as CustomEvent).detail;
      if (!ev || ev.kind !== 'job.updated') return;
      const nodeId = useCanvas.getState().jobNodeMap[ev.jobId];
      if (!nodeId) return;
      if (ev.status === 'done') {
        useCanvas.getState().applyJobResult(ev.jobId, {
          generating: false,
          resultUrl: ev.resultUrl ?? undefined,
        });
        useCanvas.getState().removeJob(ev.jobId);
        toast.success('生成完成');
      } else if (ev.status === 'failed' || ev.status === 'refunded') {
        useCanvas.getState().applyJobResult(ev.jobId, { generating: false });
        useCanvas.getState().removeJob(ev.jobId);
        toast.error(ev.error || '生成失败，已退款');
      }
    };
    window.addEventListener('pea:event', onEvent);
    return () => window.removeEventListener('pea:event', onEvent);
  }, []);

  // ── 节点切换：恢复该节点的草稿（优先）/已保存 prompt，否则清空 ──
  useEffect(() => {
    if (!single) {
      setText('');
      prevSingleRef.current = null;
      return;
    }
    if (single !== prevSingleRef.current) {
      prevSingleRef.current = single;
      const node = nodes.find((n) => n.id === single);
      const restored = draftRef.current[single] ?? node?.data.prompt ?? '';
      setText(restored);
      setTimeout(() => inputRef.current?.focus(), 60);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [single, nodes]);

  // ── 加载可用模型 + 依据节点已存 meta 还原模型/参数选择 ──
  useEffect(() => {
    if (!single || !genType) {
      setModels([]);
      setModelId('');
      setPickerOpen(false);
      return;
    }
    let cancelled = false;
    setModels([]);
    setModelId('');
    listAvailableModels(genType)
      .then((list) => {
        if (cancelled) return;
        setModels(list);
        const node = useCanvas.getState().nodes.find((n) => n.id === single);
        const meta = ((node?.data.meta ?? {}) as Record<string, unknown>) || {};
        const pick =
          list.find((m) => m.id === meta.modelId) ??
          list.find((m) => m.isDefault) ??
          list[0];
        setModelId(pick?.id ?? '');
        // 初始化参数：默认取各 tier 维度第一项；若节点已存 genParams 则还原
        const t = (pick?.pricing as PricingRule | null)?.tiers ?? {};
        const init: Record<string, string> = {};
        Object.keys(t).forEach((d) => {
          init[d] = String(Object.keys(t[d] ?? {})[0] ?? '');
        });
        const gp = (meta.genParams ?? {}) as Record<string, unknown>;
        Object.keys(t).forEach((d) => {
          if (gp[d] !== undefined) init[d] = String(gp[d]);
        });
        setTierVals(init);
        const mult = (pick?.pricing as PricingRule | null)?.multiplier ?? null;
        setCount(mult && gp[mult] != null ? Number(gp[mult]) || 1 : 1);
        // 图片节点：还原比例/分辨率
        if (genType === 'image') {
          setAspectRatio((gp.aspectRatio as string) || '1:1');
          setResolution((gp.resolution as string) || '2k');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setModels([]);
          setModelId('');
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [genType, single]);

  // ── 实时预估 Tapies（按当前模型 + 参数）──
  useEffect(() => {
    if (!modelId) {
      setEst(null);
      return;
    }
    let cancelled = false;
    const key = JSON.stringify(params);
    const t = setTimeout(() => {
      estimateCost(modelId, params)
        .then((r) => {
          if (!cancelled) setEst({ cost: r.cost, allowed: r.allowed, minPlanLevel: r.minPlanLevel });
        })
        .catch(() => {
          if (!cancelled) setEst(null);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, JSON.stringify(params)]);

  // ── 关闭所有浮层（点击外部 / Esc）──
  useEffect(() => {
    const anyOpen = pickerOpen || aspectOpen || countOpen;
    if (!anyOpen) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      // 检查是否点击在弹出框内部或触发按钮内部
      if (pickerRef.current?.contains(t) || chipRef.current?.contains(t)) return;
      if (aspectRef.current?.contains(t) || aspectBtnRef.current?.contains(t)) return;
      if (countRef.current?.contains(t)) return;
      setPickerOpen(false);
      setAspectOpen(false);
      setCountOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setPickerOpen(false); setAspectOpen(false); setCountOpen(false); }
    };
    window.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [pickerOpen, aspectOpen, countOpen]);

  // ── 确定性定位：基于节点真实 DOM 底边 + rAF 循环跟随 ──
  useEffect(() => {
    if (!sel || !single) {
      setRect(null);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const compute = (): { left: number; top: number; width: number; bottom: number } | null => {
      const nodeEl = document.querySelector(
        `.react-flow__node[data-id="${single}"]`,
      ) as HTMLElement | null;
      if (nodeEl) {
        const r = nodeEl.getBoundingClientRect();
        const centerX = r.left + r.width / 2;
        const width = Math.max(520, Math.round(r.width));
        const top = Math.round(r.bottom + 16);
        return { left: Math.round(centerX - width / 2), top, width, bottom: top + 130 };
      }
      // DOM 不可用时回退到 viewport 变换计算
      const { x: vx, y: vy, zoom } = viewport;
      const fx = sel.position.x;
      const fy = sel.position.y;
      const w = (sel.width ?? 260) * zoom;
      const h = (sel.height ?? 160) * zoom;
      const screenX = fx * zoom + vx;
      const screenY = fy * zoom + vy;
      const width = Math.max(520, Math.round(w));
      const top = Math.round(screenY + h + 16);
      return { left: Math.round(screenX + w / 2 - width / 2), top, width, bottom: top + 130 };
    };

    const loop = () => {
      const next = compute();
      if (next) {
        const key = `${next.left},${next.top},${next.width},${next.bottom}`;
        if (lastRectRef.current !== key) {
          lastRectRef.current = key;
          setRect(next);
        }
      }
      rafRef.current = requestAnimationFrame(loop);
    };

    const initial = compute();
    if (initial) setRect(initial);
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [sel, single, viewport.x, viewport.y, viewport.zoom, sel?.position.x, sel?.position.y, sel?.width, sel?.height]);

  // 模型切换回调（必须放在早期 return 之前，避免 hooks 数量随 rect 变化而触发 React #310）
  const onModelChange = useCallback((v: string) => {
    setModelId(v);
    const m = models.find((x) => x.id === v);
    const t = (m?.pricing as PricingRule | null)?.tiers ?? {};
    const init: Record<string, string> = {};
    Object.keys(t).forEach((d) => {
      init[d] = String(Object.keys(t[d] ?? {})[0] ?? '');
    });
    setTierVals(init);
    setCount(1);
  }, [models]);

  // 比例/分辨率变更时立即持久化到节点 meta（修复 #26：重新选中节点不回退默认值）
  const persistAspect = useCallback((ar: string) => {
    setAspectRatio(ar);
    if (single && genType === 'image') {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.aspectRatio = ar;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  const persistResolution = useCallback((res: string) => {
    setResolution(res);
    if (single && genType === 'image') {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.resolution = res;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  if (!sel || !rect || !single) return null;
  const cfg = KIND_CFG[kind] ?? KIND_CFG.text;

  const onTierChange = (dim: string, v: string) =>
    setTierVals((s) => ({ ...s, [dim]: v }));
  const onCountChange = (v: number) =>
    setCount(Number.isFinite(v) && v >= 1 ? Math.min(8, Math.floor(v)) : 1);

  const submit = async () => {
    const t = text.trim();
    if (!t || submitting) return;
    if (!genType) {
      toast.info('音频生成即将开放，敬请期待');
      return;
    }
    if (!modelId || !selectedModel) {
      toast.error('暂无可用模型，请联系管理员配置');
      return;
    }
    if (est && !est.allowed) {
      toast.error(`该模型需要更高套餐（权益等级 ≥ ${est.minPlanLevel}）`);
      return;
    }
    // 写入节点 prompt，并记忆所选模型/参数（随画布保存）
    const extraMeta: Record<string, unknown> = {};
    if (genType === 'image') { extraMeta.aspectRatio = aspectRatio; extraMeta.resolution = resolution; }
    update(single, {
      prompt: t,
      meta: { ...(sel.data.meta ?? {}), modelId, genParams: params, ...extraMeta },
    });
    push('user', `[${sel.data.label || cfg.label}] ${t}`);
    setSubmitting(true);
    try {
      const res = await acceptGenerationJob({
        type: genType,
        prompt: t,
        model: modelId,
        params,
        priority: 'normal',
        idempotencyKey: `gen-${single}-${Date.now()}`,
      });
      useCanvas.getState().registerJob(res.jobId, single);
      update(single, { generating: true });
      toast.success('已受理，生成中…');
      // 保留上一次输入的消息：不清空草稿与输入框，便于点击节点时再次带出 / 连续编辑。
      // 草稿已在 onChange 中实时写入 draftRef，故此处无需额外处理。
      setTimeout(() => inputRef.current?.focus(), 0);
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '受理失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setText('');
    }
  };

  const costLabel =
    est == null ? '…' : est.allowed ? String(est.cost) : `需 Lv.${est.minPlanLevel}`;

  // 模型图标映射
  const modelIconFor = (m: AvailableModel): string => {
    const n = m.displayName.toLowerCase();
    if (n.includes('gemini')) return '💎';
    if (n.includes('deepseek')) return '🔍';
    if (n.includes('agnes')) return '✦';
    if (n.includes('seedream') || n.includes('seed')) return '🌾';
    return '✦';
  };

  return (
    <div
      className="node-input-bar node-chat-prompt"
      style={{ left: rect.left, top: rect.top, width: rect.width, position: 'fixed' }}
      role="dialog"
      aria-label={`对 ${cfg.label} 节点提问`}
      data-kind={kind}
    >
      {/* 工具栏 */}
      <div className="node-input-tools">
        {(kind === 'image' || kind === 'video') && (
          <button type="button" className="node-input-tool" title="特效/灵感" aria-label="特效">
            ✦
          </button>
        )}
        <button type="button" className="node-input-tool" title="附件" aria-label="附件">
          +
        </button>
      </div>

      {/* 输入框（自动撑开，无滚动条） */}
      <textarea
        ref={inputRef}
        className="node-input-textarea node-chat-prompt-input"
        placeholder={cfg.placeholder}
        value={text}
        rows={1}
        onChange={(e) => {
          const v = e.target.value;
          setText(v);
          if (single) draftRef.current[single] = v;
          // 自动撑开：重置高度后根据内容计算
          e.target.style.height = 'auto';
          e.target.style.height = `${e.target.scrollHeight}px`;
        }}
        onKeyDown={onKey}
        onMouseDown={(e) => {
          // 点击输入框属于「点击非选择框区域」→ 关闭所有浮层（否则 stopPropagation 会阻止 window 监听器收到事件）
          setPickerOpen(false);
          setAspectOpen(false);
          setCountOpen(false);
          e.stopPropagation();
        }}
        style={{ minHeight: '60px', maxHeight: '200px', overflow: 'hidden', resize: 'none' }}
      />

      {/* 状态栏：左侧（模型/参数）+ 右侧（操作） */}
      <div className="node-input-status">
        <div className="node-input-status-left">
          {genType ? (
            /* ── 模型选择芯片（点击弹出卡片式选择器）── */
            <button
              ref={chipRef}
              type="button"
              className="node-input-model-chip"
              title={selectedModel?.displayName ?? '选择模型'}
              aria-label="选择模型"
              aria-haspopup="dialog"
              aria-expanded={pickerOpen}
              onClick={() => {
                // 记录触发按钮的实际位置
                const btnRect = chipRef.current?.getBoundingClientRect();
                if (btnRect) {
                  setTriggerRect({
                    left: btnRect.left,
                    top: btnRect.top,
                    width: btnRect.width,
                    bottom: btnRect.bottom,
                  });
                }
                setPickerOpen((v) => !v);
              }}
            >
              <span className="node-model-chip-icon">{selectedModel ? modelIconFor(selectedModel) : cfg.modelIcon}</span>
              <span className="node-model-chip-name">{selectedModel?.displayName || (models.length ? '选择模型' : '无可用模型')}</span>
              <svg className="node-model-chip-arrow" width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          ) : (
            <span className="node-input-model-chip disabled" title="音频生成即将开放">
              <span className="node-model-chip-icon">{cfg.modelIcon}</span>
              <span>音频生成即将开放</span>
            </span>
          )}

          {/* 图片节点：比例·分辨率 选择器（参考截图5 "1:1 · 2K"） */}
          {genType === 'image' && (
            <>
              <button
                ref={aspectBtnRef}
                type="button"
                className="node-input-aspect-chip"
                title={`比例 ${aspectRatio} · 分辨率 ${resolution.toUpperCase()}`}
                aria-haspopup="dialog"
                aria-expanded={aspectOpen}
                onClick={() => {
                  const btnRect = aspectBtnRef.current?.getBoundingClientRect();
                  if (btnRect) {
                    setAspectTriggerRect({
                      left: btnRect.left,
                      top: btnRect.top,
                      width: btnRect.width,
                      bottom: btnRect.bottom,
                    });
                  }
                  setAspectOpen((v) => !v);
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1.5" y="2.5" width="11" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><line x1="1.5" y1="5.5" x2="12.5" y2="5.5" stroke="currentColor" strokeWidth="1.3"/></svg>
                <span>{aspectRatio} · {resolution.toUpperCase()}</span>
                <svg className="node-model-chip-arrow" width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>

              {/* 倍率/数量选择已移至右侧消耗量前（按钮化），此处不再重复展示 */}
            </>
          )}

          {/* 通用 tier 参数（仅非图片节点展示；图片节点的参数已通过比例·分辨率芯片表达） */}
          {genType !== 'image' && dimKeys.map((d) => (
            <span key={d} className="node-input-param" title={d}>
              <span className="node-input-param-icon" aria-hidden>⚙</span>
              <span>{tierVals[d] ?? '—'}</span>
            </span>
          ))}
          {multiplier && genType !== 'image' && (
            <span className="node-input-param" title={multiplier}>
              <span className="node-input-param-icon" aria-hidden>×</span>
              <span>{count}</span>
            </span>
          )}
        </div>

        {/* 右侧操作区 */}
        <div className="node-input-status-right">
          <button type="button" className="node-input-icon-btn" title="语音输入" aria-label="语音">🎤</button>
          {kind !== 'audio' && (
            <div className="node-count-btn-wrapper" ref={countRef}>
              <button
                type="button"
                className="node-count-btn"
                title="生成数量"
                aria-expanded={countOpen}
                onClick={() => setCountOpen((v) => !v)}
              >
                {count}x
              </button>
              {/* hover 提示 "生成数量" */}
              <span className="node-count-btn-hint" aria-hidden>生成数量</span>
              {countOpen && (
                <div className="node-count-btn-dropdown">
                  {COUNT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className={`node-count-opt${count === opt.value ? ' active' : ''}`}
                      onClick={() => { onCountChange(opt.value); setCountOpen(false); }}
                      title={`生成 ${opt.value} 张图`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <span className="node-input-tapies" title="本次预计消耗 Tapies">
            <span className="node-input-tapies-icon" aria-hidden>💎</span>
            <span>{costLabel}</span>
          </span>
          <button
            type="button"
            className="node-input-send node-chat-prompt-send"
            title="发送 (Enter)"
            aria-label="发送"
            disabled={!text.trim() || submitting || (!!genType && !modelId)}
            onMouseDown={(e) => e.preventDefault()}
            onClick={submit}
          >
            ↑
          </button>
        </div>
      </div>

      {/* ═════════ 卡片式模型选择浮层（参考截图2/3）═════════════ */}
      {/* 使用 Portal 渲染到 body，避免被父元素的 transform 影响 fixed 定位 */}
      {pickerOpen && genType && triggerRect && createPortal(
        <ModelPickerPopup
          ref={pickerRef}
          rect={triggerRect}
          models={models}
          modelId={modelId}
          selectedModel={selectedModel}
          est={est}
          onPick={(id) => { if (models.find(m => m.id === id)?.allowed) { onModelChange(id); setPickerOpen(false); } }}
          onClose={() => setPickerOpen(false)}
        />,
        document.body
      )}

      {/* ═════════ 图片比例/分辨率浮层（参考截图5/6）═════════════ */}
      {aspectOpen && genType === 'image' && aspectTriggerRect && createPortal(
        <AspectPickerPopup
          ref={aspectRef}
          rect={aspectTriggerRect}
          resolution={resolution}
          aspectRatio={aspectRatio}
          onResolution={persistResolution}
          onAspectRatio={persistAspect}
          onClose={() => setAspectOpen(false)}
        />,
        document.body
      )}
    </div>
  );
}
