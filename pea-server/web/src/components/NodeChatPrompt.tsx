import { useEffect, useRef, useState, useCallback, useMemo, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import { Node } from 'reactflow';

/** 简易防抖：用于把编辑框内容持久化到节点 meta，避免逐字输入频繁写 store。 */
function debounce<T extends (...args: any[]) => void>(fn: T, wait: number) {
  let t: any;
  return (...args: Parameters<T>) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}
import { useCanvas, PeaNodeData, stripRefTokens } from '../store/canvas';
import { useAgent } from '../store/agent';
import { toast } from '../store/toast';
import { listAvailableModels, estimateCost, acceptNodeGenerationJob } from '../api/catalog';
import type { AvailableModel, PricingRule } from '../api/catalog';
import NodePromptInput, { NodePromptInputRef, ParsedPrompt } from './NodePromptInput';
import { getFileUrl, getPresignedUrl } from '../api/files';
import { PeaNodeKind } from '../constants/nodeTypes';
import { pollNodeJobResult } from '../lib/nodeGeneration';
import { syncBalance } from '../lib/balanceSync';
import { shouldHideNodeEditor } from '../lib/nodeSemantics';

/**
 * 节点生成结果轮询兜底：实现见 ../lib/nodeGeneration（pollNodeJobResult）。
 * 失败态会把 error 写回节点，供节点内失败卡展示与重试。
 */

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
  { label: '4K', value: '4k', scale: 4096 },
];

/** 倍率选项 */
const COUNT_OPTIONS = [1, 2, 3, 4].map((n) => ({ label: `${n}x`, value: n }));

/** 视频清晰度档位 */
const VIDEO_RESOLUTIONS = [
  { label: '480p', value: '480p', scale: 480 },
  { label: '720p', value: '720p', scale: 720 },
];

/** 视频生成时长选项（秒） */
const DURATIONS = ['4s', '5s', '6s', '7s', '8s', '9s', '10s', '11s', '12s'];

/** 视频生成方式 */
const GEN_MODES = [
  { label: '首尾帧', value: 'first_last', desc: '首尾帧模式' },
  { label: '全能参考', value: 'full_ref', desc: '全能参考模式' },
];

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
/* ──────────────── 上游输入解析辅助 ──────────────── */

function extractNodeText(node: Node<PeaNodeData>): string {
  const raw = node.data.prompt || node.data.html || '';
  return raw.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

async function resolveUpstreamMediaUrl(node: Node<PeaNodeData>): Promise<string | undefined> {
  const d = node.data;
  const urls = d.resultUrls?.length ? d.resultUrls : d.resultUrl ? [d.resultUrl] : [];
  const firstUrl = urls[0] || d.url;
  // ★ 关键修复：必须校验 scheme / 路径。
  // AI 生成图的 resultUrl 是相对路径 /media/...（PEA_CDN_BASE_URL=/media），
  // blob: URL 仅浏览器内可达——两者发给外部模型(Agnes)都会被编排器静默丢弃，
  // 导致"参考图传了但视频和图完全无关"。
  // 公网 http(s) 直链直接可用；本站公开 CDN 相对路径 /media/... 交给编排器解析为内部 MinIO key。
  if (firstUrl && (firstUrl.startsWith('http') || firstUrl.startsWith('data:'))) return firstUrl;
  if (firstUrl && firstUrl.startsWith('/media/')) return firstUrl;
  if (d.fileKey) {
    // 优先返回可外传的真实签名 URL（参考图需发给外部模型）；失败再退化为 blob 仅作显示。
    try {
      const pu = await getPresignedUrl(d.fileKey);
      if (pu) return pu;
    } catch {
      /* fallthrough */
    }
    try {
      return await getFileUrl(d.fileKey);
    } catch {
      return undefined;
    }
  }
  return undefined;
}

/** 取参考图的可读名称（文件名优先，其次 URL 末段），用于提示词中显式标注每张参考图。 */
function describeRef(node?: Node<PeaNodeData> | null): string {
  if (!node) return '';
  const meta = (node.data.meta ?? {}) as Record<string, string>;
  if (meta.fileName) return meta.fileName;
  const url = node.data.url || node.data.resultUrl || node.data.resultUrls?.[0];
  if (url) {
    try {
      const name = new URL(url).pathname.split('/').pop();
      if (name) return decodeURIComponent(name);
    } catch {
      /* ignore */
    }
  }
  return node.data.label || (node.data.kind === 'image' ? '图片' : '视频');
}

/**
 * 构建「参考图说明」块，拼到 prompt 最前面。
 * 多图时显式编号 + 角色区分（首图=主体，其余=风格/背景/构图），并加全局防混淆提示，
 * 让模型即使无法靠数组顺序对齐，也能按"文字描述的内容"自行匹配每张参考图，避免混淆。
 * 编号顺序与上传的 reference_images 数组顺序严格一致。
 */
function buildReferenceBlock(urls: string[], nameMap: Map<string, string>): string {
  if (urls.length === 0) return '';
  const lines: string[] = [];
  if (urls.length === 1) {
    const name = nameMap.get(urls[0]) || '参考图';
    lines.push(
      `【参考图】${name}：请严格保持该参考图中物体的款式、颜色、材质、形状、图案与原图完全一致；` +
      `仅允许调整其摆放位置、角度或所处场景，不得重新设计并改变其外观。`,
    );
  } else {
    lines.push(
      `【参考图清单】共 ${urls.length} 张，已随请求按序上传，请严格按编号分别使用：`,
    );
    urls.forEach((u, i) => {
      const name = nameMap.get(u) || `参考图${i + 1}`;
      lines.push(
        `【参考图 ${i + 1}】${name}：请准确识别图中物体的款式、颜色、材质、形状、图案与细节；` +
        `在生成时根据用户指令将该物体作为素材融入画面，保持其外观特征一致性。`,
      );
    });
  }
  return lines.join('\n');
}

/** 同步获取节点媒体首图 URL(缩略图展示用;仅 fileKey 场景会缺失,回退占位)。 */
function getNodeMediaUrlSync(node: Node<PeaNodeData>): string | undefined {
  const d = node.data;
  const urls = d.resultUrls?.length ? d.resultUrls : d.resultUrl ? [d.resultUrl] : [];
  return urls[0] || d.url;
}

const PLACEHOLDER_THUMB = 'https://placehold.co/40x40/1a1a1a/888?text=?';

const KIND_CFG: Record<string, KindCfg> = {
  text: { label: '文本', placeholder: '输入简短描述，AI 帮你改写为高质量图片/视频生成提示词', modelIcon: '✦' },
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

/**
 * 节点聊天 SSE 客户端 (文本节点, 轻量流):
 * POST /chat/stream, 解析 named SSE 事件 (meta/delta/done/error), 逐 delta 回调。
 */
async function streamNodeChat(opts: {
  nodeId: string;
  kind: string;
  prompt: string;
  model?: string;
  onMeta: (m: any) => void;
  onDelta: (t: string) => void;
  onDone: (d: any) => void;
  onError: (e: any) => void;
}): Promise<void> {
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('pea_token') : null;
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      nodeId: opts.nodeId,
      kind: opts.kind,
      prompt: opts.prompt,
      model: opts.model,
      idempotencyKey: `chat-${opts.nodeId}-${Date.now()}`,
    }),
  });
  if (!resp.ok || !resp.body) {
    let msg = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      msg = j?.message || msg;
    } catch {
      /* ignore */
    }
    opts.onError({ message: msg });
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';
    for (const part of parts) {
      let ev = '';
      let data = '';
      for (const line of part.split('\n')) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (!data) continue;
      let json: any = null;
      try {
        json = JSON.parse(data);
      } catch {
        continue;
      }
      if (ev === 'meta') opts.onMeta(json);
      else if (ev === 'delta') opts.onDelta(json.text ?? '');
      else if (ev === 'done') opts.onDone(json);
      else if (ev === 'error') opts.onError(json);
    }
  }
}

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

/* 浮层触发按钮的实时视口坐标 */
type TriggerRect = { left: number; top: number; width: number; bottom: number };

/**
 * 浮层锚点跟随：浮层打开期间每帧读取触发元素的实时 getBoundingClientRect，
 * 使弹出层随节点拖拽 / 画布平移缩放无缝跟随（修复：选择框不随节点移动）。
 * 仅当坐标（取整）变化时才 setState，静止时不触发重渲染，避免无谓开销。
 */
function useAnchoredRect(open: boolean, ref: React.RefObject<HTMLElement>): TriggerRect | null {
  const [rect, setRect] = useState<TriggerRect | null>(null);
  useEffect(() => {
    if (!open || !ref.current) {
      setRect(null);
      return;
    }
    let raf = 0;
    let last = '';
    const read = () => {
      const el = ref.current;
      if (el) {
        const r = el.getBoundingClientRect();
        const key = `${Math.round(r.left)}|${Math.round(r.top)}|${Math.round(r.width)}|${Math.round(r.bottom)}`;
        if (key !== last) {
          last = key;
          setRect({ left: r.left, top: r.top, width: r.width, bottom: r.bottom });
        }
      }
      raf = requestAnimationFrame(read);
    };
    raf = requestAnimationFrame(read);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ref]);
  return rect;
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

/* ──────────────── 比例/分辨率/视频参数弹出层（视口感知） ──────────────── */

interface AspectPickerPopupProps {
  rect: { left: number; top: number; width: number; bottom?: number };
  genType: 'image' | 'video';
  resolution: string;
  aspectRatio: string;
  onResolution: (v: string) => void;
  onAspectRatio: (v: string) => void;
  onClose: () => void;
  // ── 视频特有 ──
  duration?: string;
  audioEnabled?: boolean;
  genMode?: string;
  onDuration?: (v: string) => void;
  onAudio?: (v: boolean) => void;
  onGenMode?: (v: string) => void;
}

const AspectPickerPopup = forwardRef<HTMLDivElement, AspectPickerPopupProps>((props, ref) => {
  const {
    rect, genType, resolution, aspectRatio,
    onResolution, onAspectRatio, onClose,
    duration, audioEnabled, genMode,
    onDuration, onAudio, onGenMode,
  } = props;

  const isVideo = genType === 'video';
  // 视频面板更宽（5 个区域），图片面板保持紧凑
  const popupWidth = isVideo ? 240 : 200;
  const estimatedHeight = isVideo ? 440 : 260;
  const pos = usePopupPosition({ ...rect, bottom: (rect as any).bottom ?? rect.top + 160 }, estimatedHeight, popupWidth);

  // 视频比例选项：截图中顺序为 16:9 / 4:3 / 1:1 / 3:4 / 9:16 / 21:9
  const videoAspectRatios = ASPECT_RATIOS.filter((a) =>
    ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9'].includes(a.value),
  );
  const displayedRatios = isVideo ? videoAspectRatios : ASPECT_RATIOS;

  return (
      <div ref={ref} className="node-aspect-picker" style={{
        position: 'fixed', left: pos.left, top: pos.top, bottom: pos.bottom, width: popupWidth,
      }} role="dialog" aria-label={isVideo ? '视频参数设置' : '画幅设置'}>
      {/* ── 视频：生成方式 ── */}
      {isVideo && (
        <div className="aspect-section">
          <div className="aspect-label">生成方式</div>
          <div className="aspect-res-btns">
            {GEN_MODES.map((m) => (
              <button key={m.value} type="button"
                className={`aspect-res-btn${genMode === m.value ? ' active' : ''}`}
                onClick={() => onGenMode?.(m.value)}
                title={m.desc}
              >{m.label}</button>
            ))}
          </div>
        </div>
      )}
      {/* ── 比例（图片/视频共用） ── */}
      <div className="aspect-section">
        <div className="aspect-label">比例</div>
        <div className={`aspect-grid${isVideo ? ' aspect-grid-6col' : ''}`}>
          {displayedRatios.map((ar) => (
            <button key={ar.value} type="button"
              className={`aspect-ratio-btn${aspectRatio === ar.value ? ' active' : ''}`}
              onClick={() => onAspectRatio(ar.value)}
              title={`${ar.label} (${ar.w}×${ar.h})`}
            >
              <svg width="22" height="22" viewBox="0 0 28 28" fill="none">
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
      {/* ── 清晰度（视频用 480p/720p，图片用 1K/2K/3K） ── */}
      <div className="aspect-section">
        <div className="aspect-label">{isVideo ? '清晰度' : '画质'}</div>
        <div className="aspect-res-btns">
          {(isVideo ? VIDEO_RESOLUTIONS : RESOLUTIONS).map((r) => (
            <button key={r.value} type="button"
              className={`aspect-res-btn${resolution === r.value ? ' active' : ''}`}
              onClick={() => onResolution(r.value)}
            >{r.label}</button>
          ))}
        </div>
      </div>
      {/* ── 视频：生成时长 ── */}
      {isVideo && (
        <div className="aspect-section">
          <div className="aspect-label">生成时长</div>
          <div className="aspect-duration-grid">
            {DURATIONS.map((d) => (
              <button key={d} type="button"
                className={`aspect-duration-btn${duration === d ? ' active' : ''}`}
                onClick={() => onDuration?.(d)}
              >{d}</button>
            ))}
          </div>
        </div>
      )}
      {/* ── 视频：生成音频 ── */}
      {isVideo && (
        <div className="aspect-section">
          <div className="aspect-label">生成音频 <span className="aspect-hint" title="是否为视频生成背景音乐/音效">ⓘ</span></div>
          <div className="aspect-res-btns">
            <button type="button"
              className={`aspect-res-btn${audioEnabled ? ' active' : ''}`}
              onClick={() => onAudio?.(true)}
            >开启</button>
            <button type="button"
              className={`aspect-res-btn${!audioEnabled ? ' active' : ''}`}
              onClick={() => onAudio?.(false)}
            >关闭</button>
          </div>
        </div>
      )}
    </div>
  );
});
AspectPickerPopup.displayName = 'AspectPickerPopup';

export default function NodeChatPrompt() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const selectedId = useCanvas((s) => s.selectedId);
  // 必须在引用它的选择器（upstream）之前声明，避免 TDZ 崩溃
  // 关键修复：仅当「恰好选中 1 个节点」时才视为单选，否则为 null。
  // 之前的回退 selectedId 会在多选（框选）时让下方输入栏错误弹出（需求2：框选不应触发节点弹框）。
  const single = selectedIds.length === 1 ? selectedIds[0] : null;
  const nodes = useCanvas((s) => s.nodes);
  const canvasId = useCanvas((s) => s.canvasId);
  const update = useCanvas((s) => s.updateNodeData);
  const upstream = useCanvas((s) => (single ? s.getUpstreamInputs(single) : []));
  const push = useAgent((s) => s.push);
  const setOpen = useAgent((s) => s.setOpen);
  const draftKey = canvasId && single ? `pea:draft:${canvasId}:${single}` : null;

  const sel = single ? nodes.find((n) => n.id === single) : null;

  const inputRef = useRef<NodePromptInputRef>(null);
  const prevSingleRef = useRef<string | null>(null);
  // 按节点 id 缓存输入草稿：切换节点再切回时"接着上次编辑的内容继续写"
  const draftRef = useRef<Record<string, string>>({});
  // 回填 setHtml 期间为 true：抑制 setHtml 触发的 onChange 竞态（可能回传空文本）
  // 污染 store.meta.editorText / localStorage 草稿，导致刷新/重启后 prompt 被静默清空。
  const restoringRef = useRef(false);

  // 防抖持久化 editorText 到节点 meta：未提交时刷新页面也能恢复输入内容（修复视频/图片节点刷新丢失）。
  const persistEditorTextRef = useRef(
    debounce((id: string, html: string) => {
      const node = useCanvas.getState().nodes.find((n) => n.id === id);
      if (!node) return;
      const meta = { ...(node.data.meta ?? {}) } as Record<string, unknown>;
      const current = (meta.editorText as string | undefined) ?? '';
      if (current === html) return;
      useCanvas.getState().updateNodeData(id, { meta: { ...meta, editorText: html } }, false);
    }, 700),
  );

  // 通过 +「从画布选择参考」显式添加的图片/视频节点 id(也包含 @ 选择器插入的图片)
  const [referencedNodeIds, setReferencedNodeIds] = useState<string[]>([]);
  const [canvasPickMode, setCanvasPickMode] = useState(false);

  // ── 生成态（模型/参数/预估）──
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [modelId, setModelId] = useState('');
  const [tierVals, setTierVals] = useState<Record<string, string>>({});
  const [count, setCount] = useState(1);
  const [est, setEst] = useState<{ cost: number; allowed: boolean; minPlanLevel: number } | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // 同步锁:useState 在 React 18 自动批处理下,同一渲染周期内两次 onClick 仍可读到
  // submitting===false。useRef 跨渲染稳定,可作为"硬锁"确保 submit 不可重入。
  const submittingLockRef = useRef(false);
  const [hasInput, setHasInput] = useState(false);
  const [thumbUrls, setThumbUrls] = useState<Record<string, string>>({});
  const [launchClicked, setLaunchClicked] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  // 触发按钮的实时视口坐标（浮层打开期间每帧跟随节点移动）
  const triggerRect = useAnchoredRect(pickerOpen, chipRef);

  // 图片/视频节点：比例 / 分辨率 / 倍率浮层
  const [aspectOpen, setAspectOpen] = useState(false);
  // 默认画幅比例：跟随 store（默认 9:16），与新建节点框保持一致
  const [aspectRatio, setAspectRatio] = useState<string>(
    () => useCanvas.getState().defaultAspectRatio || '9:16',
  );
  const [resolution, setResolution] = useState('1k');
  // ── 视频特有参数 ──
  const [duration, setDuration] = useState('5s');
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [genMode, setGenMode] = useState('full_ref');
  const [countOpen, setCountOpen] = useState(false);
  const aspectRef = useRef<HTMLDivElement>(null);
  const countRef = useRef<HTMLDivElement>(null);
  // 弹窗单独持有 ref：不能和触发按钮共用 countRef，否则下拉挂载后 countRef.current
  // 会被覆盖成弹窗自身，useAnchoredRect 每帧读到的变成"下拉自己"的坐标 → 定位反馈
  // 循环、弹窗一路飞出屏幕（已修复：复用 countRef 导致的飞出 bug）。
  const countDropdownRef = useRef<HTMLDivElement>(null);
  const aspectBtnRef = useRef<HTMLButtonElement>(null);
  const aspectTriggerRect = useAnchoredRect(aspectOpen, aspectBtnRef);
  // 出图数触发按钮位置（Portal 定位用）
  const countTriggerRect = useAnchoredRect(countOpen, countRef);

  const kind = sel?.data.kind ?? 'text';
  const genType = GEN_TYPE[kind] ?? null;
  // 生成中状态：把「生成」按钮切换为可点击的「停止」按钮
  const isGenerating = !!sel?.data.generating;
  const data = sel?.data;
  // ── 编辑框显隐（需求：用户自己上传的素材节点，选中时不弹下方编辑框）──────────
  // 判定收敛在 lib/nodeSemantics.shouldHideNodeEditor（generating 时强制显示，
  // 以保住「停止」按钮入口 + 避免提示词随组件卸载丢失，历史回归见该函数注释）。
  const hideEditor = shouldHideNodeEditor(data);
  const selectedModel = models.find((m) => m.id === modelId) ?? null;
  const tiers = (selectedModel?.pricing as PricingRule | null)?.tiers ?? {};
  const dimKeys = Object.keys(tiers);
  const multiplier = (selectedModel?.pricing as PricingRule | null)?.multiplier ?? null;
  const params: Record<string, unknown> = { ...tierVals };
  // 图片节点：始终传递 n 参数（出图数量），即使模型没有 multiplier 字段
  // 这样后端和提供商适配器可以正确处理批量生成
  if (genType === 'image') {
    params.n = count;
  } else if (multiplier) {
    params[multiplier] = count;
  }

  // 图片/视频节点：把比例和分辨率映射为 width/height
  if (genType === 'image' || genType === 'video') {
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
        const url = ev.resultUrl ?? undefined;
        // 优先使用多图数组，兼容单图
        const urls = ev.resultUrls ?? (url ? [url] : undefined);
        useCanvas.getState().applyJobResult(ev.jobId, {
          generating: false,
          resultUrl: urls?.[0] ?? url,
          resultUrls: urls,
          resultIndex: 0,
        });
        useCanvas.getState().removeJob(ev.jobId);
        const count = urls?.length ?? 1;
        toast.success(count > 1 ? `生成完成，共 ${count} 张图` : '生成完成');
      } else if (ev.status === 'failed' || ev.status === 'refunded') {
        useCanvas.getState().applyJobResult(ev.jobId, {
          generating: false,
          error: ev.error || '生成失败',
          // 失败时清理旧结果，避免旧 resultUrl 导致 broken image 覆盖失败卡
          resultUrl: undefined,
          resultUrls: undefined,
          resultIndex: 0,
          savedToLibrary: false,
          isFavorite: false,
        });
        useCanvas.getState().removeJob(ev.jobId);
        toast.error(ev.error || '生成失败，已退款');
      } else {
        return;
      }
      // 任务进入终态 = 结算或退款已落账，同步一次余额。
      // 与 WS 的 balance.changed 幂等（都写服务端权威值），可防止两条事件先后到达时的展示错位。
      syncBalance();
    };
    window.addEventListener('pea:event', onEvent);
    return () => window.removeEventListener('pea:event', onEvent);
  }, []);

  // ── 节点切换：恢复该节点的草稿（优先）/已保存 prompt，否则清空 ──
  useEffect(() => {
    if (!single) {
      prevSingleRef.current = null;
      return;
    }
    if (single !== prevSingleRef.current) {
      prevSingleRef.current = single;
      const node = nodes.find((n) => n.id === single);
      // 还原编辑框优先级：本会话草稿 > localStorage（刷新未保存时）> 节点 meta.editorText。
      // 注意：不能用 node.data.prompt —— 那是「上游文本 + 用户文本」的合并结果，
      // 回填空会导致二次提交时上游文本被重复拼接。
      let lsDraft = '';
      try {
        lsDraft = draftKey ? (localStorage.getItem(draftKey) ?? '') : '';
      } catch {
        lsDraft = '';
      }
      // 修复：回填优先级必须用「真值」判断，不能用 ??。
      // ?? 只把 null/undefined 当空，会把 ''（空串草稿）当成有效值而短路，
      // 导致 localStorage 里那条空的 pea:draft 草稿遮住服务端持久化的 meta.editorText，
      // 表现为「MySQL 里 prompt 还在、但编辑器刷新/重启后变空白」。
      // 改用 || 并对空串做 trim 兜底：空串草稿不再阻断回退到 meta.editorText。
      const memDraft = draftRef.current[single];
      const memDraftNonEmpty = memDraft && memDraft.trim().length > 0 ? memDraft : '';
      const lsDraftNonEmpty = lsDraft && lsDraft.trim().length > 0 ? lsDraft : '';
      const restored =
        memDraftNonEmpty ||
        lsDraftNonEmpty ||
        (node?.data.meta?.editorText as string | undefined) ||
        // 兜底：本地草稿/editorText 都丢失，但节点本身有持久化 prompt，且无上游输入
        // （避免合并 prompt 含上游文本导致二次提交重复拼接）时，用 data.prompt 还原，
        // 确保生成中/刷新后编辑框绝不出现空框（提示词丢失幻觉）。
        (upstream.length === 0 ? (node?.data.prompt as string | undefined) : undefined) ||
        '';
      // 仅当 restored 是纯文本时才需要 escape；包含 <span data-pea-ref> 等 HTML 标签时直接作为 HTML 写入
      // （否则 token span 会被错误转义，以 `&lt;span&gt;` 形式显示为源码）。
      const isHtml = /<[a-z][^>]*data-pea-ref/i.test(restored) || /<br\b/i.test(restored);
      const html = isHtml
        ? restored
        : restored
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
      restoringRef.current = true;
      inputRef.current?.setHtml(html);
      // 抑制 setHtml 触发的 onChange 竞态（可能回传空文本）污染 store/localStorage
      setTimeout(() => { restoringRef.current = false; }, 200);
      // 强制计算 hasInput：setHtml 触发的 onChange 可能因 innerText 时序传回空文本，
      // 导致发送按钮等派生状态未刷新（修复图片节点刷新后按钮仍置灰）。
      const has =
        restored.replace(/<[^>]+>/g, '').trim().length > 0 || restored.includes('data-pea-ref');
      setHasInput(has);
      setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 60);
      // 恢复通过 + 选择器显式引用的节点 id
      const meta = (node?.data.meta ?? {}) as Record<string, unknown>;
      const saved = Array.isArray(meta.referencedNodeIds) ? (meta.referencedNodeIds as string[]) : [];
      setReferencedNodeIds(saved);
      setCanvasPickMode(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [single, nodes]);

  // ── 显式引用关系持久化到节点 meta(随画布保存) ──
  useEffect(() => {
    if (!single) return;
    const node = nodes.find((n) => n.id === single);
    const meta = (node?.data.meta ?? {}) as Record<string, unknown>;
    const saved = Array.isArray(meta.referencedNodeIds) ? (meta.referencedNodeIds as string[]) : [];
    if (JSON.stringify(saved) !== JSON.stringify(referencedNodeIds)) {
      update(single, { meta: { ...meta, referencedNodeIds } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referencedNodeIds, single]);

  // ── 断线回收：连线被删 / 上游节点被删时，同步清掉引用条缩略图与编辑器 @ token ──
  // store 侧已清理节点 meta（canvas.ts pruneDetachedRefs），此处负责让「当前正打开的输入框」
  // 立即跟随。必须同步本地 referencedNodeIds state，否则上面的持久化 effect 会把已断开的
  // 引用重新写回 meta；也必须清理草稿，否则恢复优先级(草稿 > localStorage > meta)会让 token 复活。
  useEffect(() => {
    const onDetached = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as
        | { targetId: string; removedRefIds: string[] }
        | undefined;
      if (!detail?.targetId || !detail.removedRefIds?.length) return;
      const kill = new Set(detail.removedRefIds);

      if (detail.targetId === single) {
        setReferencedNodeIds((prev) =>
          prev.some((id) => kill.has(id)) ? prev.filter((id) => !kill.has(id)) : prev,
        );
        inputRef.current?.removeRefTokens(detail.removedRefIds);
      }

      const cached = draftRef.current[detail.targetId];
      if (cached && cached.includes('data-pea-ref')) {
        const cleaned = stripRefTokens(cached, kill);
        if (cleaned !== cached) draftRef.current[detail.targetId] = cleaned;
      }
      if (canvasId) {
        try {
          const lsKey = `pea:draft:${canvasId}:${detail.targetId}`;
          const raw = localStorage.getItem(lsKey);
          if (raw && raw.includes('data-pea-ref')) {
            const cleaned = stripRefTokens(raw, kill);
            if (cleaned !== raw) localStorage.setItem(lsKey, cleaned);
          }
        } catch {
          /* localStorage 不可用时忽略，meta 已是干净的 */
        }
      }
    };
    window.addEventListener('pea:refs-detached', onDetached);
    return () => window.removeEventListener('pea:refs-detached', onDetached);
  }, [single, canvasId]);

  // ──「从画布选择参考」模式：点击图片/视频节点加入引用集合 ──
  useEffect(() => {
    if (!canvasPickMode || !single) return;
    const onClick = (e: MouseEvent) => {
      const nodeEl = (e.target as HTMLElement | null)?.closest('.react-flow__node') as HTMLElement | null;
      if (!nodeEl) return;
      const id = nodeEl.getAttribute('data-id');
      if (!id || id === single) return;
      const node = useCanvas.getState().nodes.find((n) => n.id === id);
      if (!node) return;
      // 允许图片/视频/文本三种节点的引用（图/视频作为参考图，文本作为 prompt 来源）
      if (node.data.kind !== 'image' && node.data.kind !== 'video' && node.data.kind !== 'text') {
        toast.info('请选择图片、视频或文本节点作为参考');
        return;
      }
      setReferencedNodeIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
      const kindLabel = node.data.kind === 'text' ? '文本' : node.data.kind === 'image' ? '图片' : '视频';
      toast.success(`已添加${kindLabel}参考`);
      // 阻止 ReactFlow 把选中态切到被点击节点,避免输入栏关闭
      e.preventDefault();
      e.stopImmediatePropagation();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCanvasPickMode(false);
    };
    document.addEventListener('click', onClick, true);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('click', onClick, true);
      window.removeEventListener('keydown', onKey);
    };
  }, [canvasPickMode, single]);

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
        // 图片/视频节点：还原比例/分辨率
        if (genType === 'image' || genType === 'video') {
          const fallbackRatio = genType === 'video' ? '16:9' : (useCanvas.getState().defaultAspectRatio || '9:16');
          setAspectRatio((gp.aspectRatio as string) || fallbackRatio);
          setResolution((gp.resolution as string) || (genType === 'video' ? '480p' : '2k'));
        }
        // 视频节点：还原时长/音频/生成方式
        if (genType === 'video') {
          setDuration((gp.duration as string) || '5s');
          setAudioEnabled(gp.audioEnabled === true || gp.audioEnabled === 'true');
          setGenMode((gp.genMode as string) || 'full_ref');
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

  // ── 节点类型切换时同步默认参数（图片↔视频切换时 resolution/duration 等需重置）──
  useEffect(() => {
    if (!single) return;
    if (genType === 'video') {
      setResolution((prev) => {
        const meta = (sel?.data.meta ?? {}) as Record<string, unknown>;
        const gp = (meta.genParams ?? {}) as Record<string, unknown>;
        return (gp.resolution as string) || '480p';
      });
      setDuration((prev) => {
        const meta = (sel?.data.meta ?? {}) as Record<string, unknown>;
        const gp = (meta.genParams ?? {}) as Record<string, unknown>;
        return (gp.duration as string) || '5s';
      });
      setAudioEnabled((prev) => {
        const meta = (sel?.data.meta ?? {}) as Record<string, unknown>;
        const gp = (meta.genParams ?? {}) as Record<string, unknown>;
        return gp.audioEnabled === true || gp.audioEnabled === 'true';
      });
      setGenMode((prev) => {
        const meta = (sel?.data.meta ?? {}) as Record<string, unknown>;
        const gp = (meta.genParams ?? {}) as Record<string, unknown>;
        return (gp.genMode as string) || 'full_ref';
      });
    }
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
      // 仅当点击落在「浮层内容」或「对应触发按钮」内部时才保持打开；
      // 其它任何点击（选中尺寸后点编辑框内、点节点本体、点画布、点页面其它区域）
      // 一律关闭浮层 —— 满足「超出选择框范围点击即可关闭」的需求。
      // 浮层本身通过 Portal + useAnchoredRect 实时跟随触发按钮，关闭不影响其定位。
      if (pickerRef.current?.contains(t) || chipRef.current?.contains(t)) return;
      if (aspectRef.current?.contains(t) || aspectBtnRef.current?.contains(t)) return;
      if (countRef.current?.contains(t) || countDropdownRef.current?.contains(t)) return;
      setPickerOpen(false);
      setAspectOpen(false);
      setCountOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setPickerOpen(false); setAspectOpen(false); setCountOpen(false); }
    };
  window.addEventListener('mousedown', onDoc, true);   // 捕获阶段：在 ReactFlow Pane 的 stopPropagation 之前触发
  window.addEventListener('keydown', onKey);
  return () => {
    window.removeEventListener('mousedown', onDoc, true);
    window.removeEventListener('keydown', onKey);
  };
  }, [pickerOpen, aspectOpen, countOpen]);

  // 编辑器不再用 rAF + getBoundingClientRect 做视口定位：它会被 portal 进选中节点内部的
  // .pea-node-editor-anchor，随节点平移无缝贴合，并通过 CSS counter-scale(var(--pea-inv-zoom))
  // 抵消画布缩放，保持屏幕恒定大小（详见 PeaNode.tsx / index.css）。

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
    // 同步到 store：新建节点时读取此值作为默认画幅比例
    useCanvas.getState().setDefaultAspectRatio(ar);
    // 同步到当前选中节点：① 写 data.aspectRatio 让空白节点框实时按新比例变化
    //                      ② 写 meta.genParams 供重新选中时还原
    if (single && (genType === 'image' || genType === 'video')) {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.aspectRatio = ar;
      update(single, { aspectRatio: ar, meta: { ...meta, genParams: gp } });
    }
    // 选中比例后【不】自动关闭浮层：让用户继续选分辨率/时长/音频，
    // 浮层由再次点击按钮 / 点击空白处 / Esc 关闭（修复：选尺寸后配置未完成浮层就退出）。
  }, [single, sel?.data.meta, genType, update]);

  const persistResolution = useCallback((res: string) => {
    setResolution(res);
    if (single && (genType === 'image' || genType === 'video')) {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.resolution = res;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  // ── 视频特有参数持久化 ──
  const persistDuration = useCallback((d: string) => {
    setDuration(d);
    if (single && genType === 'video') {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.duration = d;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  const persistAudio = useCallback((enabled: boolean) => {
    setAudioEnabled(enabled);
    if (single && genType === 'video') {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.audioEnabled = enabled;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  const persistGenMode = useCallback((mode: string) => {
    setGenMode(mode);
    if (single && genType === 'video') {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.genMode = mode;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  // 出图数量变更时立即持久化到节点 meta（修复切换节点后 count 回退问题）
  const persistCount = useCallback((v: number) => {
    setCount(v);
    if (single && genType === 'image') {
      const meta = { ...(sel?.data.meta ?? {}) } as Record<string, unknown>;
      const gp = { ...(meta.genParams as Record<string, unknown> ?? {}) };
      gp.n = v;
      update(single, { meta: { ...meta, genParams: gp } });
    }
  }, [single, sel?.data.meta, genType, update]);

  // 引用条数据源：上游连接的图片/视频节点 + 显式通过 + 添加的(去重)
  // 必须在 early-return 之前声明，否则非 null 渲染会比 null 渲染多 hooks，触发 React #310 崩溃
  const refIds = useMemo(() => {
    const ids: string[] = [];
    const add = (id: string) => { if (id && !ids.includes(id)) ids.push(id); };
    upstream.filter((n) => n.data.kind === 'image' || n.data.kind === 'video').forEach((n) => add(n.id));
    referencedNodeIds.forEach(add);
    return ids;
  }, [upstream, referencedNodeIds]);

  const refImageNodes = useMemo(() => {
    return refIds.map((id) => nodes.find((n) => n.id === id)).filter(Boolean) as Node<PeaNodeData>[];
  }, [refIds, nodes]);

  const hasUpstreamText = useMemo(() => {
    return upstream.some((n) => n.data.kind === 'text' && extractNodeText(n).length > 0);
  }, [upstream]);

  // 解析引用条缩略图 URL（fileKey 需要异步换签名 URL）
  // 用稳定 key 作依赖，避免 nodes 数组引用变化导致反复重解
  const refThumbKey = useMemo(
    () => refImageNodes.map((n) => `${n.id}:${n.data.fileKey || n.data.url || n.data.resultUrl || ''}`).join('|'),
    [refImageNodes],
  );
  useEffect(() => {
    let cancelled = false;
    const resolve = async () => {
      const map: Record<string, string> = {};
      await Promise.all(
        refImageNodes.map(async (n) => {
          const d = n.data;
          let url: string | undefined = d.url || d.resultUrl || d.resultUrls?.[0];
          if (!url && d.fileKey) {
            try {
              url = await getFileUrl(d.fileKey);
            } catch {
              url = undefined;
            }
          }
          map[n.id] = url || PLACEHOLDER_THUMB;
        }),
      );
      if (cancelled) return;
      setThumbUrls((prev) => {
        const same = Object.keys(map).length === Object.keys(prev).length
          && Object.entries(map).every(([k, v]) => prev[k] === v);
        return same ? prev : map;
      });
    };
    resolve();
    return () => { cancelled = true; };
  }, [refThumbKey]);

  // 锚定到选中节点的 DOM 容器（.pea-node-editor-anchor 由 PeaNode 渲染），
// 编辑框作为该节点的子元素随其平移，无需 rAF，零抖动。
// 每次渲染同步尝试定位 anchor：一旦锚点挂载，effect 即 setAnchorEl 触发重渲染补全 portal；
// 切换节点时若新锚点尚未挂载，保留上一帧的 anchorEl（不强制清空），避免编辑框闪烁/消失。
const [anchorEl, setAnchorEl] = useState<Element | null>(null);
const liveAnchor = single && typeof document !== 'undefined'
  ? (Array.from(document.querySelectorAll<HTMLElement>('.pea-node-editor-anchor')).find(
      (item) => item.getAttribute('data-pea-anchor') === single,
    ) ?? null)
  : null;
useEffect(() => {
  if (liveAnchor) {
    setAnchorEl(liveAnchor);
  } else if (!single) {
    setAnchorEl(null);
  }
}, [liveAnchor, single]);

// 编辑框「由显转隐」时立即落盘草稿。
// 场景：用户在空图片节点里先写了提示词，再点上传选了文件 → 节点变成上传态、编辑框收起，
// 而 onInputChange 的 700ms 防抖可能尚未触发，子树一卸载草稿就没了。
// 这里做一次同步写入 meta.editorText（不进历史栈），保证内容可在后续恢复。
const prevHideEditorRef = useRef(false);
useEffect(() => {
  const wasHidden = prevHideEditorRef.current;
  prevHideEditorRef.current = hideEditor;
  if (!hideEditor || wasHidden || !single) return;
  const html = draftRef.current[single];
  if (html == null) return;
  const node = useCanvas.getState().nodes.find((n) => n.id === single);
  if (!node) return;
  const meta = { ...(node.data.meta ?? {}) } as Record<string, unknown>;
  if ((meta.editorText as string | undefined) === html) return;
  useCanvas.getState().updateNodeData(single, { meta: { ...meta, editorText: html } }, false);
}, [hideEditor, single]);

  // 编辑框始终锚定在节点正下方（相对节点固定），不再根据视口落点翻转到节点上方。
  // 这样「上方功能条」（恒在节点上方）与「下方编辑框」（恒在节点下方）都相对节点固定、行为一致。
  // 若节点贴近视口底部导致编辑框被裁切，由画布平移（右键拖拽 / 滚轮）调整视图，而非改变相对位置。

  // hideEditor：用户自己上传的素材节点（image/video/audio/ref，非 AI 结果、非生成中）
  // 选中时不渲染下方编辑框。NodeChatPrompt 由 CanvasEditor 常驻挂载，这里 return null
  // 只卸载编辑框子树，组件自身的 draftRef 草稿仍在内存中，切回可生成节点即可续写。
  // cubeOpen：角度魔方模式激活时，编辑框由 AngleCubeOverlay 替代，此处不渲染。
  // 该状态来自 store.cubeOpenNodeId（单一数据源），不读 meta，避免关闭后误恢复。
  const cubeOpenNodeId = useCanvas((s) => s.cubeOpenNodeId);
  const cubeOpen = !!(sel && cubeOpenNodeId === sel.id);
  if (!sel || !single || !anchorEl || hideEditor || cubeOpen) return null;
  const cfg = KIND_CFG[kind] ?? KIND_CFG.text;

  const hasImageRefs = refImageNodes.length > 0;
  const canSend = hasInput || hasUpstreamText || hasImageRefs;

  const onTierChange = (dim: string, v: string) =>
    setTierVals((s) => ({ ...s, [dim]: v }));
  const onCountChange = (v: number) => {
    persistCount(Number.isFinite(v) && v >= 1 ? Math.min(8, Math.floor(v)) : 1);
  };

  const submit = async () => {
    // 同步锁优先于 setState 检查(React 18 批处理下,同周期两次点击 state 仍是 false)。
    if (submittingLockRef.current) return;
    if (submitting) return;
    submittingLockRef.current = true;
    try {
      if (!genType) {
        toast.info('音频生成即将开放，敬请期待');
        return;
      }

      const parsed = inputRef.current?.getParsed() ?? { text: '', referenceImages: [], referencedNodeIds: [], html: '' };
    const upstream = useCanvas.getState().getUpstreamInputs(single);
    const atReferencedIds = new Set(parsed.referencedNodeIds);

    // 引用集合：上游连接的 + 显式通过 + 添加的 + @ 选择器插入的(去重，保留顺序)
    // 同时支持图片/视频（reference_images）和文本（合并进 prompt）
    const refIds: string[] = [];
    const addRefId = (id: string) => { if (id && !refIds.includes(id)) refIds.push(id); };
    for (const n of upstream) {
      if (n.data.kind === 'image' || n.data.kind === 'video' || n.data.kind === 'text') addRefId(n.id);
    }
    for (const id of referencedNodeIds) addRefId(id);
    for (const id of parsed.referencedNodeIds) {
      const n = nodes.find((x) => x.id === id);
      if (n && (n.data.kind === 'image' || n.data.kind === 'video' || n.data.kind === 'text')) addRefId(id);
    }

    // 收集参考图 URL（仅 image/video 节点），按引用顺序构建，并附带可读名称用于提示词编排。
    // 上传图经 getPresignedUrl 解析为真实可外传签名 URL（blob 会被编排器丢弃，导致"参考图没上传"）。
    const referenceImages: string[] = [];
    const refNameMap = new Map<string, string>();
    const refNumberById = new Map<string, number>();
    const addRef = (url: string | undefined, name: string, id?: string) => {
      if (!url) return;
      let num = referenceImages.indexOf(url);
      if (num === -1) {
        referenceImages.push(url);
        num = referenceImages.length - 1;
        refNameMap.set(url, name || `参考图${referenceImages.length}`);
      }
      if (id && !refNumberById.has(id)) refNumberById.set(id, num + 1);
    };
    for (const id of refIds) {
      const n = nodes.find((x) => x.id === id);
      if (!n) continue;
      if (n.data.kind !== 'image' && n.data.kind !== 'video') continue;
      const url = await resolveUpstreamMediaUrl(n);
      addRef(url, describeRef(n), n.id);
    }
    // 兜底：@ 选择器可能直接解析出 URL（未必能映射到节点），也并入并去重
    for (const url of parsed.referenceImages) {
      const n = nodes.find((x) => {
        const u = [x.data.url, x.data.resultUrl, ...(x.data.resultUrls || [])];
        return u.includes(url);
      });
      addRef(url, describeRef(n), n?.id);
    }

    // 自动合并文本节点内容：① 上游连接的文本(排除已在 @ 中显式引用的，避免重复)
    //                      ② 显式通过 + 添加的文本节点(来自 + 按钮)
    const autoTextParts: string[] = [];
    const addedTextIds = new Set<string>();
    for (const n of upstream) {
      if (atReferencedIds.has(n.id)) continue;
      if (n.data.kind === 'text') {
        const txt = extractNodeText(n);
        if (txt) { autoTextParts.push(txt); addedTextIds.add(n.id); }
      }
    }
    // 防止上游文本被 + 引用重复合并（atReferencedIds 已在 NodePromptInput 解析时建立）
    for (const id of referencedNodeIds) {
      if (addedTextIds.has(id) || atReferencedIds.has(id)) continue;
      const n = nodes.find((x) => x.id === id);
      if (n && n.data.kind === 'text') {
        const txt = extractNodeText(n);
        if (txt) { autoTextParts.push(txt); addedTextIds.add(id); }
      }
    }

    // 参考图提示词编排：多图时显式编号，避免模型混淆；单图时强调"主体严格一致"。
    // 说明块按数组顺序与上传的 reference_images 一一对应。
    const refBlock = buildReferenceBlock(referenceImages, refNameMap);
    // 正文：把 @ 的媒体 token 替换为「参考图N」，与说明块编号一致，让模型精确对应。
    const bodyWithRefs = inputRef.current?.getBodyText(refNumberById) ?? parsed.text;
    const parts: string[] = [];
    if (refBlock) parts.push(refBlock);
    if (autoTextParts.length) parts.push(autoTextParts.join('\n'));
    if (bodyWithRefs) parts.push(bodyWithRefs);
    const finalPrompt = parts.join('\n\n').trim();

    if (!finalPrompt && referenceImages.length === 0) {
      toast.info('请输入描述或连接上游节点');
      return;
    }

    // 先持久化用户输入：合并后的 prompt + reference_images 写入节点（随画布保存）。
    // 该步骤与「能否发起生成」无关——即使套餐不可用，用户的引用关系也已正确落库，
    // 选好模型/升级套餐后即可直接重试，不会丢失已拼接的多图引用与文本输入。
    const extraMeta: Record<string, unknown> = {};
    if (genType === 'image' || genType === 'video') { extraMeta.aspectRatio = aspectRatio; extraMeta.resolution = resolution; }
    if (genType === 'video') { extraMeta.duration = duration; extraMeta.audioEnabled = audioEnabled; extraMeta.genMode = genMode; }
    const mergedParams = { ...params };
    if (referenceImages.length) mergedParams.reference_images = referenceImages;
    // 视频特有参数写入提交参数
    if (genType === 'video') {
      if (duration) mergedParams.duration = duration;
      mergedParams.audio_enabled = audioEnabled;
      if (genMode) mergedParams.gen_mode = genMode;
    }
    const metaPatch: Record<string, unknown> = { genParams: mergedParams, ...extraMeta };
    if (modelId) metaPatch.modelId = modelId;
    // 持久化「用户自己的编辑框内容」(完整 HTML，含 @ 引用 token)，独立于合并后的 prompt。
    // 必须存完整 HTML 而非纯文本——否则 @ 引用 token 会在刷新后丢失，
    // 导致重新打开编辑框时 @ 的图片消失、且发送时 reference_images 为空、生成不参考该图片。
    metaPatch.editorText = parsed.html || parsed.text;
    update(single, {
      prompt: finalPrompt,
      params: mergedParams,
      meta: { ...(sel.data.meta ?? {}), ...metaPatch },
    });
    // 立即落盘：确保用户写的 prompt 立刻写库，不再依赖 1s 防抖 autosave——
    // 生成任务耗时数分钟，期间刷新/切走会让防抖保存被取消，prompt 永久丢失（已复现）。
    // 关键修复：saveCanvasNow 现在返回是否真落盘。仅当确认真实落盘后，才清除 localStorage
    // 兜底草稿；若落盘失败（如乐观锁 409 且重试仍失败），务必保留草稿，否则退出重进后
    // 编辑框空白（"刷新丢 prompt 且草稿也没了" 的真空，已复现）。
    const saved = await useCanvas.getState().saveCanvasNow();
    if (saved && draftKey) {
      try {
        localStorage.removeItem(draftKey);
      } catch {
        /* ignore */
      }
    } else if (!saved) {
      console.warn('[submit] 落盘未成功，保留 localStorage 兜底草稿，避免 prompt 丢失');
    }

    // 以下为实际生成接入：需要模型可用
    if (!modelId || !selectedModel) {
      toast.error('暂无可用模型，已保存草稿，请配置模型后再生成');
      return;
    }
    if (est && !est.allowed) {
      toast.error(`该模型需要更高套餐（权益等级 ≥ ${est.minPlanLevel}），已保存草稿`);
      return;
    }

    // 文本节点：轻量 SSE 聊天流（润色用户输入为提示词，回写节点内容区）
    if (genType === 'text') {
      push('user', `[${sel.data.label || cfg.label}] ${finalPrompt}`);
      setSubmitting(true);
      // 文本节点也必须进入生成态，让发送按钮切换为「停止」态，否则用户无法感知任务正在运行。
      update(single, { generating: true, error: undefined });
      let acc = '';
      try {
        await streamNodeChat({
          nodeId: single,
          kind: 'text',
          prompt: finalPrompt,
          model: modelId,
          onMeta: (m) => {
            // 优先使用前端预估的 est.cost，确保按钮展示与提示消耗一致。
            if (est?.cost != null) toast.success(`已受理，预估 ${est.cost} Tapies`);
            else if (m.costTapies != null) toast.success(`已受理，预估 ${m.costTapies} Tapies`);
            else toast.success('已受理');
          },
          onDelta: (txt) => {
            acc += txt;
            update(single, { html: acc });
          },
          onDone: () => {
            update(single, { generating: false });
            toast.success('提示词已生成');
          },
          onError: (e) => {
            update(single, { generating: false });
            toast.error(e?.message || '生成失败');
          },
        });
      } catch (e: any) {
        update(single, { generating: false });
        toast.error(e?.message || '聊天失败');
      } finally {
        setSubmitting(false);
        submittingLockRef.current = false;
      }
      return;
    }

    // 图片/视频：现有 WS 任务流
    push('user', `[${sel.data.label || cfg.label}] ${finalPrompt}`);
    setSubmitting(true);
    try {
      const res = await acceptNodeGenerationJob({
        type: genType,
        prompt: finalPrompt,
        model: modelId,
        params: mergedParams,
        priority: 'normal',
        idempotencyKey: `gen-${single}-${Date.now()}`,
      });
      useCanvas.getState().registerJob(res.jobId, single);
      update(single, {
        generating: true,
        error: undefined,
        // 新请求发起时清理旧结果，避免重试/二次生成时仍显示上次失败的图片
        resultUrl: undefined,
        resultUrls: undefined,
        resultIndex: 0,
        savedToLibrary: false,
        isFavorite: false,
        lastJobId: res.jobId,
      });
      toast.success(referenceImages.length ? `已受理，含 ${referenceImages.length} 张参考图` : '已受理，生成中…');
      // 轮询兜底：WS 事件若丢失，保证长任务结果仍回填到节点
      pollNodeJobResult(res.jobId);
      setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 0);
    } catch (e: any) {
      // 受理失败 (HTTP 4xx/5xx/网络) —— 节点不能卡在 generating=true,
      // 否则 HUD 4 角 + 中心 TechLoader 一直转. 同时写 error 给失败卡显示.
      const msg = e?.response?.data?.message || e?.message || '受理失败，请重试';
      update(single, { generating: false, error: msg });
      toast.error(msg);
    } finally {
      setSubmitting(false);
      submittingLockRef.current = false;
    }
    } catch (e) {
      // 兜底:任何未预期的异常都释放同步锁,避免按钮永久卡死。
      // (具体业务异常已被上文各自的 try/catch 捕获,这里只是防意外。)
      // eslint-disable-next-line no-console
      console.error('[submit] unexpected error:', e);
    } finally {
      submittingLockRef.current = false;
    }
  };

  // 生成中点击按钮 → 停止当前生成：释放节点生成态，让用户能重新编辑/再次生成。
  // 该处理器刻意不依赖 submitting / canSend / genType，确保生成中按钮始终可点击、始终有效。
  const cancelGeneration = () => {
    if (!single) return;
    update(single, { generating: false, error: undefined });
  };

  const onInputChange = (html: string, plainText: string) => {
    // 回填期间的 setHtml 竞态回调：直接忽略，避免空文本回落污染 store/localStorage
    if (restoringRef.current) return;
    if (single) {
      draftRef.current[single] = html;
      // 防抖持久化 editorText 到节点 meta（随画布保存）
      persistEditorTextRef.current(single, html);
      // 同时写入 localStorage：未保存到后端前刷新页面也能恢复（修复视频/图片节点输入丢失）。
      try {
        // 不写空串草稿：回填 setHtml 触发的 onChange 竞态可能传回空文本，
        // 若写进 localStorage 会污染 pea:draft，导致下次重载被空草稿遮住服务端 prompt。
        if (draftKey && html && html.trim().length > 0) localStorage.setItem(draftKey, html);
      } catch {
        /* 隐私模式等场景可能禁用 localStorage */
      }
    }
    const has = plainText.trim().length > 0 || html.includes('data-pea-ref');
    setHasInput(has);
    // 注意：清空内容时不要 delete draftRef[single]，保留为空字符串。
    // 否则 initialHtml 会回退到 sel.data.meta.editorText（旧 prompt），
    // 编辑器会被旧文本重新顶回来（用户反馈的「删光文本又全冒出来」）。
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

  const editorRoot = (
    <div
      className="node-input-bar node-chat-prompt nodrag nopan placed-below"
      role="dialog"
      aria-label={`对 ${cfg.label} 节点提问`}
      data-kind={kind}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* 「从画布选择参考」顶部提示条 */}
      {canvasPickMode && createPortal(
        <div className="node-canvas-pick-bar">
          <div className="node-canvas-pick-inner">
            <span className="node-canvas-pick-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
              从画布选择参考
            </span>
            <button
              type="button"
              className="node-canvas-pick-exit"
              onClick={() => setCanvasPickMode(false)}
            >
              退出
            </button>
          </div>
        </div>,
        document.body,
      )}

      {/* 引用条：✦ + 已引用节点（图片/视频显示缩略图，文本显示文本图标）+ + */}
      <div className="node-ref-bar">
        <button type="button" className="node-ref-tool" title="特效/灵感" aria-label="特效">✦</button>
        <div className="node-ref-thumbs">
          {refImageNodes.map((n) => {
            const isText = n.data.kind === 'text';
            const textSummary = isText
              ? (n.data.html || n.data.prompt || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().slice(0, 36) || '空文本'
              : '';
            return (
              <div
                key={n.id}
                className={`node-ref-thumb${isText ? ' node-ref-thumb-text' : ''}`}
                title={isText ? `文本：${textSummary}` : (n.data.label || '参考图')}
                data-ref-kind={n.data.kind}
              >
                {isText ? (
                  <span className="node-ref-text-icon" aria-hidden>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="5" y1="7" x2="19" y2="7" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                      <line x1="5" y1="17" x2="13" y2="17" />
                    </svg>
                  </span>
                ) : n.data.kind === 'video' ? (
                  <VideoRefThumb url={thumbUrls[n.id]} label={n.data.label || '视频'} />
                ) : (
                  <img
                    src={thumbUrls[n.id] || PLACEHOLDER_THUMB}
                    alt=""
                    loading="lazy"
                    onError={(e) => { e.currentTarget.src = PLACEHOLDER_THUMB; }}
                  />
                )}
                <button
                  type="button"
                  className="node-ref-remove"
                  title="移除该引用"
                  aria-label="移除该引用"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setReferencedNodeIds((prev) => prev.filter((x) => x !== n.id));
                  }}
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            );
          })}
        </div>
        <button
          type="button"
          className={`node-ref-tool${canvasPickMode ? ' active' : ''}`}
          title="从画布选择参考"
          aria-label="从画布选择参考"
          aria-pressed={canvasPickMode}
          onClick={() => setCanvasPickMode((v) => !v)}
        >
          +
        </button>
      </div>

      {/* 输入框（富文本，支持 @ 引用上游节点） */}
      <NodePromptInput
        ref={inputRef}
        nodeId={single}
        kind={kind as PeaNodeKind}
        placeholder={cfg.placeholder}
        initialHtml={draftRef.current[single] ?? (sel.data.meta?.editorText as string | undefined) ?? ''}
        onChange={onInputChange}
        onSubmit={submit}
        onInsertReference={(id) => {
          setReferencedNodeIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
        }}
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
                // 位置由 useAnchoredRect 每帧实时跟随，这里只需切换开关
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

          {/* 图片/视频节点：比例·分辨率 选择器（图片 "9:16 · 2K" / 视频 "全能参考 · 16:9 · 480p · 5s · 🎵"） */}
          {(genType === 'image' || genType === 'video') && (
            <>
              <button
                ref={aspectBtnRef}
                type="button"
                className="node-input-aspect-chip"
                title={
                  genType === 'video'
                    ? `${GEN_MODES.find(m => m.value === genMode)?.label ?? genMode} · ${aspectRatio} · ${resolution.toUpperCase()} · ${duration}${audioEnabled ? ' · 音频开启' : ''}`
                    : `比例 ${aspectRatio} · 分辨率 ${resolution.toUpperCase()}`
                }
                aria-haspopup="dialog"
                aria-expanded={aspectOpen}
                onClick={() => {
                  // 位置由 useAnchoredRect 每帧实时跟随，这里只需切换开关
                  setAspectOpen((v) => !v);
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1.5" y="2.5" width="11" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><line x1="1.5" y1="5.5" x2="12.5" y2="5.5" stroke="currentColor" strokeWidth="1.3"/></svg>
                <span>
                  {genType === 'video'
                    ? `${GEN_MODES.find(m => m.value === genMode)?.label ?? genMode} · ${aspectRatio} · ${resolution.toUpperCase()} · ${duration}${audioEnabled ? ' · 🎵' : ''}`
                    : `${aspectRatio} · ${resolution.toUpperCase()}`
                  }
                </span>
                <svg className="node-model-chip-arrow" width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>

              {/* 倍率/数量选择已移至右侧消耗量前（按钮化），此处不再重复展示 */}
            </>
          )}

          {/* 通用 tier 参数（仅非图片/视频节点展示；图片/视频节点的参数已通过比例·分辨率芯片表达） */}
          {(genType !== 'image' && genType !== 'video') && dimKeys.map((d) => (
            <span key={d} className="node-input-param" title={d}>
              <span className="node-input-param-icon" aria-hidden>⚙</span>
              <span>{tierVals[d] ?? '—'}</span>
            </span>
          ))}
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
                onClick={() => {
                  // 位置由 useAnchoredRect 每帧实时跟随，这里只需切换开关
                  setCountOpen((v) => !v);
                }}
              >
                {count}x
              </button>
              {/* hover 提示 "生成数量" */}
              <span className="node-count-btn-hint" aria-hidden>生成数量</span>
            </div>
          )}
          <span
            className={`pe-launcher${submitting ? ' submitting' : ''}${isGenerating ? ' is-stopping' : ''}${(!canSend && !isGenerating) ? ' disabled' : ''}${launchClicked ? ' clicked' : ''}`}
            title={isGenerating ? '停止生成' : (submitting ? '正在生成…' : `本次预计消耗 ${costLabel} Tapies`)}
            aria-label={isGenerating ? '停止生成' : (submitting ? '正在生成' : '发送')}
            aria-busy={submitting}
            style={{ pointerEvents: 'auto', cursor: isGenerating ? 'pointer' : (!canSend || submitting ? 'not-allowed' : 'pointer') }}
            onClick={() => {
              if (isGenerating) {
                cancelGeneration();
              } else if (canSend && !submitting) {
                setLaunchClicked(true);
                setTimeout(() => setLaunchClicked(false), 320);
                submit();
              }
            }}
          >
            {/* 左侧: 消耗数字 (无图标 / 无单位标签)；生成中显示「停止」文案 */}
            <span className="pe-cost">
              <span className="pe-cost-num">{isGenerating ? '停止' : costLabel}</span>
            </span>

            {/* 右侧: 默认「生成核心」(火花+粒子) / 生成中「停止方块」 */}
            <span className="pe-trigger">
              {isGenerating ? (
                <svg className="pe-stop-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
                  <rect x="7" y="7" width="10" height="10" rx="2.5" fill="#FFFFFF" />
                </svg>
              ) : (
                <svg className="pe-gen-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
                  <defs>
                    <linearGradient id="pea-gen-spark" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#FFFFFF"/>
                      <stop offset="100%" stopColor="#7DDDFF"/>
                    </linearGradient>
                    <linearGradient id="pea-gen-spark-light" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#FFFFFF"/>
                      <stop offset="100%" stopColor="#3B9EFF"/>
                    </linearGradient>
                  </defs>
                  {/* 中心火花核心: 象征「生成 / 创造」 */}
                  <path className="pe-gen-spark" d="M12 3 L13.4 10.6 L21 12 L13.4 13.4 L12 21 L10.6 13.4 L3 12 L10.6 10.6 Z" fill="url(#pea-gen-spark)"/>
                  {/* 轨道粒子: 环绕翻动 */}
                  <g className="pe-gen-particles">
                    <circle className="pe-particle p1" cx="12" cy="2.5" r="1.4" fill="#7DDDFF"/>
                    <circle className="pe-particle p2" cx="21.5" cy="12" r="1.4" fill="#BFE9FF"/>
                    <circle className="pe-particle p3" cx="12" cy="21.5" r="1.4" fill="#7DDDFF"/>
                    <circle className="pe-particle p4" cx="2.5" cy="12" r="1.4" fill="#BFE9FF"/>
                  </g>
                </svg>
              )}
            </span>
          </span>
        </div>
      </div>

      {/* ═════════ 卡片式模型选择浮层（参考截图2/3）═════════════ */}
      {/* 使用 Portal 渲染到 body，避免被父元素的 transform 影响 fixed 定位 */}
      {pickerOpen && genType && triggerRect && createPortal(
        <div data-pea-canvas-portal>
        <ModelPickerPopup
          ref={pickerRef}
          rect={triggerRect}
          models={models}
          modelId={modelId}
          selectedModel={selectedModel}
          est={est}
          onPick={(id) => { if (models.find(m => m.id === id)?.allowed) { onModelChange(id); setPickerOpen(false); } }}
          onClose={() => setPickerOpen(false)}
        />
        </div>,
        document.body
      )}

      {/* ═════════ 图片/视频比例/参数浮层 ══════════════ */}
      {aspectOpen && (genType === 'image' || genType === 'video') && aspectTriggerRect && createPortal(
        <div data-pea-canvas-portal>
        <AspectPickerPopup
          ref={aspectRef}
          rect={aspectTriggerRect}
          genType={genType as 'image' | 'video'}
          resolution={resolution}
          aspectRatio={aspectRatio}
          onResolution={persistResolution}
          onAspectRatio={persistAspect}
          onClose={() => setAspectOpen(false)}
          // ── 视频特有 ──
          duration={duration}
          audioEnabled={audioEnabled}
          genMode={genMode}
          onDuration={persistDuration}
          onAudio={persistAudio}
          onGenMode={persistGenMode}
        />
        </div>,
        document.body
      )}

      {/* ═════════ 出图数量下拉（Portal 渲染到 body，避免被父容器裁剪）═════════════ */}
      {countOpen && countTriggerRect && createPortal(
        <div
          ref={countDropdownRef}
          data-pea-canvas-portal
          className="node-count-btn-dropdown"
          style={{
            position: 'fixed',
            left: Math.max(10, Math.min(countTriggerRect.left + countTriggerRect.width / 2 - 40, window.innerWidth - 90)), // 居中，夹紧边界
            bottom: window.innerHeight - (countTriggerRect.bottom - 10),   // 弹窗底边 = 按钮底边上方 gap=10（与模型/比例一致）
            top: 'auto',
            width: 80,
          }}
          role="listbox"
          aria-label="生成数量"
          onClick={(e) => e.stopPropagation()}
        >
          {COUNT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`node-count-opt${count === opt.value ? ' active' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                onCountChange(opt.value);
                setCountOpen(false);
              }}
              title={`生成 ${opt.value} 张图`}
            >
              {opt.label}
            </button>
          ))}
        </div>,
        document.body
      )}


    </div>
  );

  return createPortal(editorRoot, anchorEl);
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 引用条视频缩略图：hover 时自动播放并弹出预览浮层，避免视频 URL 被当成图片显示问号。
 * ═════════════════════════════════════════════════════════════════════════════ */
function VideoRefThumb({ url, label }: { url?: string; label: string }) {
  const thumbRef = useRef<HTMLVideoElement>(null);
  const [showPopover, setShowPopover] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const handleEnter = (e: React.MouseEvent) => {
    thumbRef.current?.play().catch(() => {});
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = 220;
    const height = 150;
    let left = rect.left + rect.width / 2 - width / 2;
    let top = rect.bottom + 10;
    if (left + width > vw - 12) left = vw - width - 12;
    if (left < 12) left = 12;
    if (top + height > vh - 12) top = rect.top - height - 10;
    setPos({ left, top });
    setShowPopover(true);
  };

  const handleLeave = () => {
    thumbRef.current?.pause();
    setShowPopover(false);
  };

  if (!url) {
    return <span className="pea-ref-picker-icon pea-ref-picker-thumb-fallback">🎬</span>;
  }

  return (
    <>
      <video
        ref={thumbRef}
        className="node-ref-thumb-video"
        src={url}
        muted
        loop
        playsInline
        preload="metadata"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
      />
      {showPopover && pos && createPortal(
        <div
          className="pea-ref-video-popover"
          data-pea-canvas-portal
          style={{ left: pos.left, top: pos.top, position: 'fixed', zIndex: 120 }}
          onMouseEnter={() => setShowPopover(true)}
          onMouseLeave={() => setShowPopover(false)}
        >
          <div className="pea-ref-video-popover-tag">
            <span>@Video</span>
            <span className="pea-ref-video-popover-label">{label}</span>
          </div>
          <video
            className="pea-ref-video-popover-player"
            src={url}
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
          />
          <div className="pea-ref-video-popover-toolbar">
            <button type="button" title="全屏" aria-label="全屏" onClick={() => {
              const el = document.querySelector('.pea-ref-video-popover-player') as HTMLVideoElement | null;
              el?.requestFullscreen?.().catch(() => {});
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
            </button>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
