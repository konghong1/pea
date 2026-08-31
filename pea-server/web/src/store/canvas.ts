import { create } from 'zustand';
import {
  Edge,
  Node,
  Connection,
  EdgeChange,
  NodeChange,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from 'reactflow';
import { api } from '../api/client';
import { PeaNodeKind } from '../constants/nodeTypes';
import { useUi } from './ui';
import { wireAsUpstream } from '../lib/cropWire';

export type PeaNodeData = {
  label: string;
  kind: PeaNodeKind;
  prompt?: string;
  html?: string;
  url?: string;           // 用户上传的文件 URL（blob 或解析后的签名 URL）
  fileKey?: string;       // 上传到 MinIO 的持久化 key（u:{userId}/uploads/...），渲染时换签名下载 URL
  resultUrl?: string;     // 模型生成的结果 URL（图片/视频等，兼容旧数据）
  resultUrls?: string[];  // 模型生成的多张结果 URL（image 节点支持多图）
  resultIndex?: number;   // 当前展示 resultUrls 中的第几张
  savedToLibrary?: boolean; // 是否已通过「保存到素材库」导入
  isFavorite?: boolean;   // 是否已通过左上角星标「收藏」
  generating?: boolean;   // 是否正在生成中
  /** 最近一次生成任务的 jobId（受理成功后写入）。
   *  关键：用于加载画布时与后端核对真实状态，防止 WS 事件丢失后节点永远卡在 generating。 */
  lastJobId?: string;
  /** 裁剪产物节点标记：需要显示左侧输入 handle 以接收来自源节点的连线，
   *  但仍保留上传媒体的替换按钮语义。 */
  clipped?: boolean;
  error?: string;         // 生成失败原因（终态写回节点，用于节点内失败卡展示）
  /** 新建节点时的画幅比例（如 "9:16"、"16:9"），用于空白节点框比例。
      有内容后节点按实际媒体比例包裹，此字段不再影响显示。 */
  aspectRatio?: string;
  params?: Record<string, unknown>; // 生成参数（模型、分辨率、比例等，供 lightbox 信息面板展示）
  meta?: Record<string, unknown>;
};

/**
 * 把内存中的画布节点/边序列化为可持久化的最小结构。
 * 与 openCanvas 口径一致：保留完整 data（含 prompt/params），不裁剪字段。
 * 同时供 CanvasEditor 的 autosave / flushSave 与 store 的 saveCanvasNow 复用，避免逻辑分叉。
 */
export function cleanGraph(
  nodes: Node<PeaNodeData>[],
  edges: Edge[],
): { nodes: any[]; edges: any[] } {
  return {
    nodes: nodes.map((n) => {
      const base: Record<string, unknown> = {
        id: n.id,
        type: n.type || 'pea',
        position: n.position,
        data: n.data,
      };
      if (n.type === 'group') {
        base.parentNode = n.parentNode;
        base.extent = n.extent;
        base.style = n.style ? { width: n.style.width, height: n.style.height } : undefined;
      }
      if (n.parentNode) {
        base.parentNode = n.parentNode;
        base.extent = n.extent;
      }
      return base;
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? null,
      targetHandle: e.targetHandle ?? null,
      type: e.type || 'pea',
    })),
  };
}

interface CanvasState {
  canvasId: number | null;
  version: number;
  title: string;
  nodes: Node<PeaNodeData>[];
  edges: Edge[];
  selectedId: string | null;
  selectedIds: string[];
  /** 当前打开角度魔方面板的节点 id（单一数据源，避免节点重挂载后误恢复面板）。 */
  cubeOpenNodeId: string | null;
  /** 设置/清除当前打开角度魔方的节点（null = 关闭面板）。 */
  setCubeOpenNodeId: (id: string | null) => void;
  dirty: boolean;
  lastSavedAt: number | null;
  saveCount: number;
  clipboard: Node<PeaNodeData> | null;
  /** 新建节点时的默认画幅比例（由编辑框比例选择器同步）。
      图片节点默认 "9:16"，视频节点默认 "16:9"。 */
  defaultAspectRatio: string;
  /** 更新默认画幅比例（编辑框切换比例时调用）。 */
  setDefaultAspectRatio: (ratio: string) => void;
  /** 生成任务 jobId -> 触发节点 id，用于把异步生成结果回写到对应节点。 */
  jobNodeMap: Record<string, string>;
  /** 登记一次生成任务与其触发节点，供 WS job.updated 事件回写结果。 */
  registerJob: (jobId: string, nodeId: string) => void;
  /** 加载画布后异步核对：把 generating=true 的节点按后端真实状态回填。 */
  reconcileGeneratingNodes: () => Promise<void>;
  /** 按 jobId 把生成结果/状态 patch 回写到对应节点（自动查 jobNodeMap）。 */
  applyJobResult: (jobId: string, patch: Partial<PeaNodeData>) => void;
  /** 任务终态后清理 jobNodeMap 登记。 */
  removeJob: (jobId: string) => void;

  setCanvasMeta: (id: number, version: number, title?: string) => void;
  onNodesChange: (c: NodeChange[]) => void;
  onEdgesChange: (c: EdgeChange[]) => void;
  onConnect: (c: Connection) => void;
  removeEdge: (id: string) => void;
  addNode: (data: PeaNodeData, position: { x: number; y: number }) => string;
  updateNodeData: (id: string, patch: Partial<PeaNodeData>, recordHistory?: boolean) => void;
  select: (id: string | null) => void;
  toggleSelect: (id: string) => void;
  setSelection: (ids: string[]) => void;
  // 框选「覆盖即选中」二次校正：用 CanvasEditor 在 mouseup 时算好的完整选区 rect
  // （window.__lastSelRect，屏幕坐标→画布坐标）做 partial-intersection，把被覆盖但 RF 漏选的节点补进 selectedIds。
  // 方向：只补不删（不打断 shift 反向框选）。
  correctBoxSelection: () => void;
  clearSelection: () => void;
  markSaved: (version: number) => void;
  loadGraph: (nodes: Node<PeaNodeData>[], edges: Edge[], version: number) => void;
  openCanvas: (id: number) => Promise<void>;
  removeNode: (id: string) => void;
  /** 批量删除节点（含组及其子节点的级联清理），合并为单条撤销项。 */
  removeNodes: (ids: string[]) => void;
  duplicateNode: (id: string) => void;
  addConnected: (fromId: string) => void;
  copySelected: () => void;
  pasteNode: () => void;
  bumpSave: () => void;
  /** 获取某节点的直接上游输入节点（按边建立顺序排序）。 */
  getUpstreamInputs: (nodeId: string) => Node<PeaNodeData>[];
  /** 立即落盘（非防抖）：关键写入（如提交生成 prompt）后调用，确保内容立刻写库，
   *  不依赖 1s 防抖 autosave，避免刷新/切走时丢失。幂等（version 乐观锁）。 */
  saveCanvasNow: () => Promise<boolean>;
  /** 批量添加边（用于多选插入节点后的自动连线）。 */
  addEdges: (newEdges: Edge[]) => void;
  /**
   * 将一个新节点插入到 sourceId 的输出链路中。
   * - 若源节点没有下游边：直接建立 source -> newNode 的连线。
   * - 若源节点已有下游边：断开旧边，改为 source -> newNode -> 原下游目标，
   *   保证源节点始终只有一条输出边，避免裁剪后“双输出链接”的错乱。
   */
  insertNodeAfter: (sourceId: string, newNodeId: string) => void;
  /** 把 newNodeId 作为 targetId 的上游输入串接（裁切结果插入到源节点左侧/输入侧）。 */
  insertNodeBefore: (targetId: string, newNodeId: string) => void;
  /**
   * 多选插入节点：在选中节点集合的中心位置创建新节点，
   * 并将所有从选中节点出发的 source 边重连到新节点的 target（左 handle）。
   * 返回新创建的节点 ID。
   */
  insertNodeForSelection: (kind: PeaNodeKind, label: string) => string | null;
  /** 打组：将选中的节点包裹进一个 Group 容器节点。 */
  groupNodes: (nodeIds: string[]) => string | null;
  /** 解组：移除 Group 容器，子节点脱离父级（保留绝对位置）。 */
  ungroupNode: (groupId: string) => void;
  /**
   * 把无父节点拖入某组 / 把已归属子节点拖出到外层（按节点的画布坐标中心判定）。
   * 落在某组视觉边界内的 → 转 parentNode + 相对坐标 + 扩组；
   * 已归属但中心已落到组边界外的 → 转绝对坐标并脱离。
   * 返回本次发生的动作："added" | "removed" | null。
   */
  moveNodeToGroup: (nodeId: string) => 'added' | 'removed' | null;
  /** 切换组内布局：grid(宫格) / horizontal(水平)。 */
  reLayoutGroup: (groupId: string, layout: 'grid' | 'horizontal') => void;
  /** 下载组：将组内所有节点的数据打包导出为 JSON 文件。 */
  downloadGroup: (groupId: string) => void;
  // ── 撤销 / 重做历史栈 ──
  /** 历史栈：已提交的过往状态（可撤销）。 */
  past: HistorySnapshot[];
  /** 历史栈：被撤销后保留的将来状态（可重做）。 */
  future: HistorySnapshot[];
  /** 在「下一次结构性变更」前记录当前状态快照。传 label 可把连续同类操作合并为单条撤销项。 */
  takeSnapshot: (label?: string) => void;
  /** 撤销一步（Ctrl+Z）。还原上一次快照并保留当前状态到重做栈。 */
  undo: () => void;
  /** 重做一步（Ctrl+Shift+Z / Ctrl+Y）。 */
  redo: () => void;
}

/** 基于当前 nodes 生成唯一 ID，防止模块级 seq 在热更新/加载画布后重复导致节点被覆盖。 */
const nextId = (nodes: Node<PeaNodeData>[]) => {
  let max = 0;
  nodes.forEach((n) => {
    const m = /^n(\d+)$/.exec(n.id);
    if (m) max = Math.max(max, Number(m[1]));
  });
  return `n${max + 1}`;
};

/** 角度魔方面板打开态持久化键：刷新后据此恢复 cubeOpenNodeId。 */
const CUBE_OPEN_STORAGE_KEY = 'pea:cube-open-node-id';

/** 节点选中态持久化键：刷新后原样恢复选中集合，使面板可见性与刷新前一致。 */
const SELECTED_IDS_STORAGE_KEY = 'pea:selected-ids';
const persistSelectedIds = (ids: string[]) => {
  try {
    if (ids.length) localStorage.setItem(SELECTED_IDS_STORAGE_KEY, JSON.stringify(ids));
    else localStorage.removeItem(SELECTED_IDS_STORAGE_KEY);
  } catch {
    /* localStorage 不可用时静默降级（内存态仍生效） */
  }
};
const readSelectedIds = (): string[] => {
  try {
    const raw = localStorage.getItem(SELECTED_IDS_STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
};

/** 基于当前 edges 生成唯一边 ID，兼容 e1 / e1_xxx 等历史格式。 */
const nextEdgeId = (edges: Edge[]) => {
  let max = 0;
  edges.forEach((e) => {
    const m = /^e(\d+)(?:_.*)?$/.exec(e.id);
    if (m) max = Math.max(max, Number(m[1]));
  });
  return `e${max + 1}`;
};

// ════════════════════════════════════════════════════════════════════════
// 撤销 / 重做：基于快照的历史栈
// 设计要点（团队代码质量基准）：
//  - 只在「已提交的结构性变更」前记录快照，连续输入通过 label 合并为一条撤销项；
//  - 快照只保存可持久化的最小字段（与 openCanvas/cleanGraph 同口径），不含 ReactFlow
//    运行时字段（width/height/selected/measured…），还原时由 ReactFlow 重新测量；
//  - 生成任务回写（applyJobResult / reconcileGeneratingNodes）走 set 直写、不调 takeSnapshot，
//    因此「生成中 / 生成结果」不会污染历史栈，撤销只针对用户操作。
// ════════════════════════════════════════════════════════════════════════

/** 一条历史快照：节点/边的最小可还原表示 + 当时的选中态。 */
type HistorySnapshot = {
  nodes: any[];
  edges: any[];
  selectedIds: string[];
  selectedId: string | null;
};

const HISTORY_LIMIT = 100;

/** 深拷贝：节点数据均为可 JSON 序列化的纯对象，用 JSON 往返最稳妥。 */
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** 从当前状态提取最小快照（与 openCanvas/cleanGraph 口径一致）。 */
const snapshotFromState = (s: {
  nodes: Node<PeaNodeData>[];
  edges: Edge[];
  selectedIds: string[];
  selectedId: string | null;
}): HistorySnapshot => ({
  nodes: s.nodes.map((n: any) => {
    const base: any = {
      id: n.id,
      type: n.type || 'pea',
      position: { x: n.position.x, y: n.position.y },
      data: clone(n.data),
    };
    if (n.parentNode) {
      base.parentNode = n.parentNode;
      base.extent = n.extent;
    }
    // 组容器需保留尺寸、背景色与父子关系，否则撤销后分组丢失
    if (n.type === 'group' && n.style) {
      base.style = { width: n.style.width, height: n.style.height };
      if ((n.style as any).backgroundColor) {
        (base.style as any).backgroundColor = (n.style as any).backgroundColor;
      }
    }
    return base;
  }),
  edges: s.edges.map((e: any) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle ?? null,
    targetHandle: e.targetHandle ?? null,
    type: e.type || 'pea',
  })),
  selectedIds: [...s.selectedIds],
  selectedId: s.selectedId,
});

/** 把快照还原为受控节点（补回 selected 字段，与当前选中态对齐）。 */
const nodesFromSnapshot = (snap: HistorySnapshot): Node<PeaNodeData>[] =>
  snap.nodes.map((n: any) => ({ ...n, selected: snap.selectedIds.includes(n.id) }));

/** 合并链标记：同 label 的连续 takeSnapshot 只记录一次，用于把「逐字编辑」并成一条撤销项。 */
let lastHistoryLabel: string | null = null;
/** 拖拽快照标记：一次拖拽只在「首次产生位移」时记一条撤销项；松开后复位。 */
let dragSnapshotTaken = false;
/** 拖拽进行中标记：拖拽期间 ReactFlow 会发出 select 噪声(deselect 等)，
 * 这些 select change 不可信，必须忽略——否则会清掉 selectedIds → 节点 .selected 类丢失
 * → 功能条(opacity:0)消失。框选(box-selection)的 select change 不带 dragging，照常回写。 */
let draggingActive = false;
/**
 * 选择框拖拽中标志：由 SelectionBoundsBox 在 pointerdown 命中选择框时设为 true，
 * pointerup 时清除。
 * 目的：拖拽期间 onNodesChange 收到 ReactFlow 的 position 变更通知时，
 * 跳过 applyNodeChanges，避免与 SelectionBoundsBox 手动更新 position 冲突导致节点跳动。
 * 框选(box-selection)的 select change 不带 dragging，照常回写。
 */
let selBoxDragging = false;
/** 打组进行中标记：打组时 ReactFlow 会发出 select 噪声，抑制回写防止子节点工具条/编辑框闪现。 */
let groupingActive = false;

/** 外部（SelectionBoundsBox）设置 selBoxDragging 的标志。 */
export function setSelBoxDragging(val: boolean) {
  selBoxDragging = val;
}

export function setGroupingActive(val: boolean) {
  groupingActive = val;
}

export function getGroupingActive(): boolean {
  return groupingActive;
}

/* ────────────────────────────────────────────────────────────────────────────
 * 断线回收（detached reference GC）
 *
 * 背景：下游节点的「引用条缩略图」= 派生上游(getUpstreamInputs) ∪ 持久化引用。
 * 持久化引用共有 3 处载体，删边时若不同步回收，缩略图/参考图就会残留：
 *   ① data.meta.referencedNodeIds        引用条渲染集合（@ 插入 / + 画布选择）
 *   ② data.meta.editorText               编辑器 HTML，内含 <span data-pea-ref> token（token 本身即缩略图）
 *   ③ data.meta.genParams.reference_images  上次提交的参考图 URL（影响重试）
 * 只清 ① 不够 —— 切回节点时 ② 会把 token 恢复出来，提交时又把 id 加回 ①，形成「删了又回来」。
 * ──────────────────────────────────────────────────────────────────────────── */

/** 从编辑器 HTML 中摘除指定上游节点的 @ 引用 token（连同其后的零宽空格占位）。 */
export function stripRefTokens(html: string, ids: Set<string>): string {
  if (!html || !/data-pea-ref/i.test(html)) return html;
  try {
    const doc = new DOMParser().parseFromString(`<div id="__pea_root">${html}</div>`, 'text/html');
    const root = doc.getElementById('__pea_root');
    if (!root) return html;
    let changed = false;
    root.querySelectorAll<HTMLElement>('[data-pea-ref="1"]').forEach((el) => {
      const id = el.getAttribute('data-node-id');
      if (!id || !ids.has(id)) return;
      // token 插入时会在其后补一个 \u200B 光标锚点，一并清掉避免留下空白字符
      const next = el.nextSibling;
      if (next && next.nodeType === 3 && (next.textContent ?? '') === '\u200B') next.parentNode?.removeChild(next);
      el.parentNode?.removeChild(el);
      changed = true;
    });
    return changed ? root.innerHTML : html;
  } catch {
    return html;
  }
}

/** 收集某节点可作为参考图外发的所有 URL 指纹（去 query，用于匹配签名 URL）。 */
function refUrlFingerprints(n: Node<PeaNodeData> | undefined): string[] {
  if (!n) return [];
  const d = n.data;
  const raw = [d.url, d.resultUrl, ...(d.resultUrls ?? [])].filter(Boolean) as string[];
  const out = raw.map((u) => u.split('?')[0]);
  if (d.fileKey) out.push(d.fileKey);
  return out.filter(Boolean);
}

/**
 * 删边后回收下游节点上因该连线残留的持久化引用。
 * @param nodes      当前节点数组
 * @param edgesAfter 删除生效之后的边数组（用于判断是否还存在平行边）
 * @param removed    被删掉的边（只需 source/target）
 * @returns 新的 nodes（无变更时原样返回，保持引用稳定避免无谓重渲染）
 */
function pruneDetachedRefs(
  nodes: Node<PeaNodeData>[],
  edgesAfter: Edge[],
  removed: Array<{ source?: string | null; target?: string | null }>,
): Node<PeaNodeData>[] {
  // target -> 真正已断开的 source 集合
  const detached = new Map<string, Set<string>>();
  for (const e of removed) {
    const { source, target } = e;
    if (!source || !target) continue;
    // 平行边：还有别的边连着同一对节点时不算断开
    if (edgesAfter.some((x) => x.source === source && x.target === target)) continue;
    if (!detached.has(target)) detached.set(target, new Set());
    detached.get(target)!.add(source);
  }
  if (detached.size === 0) return nodes;

  const notify: Array<{ targetId: string; removedRefIds: string[] }> = [];
  let dirty = false;

  const next = nodes.map((n) => {
    const srcIds = detached.get(n.id);
    if (!srcIds || srcIds.size === 0) return n;

    const meta = { ...((n.data.meta ?? {}) as Record<string, unknown>) };
    let touched = false;

    // ① referencedNodeIds
    const refIds = Array.isArray(meta.referencedNodeIds) ? (meta.referencedNodeIds as string[]) : [];
    const keptRefIds = refIds.filter((id) => !srcIds.has(id));
    if (keptRefIds.length !== refIds.length) {
      meta.referencedNodeIds = keptRefIds;
      touched = true;
    }

    // ② editorText 里的 @ token
    const editorText = typeof meta.editorText === 'string' ? meta.editorText : '';
    if (editorText) {
      const stripped = stripRefTokens(editorText, srcIds);
      if (stripped !== editorText) {
        meta.editorText = stripped;
        touched = true;
      }
    }

    // ③ genParams.reference_images
    const gp = meta.genParams as Record<string, unknown> | undefined;
    const refImgs = Array.isArray(gp?.reference_images) ? (gp!.reference_images as string[]) : null;
    if (refImgs && refImgs.length) {
      const fps: string[] = [];
      srcIds.forEach((sid) => fps.push(...refUrlFingerprints(nodes.find((x) => x.id === sid))));
      if (fps.length) {
        const kept = refImgs.filter((u) => {
          const bare = String(u).split('?')[0];
          return !fps.some((fp) => bare === fp || bare.includes(fp));
        });
        if (kept.length !== refImgs.length) {
          meta.genParams = { ...(gp as Record<string, unknown>), reference_images: kept };
          touched = true;
        }
      }
    }

    if (!touched) return n;
    dirty = true;
    notify.push({ targetId: n.id, removedRefIds: Array.from(srcIds) });
    return { ...n, data: { ...n.data, meta } };
  });

  if (!dirty) return nodes;
  // 通知已打开的输入框同步本地 state / DOM（zustand set 期间不直接触发 React setState）
  queueMicrotask(() => {
    for (const payload of notify) {
      window.dispatchEvent(new CustomEvent('pea:refs-detached', { detail: payload }));
    }
  });
  return next;
}

export const useCanvas = create<CanvasState>((set, get) => ({
  canvasId: null,
  version: 0,
  title: '我的画布',
  nodes: [],
  edges: [],
  selectedId: null,
  selectedIds: [],
  cubeOpenNodeId: null,
  dirty: false,
  lastSavedAt: null,
  saveCount: 0,
  clipboard: null,
  jobNodeMap: {},
  defaultAspectRatio: '9:16',   // 图片节点默认竖海报比例
  past: [],
  future: [],

  setDefaultAspectRatio: (ratio) => set({ defaultAspectRatio: ratio }),

  // ── 撤销 / 重做：历史栈核心实现 ──
  takeSnapshot: (label) => {
    // 同 label 的连续调用（如逐字输入提示词）只记一次，避免历史被字符刷屏
    if (label && label === lastHistoryLabel) return;
    lastHistoryLabel = label ?? null;
    const s = get();
    const snap = snapshotFromState(s);
    const past = [...s.past, snap];
    if (past.length > HISTORY_LIMIT) past.shift();
    set({ past, future: [] });
  },
  undo: () => {
    const s = get();
    if (s.past.length === 0) return;
    const prev = s.past[s.past.length - 1];
    const past = s.past.slice(0, -1);
    const future = [...s.future, snapshotFromState(s)];
    lastHistoryLabel = null; // 撤销后打断合并链，下一次编辑单独成项
    set({
      nodes: nodesFromSnapshot(prev),
      edges: prev.edges,
      selectedIds: [...prev.selectedIds],
      selectedId: prev.selectedId,
      past,
      future,
      dirty: true,
    });
    persistSelectedIds(prev.selectedIds);
  },
  redo: () => {
    const s = get();
    if (s.future.length === 0) return;
    const next = s.future[s.future.length - 1];
    const future = s.future.slice(0, -1);
    const past = [...s.past, snapshotFromState(s)];
    if (past.length > HISTORY_LIMIT) past.shift();
    lastHistoryLabel = null;
    set({
      nodes: nodesFromSnapshot(next),
      edges: next.edges,
      selectedIds: [...next.selectedIds],
      selectedId: next.selectedId,
      past,
      future,
      dirty: true,
    });
    persistSelectedIds(next.selectedIds);
  },
  removeNodes: (ids) => {
    const idSet = new Set(ids);
    if (idSet.size === 0) return;
    const cubeOpenId = get().cubeOpenNodeId;
    const removeSet = new Set<string>();
    get().takeSnapshot(); // 一次批量删除合并为单条撤销项
    set((s) => {
      // 级联收集：组节点展开其子节点，并收集 parentNode 指向被删节点的孤立子节点
      const collect = (id: string) => {
        if (removeSet.has(id)) return;
        removeSet.add(id);
        const n = s.nodes.find((x) => x.id === id);
        if (n?.type === 'group') {
          ((n.data as any)?.childrenIds ?? [] as string[]).forEach(collect);
        }
        s.nodes.filter((x) => x.parentNode === id).forEach((c) => collect(c.id));
      };
      ids.forEach(collect);

      const nextEdges = s.edges.filter(
        (e) => !removeSet.has(e.source) && !removeSet.has(e.target),
      );
      // 断线回收：节点被删 = 其所有出边断开，幸存的下游节点必须清掉指向它的残留引用
      // （包括未连线但通过「+ 从画布选择」引用的死链，节点没了缩略图不能留着）。
      // 只对 meta 里确有引用痕迹的幸存节点构造清理对，避免大批量删除时的无谓遍历。
      const removedIds = Array.from(removeSet);
      const detachPairs: Array<{ source: string; target: string }> = [];
      for (const t of s.nodes) {
        if (removeSet.has(t.id)) continue;
        const m = (t.data.meta ?? {}) as Record<string, unknown>;
        const hasRefTrace =
          (Array.isArray(m.referencedNodeIds) && (m.referencedNodeIds as string[]).length > 0) ||
          (typeof m.editorText === 'string' && m.editorText.includes('data-pea-ref')) ||
          Array.isArray((m.genParams as Record<string, unknown> | undefined)?.reference_images);
        if (!hasRefTrace) continue;
        for (const sid of removedIds) detachPairs.push({ source: sid, target: t.id });
      }
      // 注意：传入未过滤的 s.nodes，pruneDetachedRefs 需要读被删节点的 URL 指纹来剔除 reference_images
      const pruned = detachPairs.length
        ? pruneDetachedRefs(s.nodes, nextEdges, detachPairs)
        : s.nodes;

      return {
        nodes: pruned.filter((n) => !removeSet.has(n.id)),
        edges: nextEdges,
        selectedId: s.selectedId != null && removeSet.has(s.selectedId) ? null : s.selectedId,
        selectedIds: s.selectedIds.filter((x) => !removeSet.has(x)),
        cubeOpenNodeId: cubeOpenId != null && removeSet.has(cubeOpenId) ? null : s.cubeOpenNodeId,
        dirty: true,
      };
    });
    persistSelectedIds(get().selectedIds);
    if (cubeOpenId != null && removeSet.has(cubeOpenId)) {
      try {
        localStorage.removeItem(CUBE_OPEN_STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
  },

  setCanvasMeta: (id, version, title) =>
    set({ canvasId: id, version, ...(title !== undefined ? { title } : {}) }),
  onNodesChange: (changes) => {
    // 选择框拖拽中：跳过 position 变更处理，避免与 SelectionBoundsBox 手动更新冲突导致跳动
    // 但 select 变更仍正常处理（框选补选等）
    const hasSelBoxDrag = selBoxDragging;
    const filteredChanges = hasSelBoxDrag
      ? changes.filter((c: any) => c.type !== 'position')
      : changes;
    const next = applyNodeChanges(filteredChanges, get().nodes) as any;
    let ids = get().selectedIds;

    // 拖拽快照：首次产生位移时记录「拖拽前」状态（一次拖拽 = 单条撤销项）。
    // 放在 onNodesChange 而非 onNodeDragStart，是因为 onNodeDragStart 在 mousedown 即触发
    //（纯点击也会触发），放在那里会为每次点击产生一条无意义的撤销项。
    // 此时 get().nodes 仍是拖拽前的状态，takeSnapshot 能正确捕获。
    const dragPos = changes.find((c: any) => c.type === 'position') as any;
    if (dragPos && !hasSelBoxDrag) {
      if (dragPos.dragging === true && !dragSnapshotTaken) {
        dragSnapshotTaken = true;
        get().takeSnapshot();
      } else if (dragPos.dragging === false) {
        dragSnapshotTaken = false;
      }
      draggingActive = dragPos.dragging === true;
    }


    // 检测框选（box-selection）产生的 select 类型变更：
    // ReactFlow 在拖拽框选时会发出 type='select' 的 change，
    // 把被框选中的节点标记 selected=true / 未选中的标记 selected=false。
    // 此时需要反向同步：从节点 selected 状态回写 selectedIds，
    // 否则多选工具条等依赖 selectedIds.length > 1 的功能无法感知框选结果。
    const hasSelectChanges = changes.some((c: any) => c.type === 'select');
    // 拖拽进行中 ReactFlow 会发出 select 噪声(拖拽前先 deselect 等)，这些 select change
    // 不可信：回写会清掉 selectedIds → 节点 .selected 类丢失 → 功能条(opacity:0)消失。
    // 仅当非拖拽(draggingActive=false)时才回写；框选(box-selection)的 select change 照常生效。
    if (hasSelectChanges && !draggingActive && !groupingActive) {
      ids = next.filter((n: any) => n.selected).map((n: any) => n.id);
      // 注：框选「覆盖即选中」的二次校正已从这里移除——
      // ReactFlow 的 box-selection 仅在拖拽过程中（选中集合变化时）发出 select change，
      // 此时 window.__lastSelRect 还是拖拽中途帧，校正只会用到不完整的选区。
      // 正确的触发点是 mouseup（见 CanvasEditor 的 onUp：用原始 pointer 事件算出完整选区 rect
      // 后 setTimeout(0) 调 correctBoxSelection），此时选区已是最终完整矩形。
    }

    // 受控选中：强制 node.selected 与 selectedIds 一致，
    // 避免 ReactFlow 内部选中（如拖动节点）制造"选中但没弹框/弹错框"的错乱。
    // 关键修复：reconciliation 始终使用 store 当前 selectedIds，
    // 而非可能因 groupingActive 保护而未更新的 ids 局部变量。
    // 否则分组期间 ReactFlow 检测到 node.selected 与 selectedIds 不一致
    // 会反复发出 select 变更，导致连线高亮等副作用。
    const curSelectedIds = get().selectedIds;
    const reconciled = next.map((n: any) =>
      n.selected === curSelectedIds.includes(n.id) ? n : { ...n, selected: curSelectedIds.includes(n.id) },
    );
    // 仅用户实质变更（拖动 position / 增删 / replace）才标脏。
    // dimensions(ReactFlow 加载时尺寸测量) 与 select(受控选中/框选) 是内部事件，
    // 不标脏——否则「进入画布即被自动保存」，导致 version 无谓递增、写放大、乐观锁冲突。
    const isUserChange = changes.some(
      (c: any) => c.type === 'position' || c.type === 'remove' || c.type === 'add' || c.type === 'replace',
    );
    set({
      nodes: reconciled,
      dirty: isUserChange ? true : get().dirty,
      // 框选时同步更新 selectedIds / selectedId
      ...(hasSelectChanges && !groupingActive ? {
        selectedIds: ids,
        selectedId: ids.length ? ids[ids.length - 1] : null,
      } : {}),
    });
    if (hasSelectChanges && !groupingActive) persistSelectedIds(ids);
  },
  onEdgesChange: (changes) => {
    // 同上：select(受控选中) 不标脏，仅 remove/add/position 等实质变更标脏。
    const isUserChange = changes.some(
      (c: any) => c.type === 'remove' || c.type === 'add' || c.type === 'position',
    );
    const before = get().edges;
    const nextEdges = applyEdgeChanges(changes, before);
    // 断线回收：ReactFlow 内建删除路径（当前 deleteKeyCode=null，但保留以防回归）
    const removedIds = changes.filter((c: any) => c.type === 'remove').map((c: any) => c.id);
    let nextNodes = get().nodes;
    if (removedIds.length) {
      const removed = before.filter((e) => removedIds.includes(e.id));
      nextNodes = pruneDetachedRefs(nextNodes, nextEdges, removed);
    }
    set({
      edges: nextEdges,
      ...(nextNodes !== get().nodes ? { nodes: nextNodes } : {}),
      dirty: isUserChange ? true : get().dirty,
    });
  },
  onConnect: (conn) => { get().takeSnapshot(); set({ edges: addEdge({ ...conn, type: 'pea' }, get().edges), dirty: true }); },
  removeEdge: (id) => {
    get().takeSnapshot();
    const before = get().edges;
    const removed = before.filter((e) => e.id === id);
    const nextEdges = before.filter((e) => e.id !== id);
    // 断线回收：清掉下游节点上因这条连线残留的引用缩略图 / @ token / 参考图 URL
    set({ edges: nextEdges, nodes: pruneDetachedRefs(get().nodes, nextEdges, removed), dirty: true });
  },
  addNode: (data, position) => {
    get().takeSnapshot();
    const nodes = get().nodes;
    const id = nextId(nodes);
    const node: Node<PeaNodeData> = { id, type: 'pea', position, data, selected: true };
    set({
      nodes: [...nodes.map((n) => ({ ...n, selected: false })), node],
      dirty: true,
      selectedId: id,
      selectedIds: [id],
    });
    persistSelectedIds([id]);
    return id;
  },
  updateNodeData: (id, patch, recordHistory = true) => {
    // 同一节点的连续编辑（如逐字输入提示词）合并为单条撤销项；
    // 不同节点用不同 label，避免互相吞掉撤销项。
    if (recordHistory) get().takeSnapshot('node-data:' + id);
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...patch } } : n,
      ),
      dirty: true,
    });
  },
  setCubeOpenNodeId: (id) => {
    set({ cubeOpenNodeId: id });
    // 持久化打开态，刷新后仍可恢复魔方面板（仅 × / 确认生成会清为空）。
    try {
      if (id) localStorage.setItem(CUBE_OPEN_STORAGE_KEY, id);
      else localStorage.removeItem(CUBE_OPEN_STORAGE_KEY);
    } catch {
      /* localStorage 不可用时静默降级（内存态仍生效） */
    }
  },
  select: (id) => {
    set((s) => ({
      selectedId: id,
      selectedIds: id ? [id] : [],
      nodes: s.nodes.map((n) => ({ ...n, selected: !!id && n.id === id })),
    }));
    persistSelectedIds(id ? [id] : []);
  },
  toggleSelect: (id) => {
    let nextIds: string[] = [];
    set((s) => {
      const has = s.selectedIds.includes(id);
      const next = has ? s.selectedIds.filter((x) => x !== id) : [...s.selectedIds, id];
      nextIds = next;
      const selId = next.length ? (has ? next[next.length - 1] || id : id) : null;
      return {
        selectedIds: next,
        selectedId: selId,
        nodes: s.nodes.map((n) => ({ ...n, selected: next.includes(n.id) })),
      };
    });
    persistSelectedIds(nextIds);
  },
  setSelection: (ids) => {
    set((s) => ({
      selectedIds: ids,
      selectedId: ids.length ? ids[ids.length - 1] : null,
      nodes: s.nodes.map((n) => ({ ...n, selected: ids.includes(n.id) })),
    }));
    persistSelectedIds(ids);
  },
  correctBoxSelection: () => {
    if (typeof window === 'undefined') return;
    const last = (window as any).__lastSelRect as
      | {
          x: number; y: number; width: number; height: number;
          screenLeft: number; screenTop: number; screenRight: number; screenBottom: number;
          timestamp: number;
        }
      | null;
    if (!last || (last.width < 1 && last.height < 1)) return;
    // 仅当最近一次框选发生在 800ms 内（防止陈旧 rect 误校正）
    if (performance.now() - last.timestamp > 800) return;
    // ── 关键修复：纯屏幕坐标判断（不做 viewport transform 转换）──
    // 之前用 canvas 坐标比对，必须把节点 screenRect 反变换到画布坐标；translate/scale 任一项
    // 读错都会让选区「明明盖到节点、节点没被选中」。改为全屏幕坐标系下的 partial-intersection：
    // 选区是 __lastSelRect 的 screenLeft/Top/Right/Bottom，节点是 getBoundingClientRect()，
    // 两个都在 viewport 坐标系（CSS px），直接比较即可。viewport 缩放时两边同步缩放，结果一致。
    const selL = last.screenLeft, selT = last.screenTop, selR = last.screenRight, selB = last.screenBottom;
    const cur = get().selectedIds;
    const curSet = new Set(cur);
    const nodes = get().nodes;
    const patched: string[] = [...cur];
    for (const n of nodes) {
      if (n.type === 'group') continue; // 跳过组容器，组本身不进 multi-select
      if (curSet.has(n.id)) continue;
      const el = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${n.id}"]`);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      // 屏幕坐标 partial-intersection（节点矩形与选区矩形有任何重叠即视为「被覆盖」）
      const overlap =
        r.left < selR &&
        r.right > selL &&
        r.top < selB &&
        r.bottom > selT;
      if (overlap) {
        patched.push(n.id);
        curSet.add(n.id);
      }
    }
    if (patched.length !== cur.length) get().setSelection(patched);

    // ── 去掉边误选：框选结束时把全部 edges.selected 强制置 false ──
    // ReactFlow v11 SelectionMode.Partial 默认会把"穿过选区"的连线也加入选中集，
    // 表现为「box 盖到边 → 边高亮 + 触发边的 selected 逻辑」。
    // 用户需求：选区只用于"框住同一组节点"，不动边。
    const edges = get().edges;
    const anyEdgeSel = edges.some((e: any) => e.selected);
    if (anyEdgeSel) {
      set({
        edges: edges.map((e: any) => (e.selected ? { ...e, selected: false } : e)),
      });
    }
  },
  clearSelection: () => {
    set((s) => ({
      selectedIds: [],
      selectedId: null,
      nodes: s.nodes.map((n) => ({ ...n, selected: false })),
    }));
  },

  markSaved: (version) => set({ version, dirty: false, lastSavedAt: Date.now(), saveCount: get().saveCount + 1 }),
  loadGraph: (nodes, edges, version) => {
    lastHistoryLabel = null;
    set({
      nodes,
      edges: (edges ?? []).map((e: Edge) => (e.type ? e : { ...e, type: 'pea' })),
      version,
      dirty: false,
      past: [],
      future: [],
    });
  },
  openCanvas: async (id) => {
    // 打开前先清空上一个画布的残留状态（nodes/edges/选中），
    // 防止切换项目时旧画布内容闪现，或请求失败时旧内容被误当作新画布展示。
    lastHistoryLabel = null;
    set({ nodes: [], edges: [], selectedId: null, selectedIds: [], dirty: false, jobNodeMap: {}, past: [], future: [] });
    const g = await api.get(`/canvases/${id}`);
    const raw = g.data.graph_json;
    const graph =
      typeof raw === 'string'
        ? raw
          ? JSON.parse(raw)
          : { nodes: [], edges: [] }
        : raw ?? { nodes: [], edges: [] };
    // 加载时清洗节点：丢弃 ReactFlow 运行时字段（width/height/positionAbsolute/
    // selected/dragging/measured 等），只保留持久化所需的字段，交由 ReactFlow 重新测量，
    // 避免陈旧测量值导致 fitView 视口抖动、看起来「内容变了」。
    const cleanNode = (n: any) => {
      const base: Record<string, unknown> = {
        id: n.id,
        type: n.type || 'pea',
        position: n.position || { x: 0, y: 0 },
        data: n.data || {},
      };
      // 保留父子关系与容器尺寸（分组节点/子节点必需）
      if (n.parentNode) base.parentNode = n.parentNode;
      if (n.extent) base.extent = n.extent;
      if (n.style) base.style = n.style;
      return base;
    };
    const cleanEdge = (e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? null,
      targetHandle: e.targetHandle ?? null,
      type: e.type || 'pea',
    });
    set({ canvasId: g.data.id, version: g.data.version, title: g.data.title, dirty: false });
    useUi.getState().setCanvasId(g.data.id);
    set({
      nodes: (graph.nodes ?? []).map(cleanNode),
      edges: (graph.edges ?? []).map(cleanEdge),
      version: g.data.version,
      dirty: false,
    });
    // 刷新后恢复角度魔方面板：cubeOpenNodeId 持久化在 localStorage，
    // 若对应节点仍存在且为带图媒体节点，则重开面板、选中并居中；否则清理残留键。
    try {
      const savedCubeId = localStorage.getItem(CUBE_OPEN_STORAGE_KEY);
      if (savedCubeId) {
        const node = get().nodes.find((n) => n.id === savedCubeId);
        const hasImage = node?.data.kind === 'image'
          && !!(
            (node.data as any).resultUrl
            || ((node.data as any).resultUrls && (node.data as any).resultUrls.length)
            || (node.data as any).url
            || (node.data as any).fileKey
          );
        if (node && hasImage) {
          // 恢复刷新前的选中集合（原样），而非强制选中魔方节点：
          // 「刷新前点空白隐藏」→ 刷新后仍是隐藏；「刷新前显示」→ 刷新后显示。
          const savedSel = readSelectedIds().filter((x) => get().nodes.some((n) => n.id === x));
          set((s) => ({
            cubeOpenNodeId: savedCubeId,
            selectedId: savedSel.length ? savedSel[savedSel.length - 1] : null,
            selectedIds: savedSel,
            nodes: s.nodes.map((n) => ({ ...n, selected: savedSel.includes(n.id) })),
          }));
          // 仅当魔方节点仍在刷新前的选中集合内（面板会显示）才居中，避免无谓跳动。
          if (savedSel.includes(savedCubeId)) {
            window.dispatchEvent(
              new CustomEvent('pea:center-node', { detail: { id: savedCubeId, mode: 'cube' } }),
            );
          }
        } else {
          localStorage.removeItem(CUBE_OPEN_STORAGE_KEY);
        }
      }
    } catch {
      /* localStorage 不可用时忽略恢复 */
    }
    // 加载完成后异步核对：所有 generating=true 的节点拿 lastJobId 去后端查真实状态，
    // 防止 WS 事件丢失/页面重开导致节点永远停「生成中」（stale state）。
    // 没 lastJobId 的旧节点直接置 false（无法重建关联的 job）。
    void get().reconcileGeneratingNodes();
  },
  // 单节点删除：委托给 removeNodes（级联清理 + 单条撤销项）。
  removeNode: (id) => get().removeNodes([id]),
  duplicateNode: (id) => {
    get().takeSnapshot();
    const src = get().nodes.find((n) => n.id === id);
    if (!src) return;
    const nid = nextId(get().nodes);
    const copy: Node<PeaNodeData> = {
      id: nid,
      type: src.type || 'pea',
      position: { x: src.position.x + 140, y: src.position.y + 60 },
      data: clone(src.data),
      selected: true,
    };

    // 复制与原节点相关的连线：原节点作为 source/target 的端点替换为新节点 ID，
    // 保持另一端的连接对象、handle、边类型不变，生成新的唯一边 ID。
    const currentEdges = get().edges;
    const duplicatedEdges: Edge[] = [];
    currentEdges.forEach((e) => {
      if (e.source !== id && e.target !== id) return;
      duplicatedEdges.push({
        ...e,
        id: nextEdgeId([...currentEdges, ...duplicatedEdges]),
        source: e.source === id ? nid : e.source,
        target: e.target === id ? nid : e.target,
      });
    });

    set({
      nodes: [...get().nodes.map((n) => ({ ...n, selected: false })), copy],
      edges: [...currentEdges, ...duplicatedEdges],
      selectedId: nid,
      selectedIds: [nid],
      dirty: true,
    });
  },
  addConnected: (fromId) => {
    get().takeSnapshot();
    const src = get().nodes.find((n) => n.id === fromId);
    if (!src) return;
    const nid = nextId(get().nodes);
    const node: Node<PeaNodeData> = {
      id: nid,
      type: 'pea',
      position: { x: src.position.x + 260, y: src.position.y + 30 },
      data: { label: '生成', kind: 'generate', prompt: '', meta: { error: false } },
    };
    const edge: Edge = { id: `e${nid}`, source: fromId, target: nid };
    set({
      nodes: [...get().nodes.map((n) => ({ ...n, selected: false })), node],
      edges: [...get().edges, edge],
      selectedId: nid,
      selectedIds: [nid],
      dirty: true,
    });
  },
  copySelected: () => {
    const sel = get().nodes.find((n) => n.id === get().selectedId);
    if (sel) set({ clipboard: sel });
  },
  pasteNode: () => {
    get().takeSnapshot();
    const clip = get().clipboard;
    if (!clip) return;
    const nid = nextId(get().nodes);
    const copy: Node<PeaNodeData> = {
      id: nid,
      type: 'pea',
      position: { x: clip.position.x + 60, y: clip.position.y + 60 },
      data: { ...clip.data },
      selected: true,
    };
    set({
      nodes: [...get().nodes.map((n) => ({ ...n, selected: false })), copy],
      selectedId: nid,
      selectedIds: [nid],
      dirty: true,
    });
  },
  bumpSave: () => set({ saveCount: get().saveCount + 1 }),
  /**
   * 立即落盘（非防抖）：在关键写入（如提交生成 prompt）后调用，
   * 确保用户内容立刻写库，避免依赖 1s 防抖 autosave 在刷新/切走时丢失。
   * 幂等（version 乐观锁，重复 PUT 第二次 409 被忽略）。
   */
  /**
   * 立即落盘（非防抖）：在关键写入（如提交生成 prompt）后调用，
   * 确保用户内容立刻写库，避免依赖 1s 防抖 autosave 在刷新/切走时丢失。
   *
   * 关键修复：原先 409/网络错误被 `catch {}` 静默吞掉，导致 prompt(editorText)
   * 永远没写进后端；而 submit() 又紧接着 `localStorage.removeItem(draftKey)` 删掉
   * 唯一兜底草稿 → 退出重进后编辑框空白（已复现）。
   * 现改为：
   *   1) 409 乐观锁冲突 → 重新拉取后端权威 version 后重试一次（last-write-wins，单用户画布安全），
   *      确保本次用户内容真正落库；
   *   2) 返回 boolean 表示是否真正落盘，供调用方决定是否清除 localStorage 兜底草稿。
   */
  saveCanvasNow: async (): Promise<boolean> => {
    const s = get();
    if (s.canvasId == null) return false;
    try {
      const { data } = await api.put(`/canvases/${s.canvasId}`, {
        graph_json: cleanGraph(s.nodes, s.edges),
        version: s.version,
      });
      get().markSaved(data.version);
      return true;
    } catch (err: any) {
      // 乐观锁冲突：本地 version 落后后端（常见于 autosave 与本次保存竞态）。
      // 重新拉取权威 version 并重试，避免用户刚输入的 prompt 被静默丢弃。
      if (err?.response?.status === 409) {
        try {
          const g = await api.get(`/canvases/${s.canvasId}`);
          const serverVersion: number = g.data.version;
          set({ version: serverVersion });
          const { data } = await api.put(`/canvases/${s.canvasId}`, {
            graph_json: cleanGraph(get().nodes, get().edges),
            version: serverVersion,
          });
          get().markSaved(data.version);
          return true;
        } catch (retryErr) {
          console.error('[saveCanvasNow] 409 重试仍失败，保留 localStorage 兜底草稿', retryErr);
          return false;
        }
      }
      // 其他错误（画布已删除 / 网络异常）：记录但不抛出，避免中断生成流程。
      console.error('[saveCanvasNow] 保存失败，保留 localStorage 兜底草稿', err);
      return false;
    }
  },
  getUpstreamInputs: (nodeId) => {
    const { nodes, edges } = get();
    const upstreamEdges = edges
      .filter((e) => e.target === nodeId)
      .sort((a, b) => {
        // 简单按边 id 字典序稳定排序，保证多参考图顺序可预期
        return a.id.localeCompare(b.id);
      });
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    return upstreamEdges
      .map((e) => nodeMap.get(e.source))
      .filter((n): n is Node<PeaNodeData> => !!n);
  },
  registerJob: (jobId, nodeId) =>
    set((s) => ({ jobNodeMap: { ...s.jobNodeMap, [jobId]: nodeId } })),
  reconcileGeneratingNodes: async () => {
    // 1) 没 lastJobId 但 generating=true 的旧节点：直接清掉 generating（无法重建关联 job）
    const orphanIds: string[] = [];
    set((s) => ({
      nodes: s.nodes.map((n) => {
        if (n.data?.generating && !n.data?.lastJobId) {
          orphanIds.push(n.id);
          return { ...n, data: { ...n.data, generating: false, error: '上次会话未完成，请重新发起' } };
        }
        return n;
      }),
      dirty: true,
    }));
    if (orphanIds.length) {
      // tsc-only debug: 让 console 留个痕迹
      console.info(`[reconcile] cleared ${orphanIds.length} orphan generating node(s) without lastJobId`);
    }
    // 2) 有 lastJobId 的节点：并发查后端，按真实状态回填
    const targets = get().nodes
      .filter((n) => n.data?.generating && n.data?.lastJobId)
      .map((n) => ({ nodeId: n.id, jobId: n.data!.lastJobId as string }));
    if (targets.length === 0) return;
    await Promise.all(
      targets.map(async ({ nodeId, jobId }) => {
        try {
          const { data } = await api.get<any>(`/generation/jobs/${jobId}`);
          const st = data?.status;
          if (st === 'done') {
            const url = data?.resultUrl ?? undefined;
            const urls = data?.resultUrls ?? (url ? [url] : undefined);
            set((s) => ({
              nodes: s.nodes.map((n) =>
                n.id === nodeId
                  ? { ...n, data: { ...n.data, generating: false, error: undefined, resultUrl: urls?.[0] ?? url, resultUrls: urls, resultIndex: 0 } }
                  : n
              ),
              dirty: true,
            }));
          } else if (st === 'failed' || st === 'refunded') {
            set((s) => ({
              nodes: s.nodes.map((n) =>
                n.id === nodeId
                  ? { ...n, data: { ...n.data, generating: false, error: data?.error || '生成失败' } }
                  : n
              ),
              dirty: true,
            }));
          } else {
            // 还在跑：注册到 jobNodeMap 让轮询兜底继续接管
            set((s) => ({ jobNodeMap: { ...s.jobNodeMap, [jobId]: nodeId } }));
            const { pollNodeJobResult } = await import('../lib/nodeGeneration');
            pollNodeJobResult(jobId);
          }
        } catch {
          // 后端查不到（job 已过期/被清理）→ 直接清理节点
          set((s) => ({
            nodes: s.nodes.map((n) =>
              n.id === nodeId
                ? { ...n, data: { ...n.data, generating: false, error: '任务记录已过期，请重新发起' } }
                : n
            ),
            dirty: true,
          }));
        }
      })
    );
  },
  applyJobResult: (jobId, patch) =>
    set((s) => {
      // 防御：绝不能因后端回写 payload 里携带 prompt: undefined/null 而把用户已输入的提示词清空。
      // （生成结果回写只关心 generating/resultUrl/error 等字段，prompt 必须始终保留。）
      const safePatch: Partial<PeaNodeData> = { ...patch };
      if (safePatch.prompt === undefined || safePatch.prompt === null) {
        delete safePatch.prompt;
      }
      // 1) 正常路径: jobNodeMap 找到 -> 直接 patch
      const nodeId = s.jobNodeMap[jobId];
      if (nodeId) {
        return {
          dirty: true,
          nodes: s.nodes.map((n) =>
            n.id === nodeId ? { ...n, data: { ...n.data, ...safePatch } } : n,
          ),
        };
      }
      // 2) 兜底: jobNodeMap 已被清 (早期 removeJob, 或 reload 后 map 重置),
      //    但节点 data.lastJobId 持久化了 jobId —— 用它回写到正确节点.
      //    不然失败/完成事件会"丢失", 节点 stuck 在 generating=true,
      //    HUD 4 角 + 中心 TechLoader 一直转.
      const fallbackId = s.nodes.find((n) => n.data?.lastJobId === jobId)?.id;
      if (fallbackId) {
        return {
          dirty: true,
          nodes: s.nodes.map((n) =>
            n.id === fallbackId ? { ...n, data: { ...n.data, ...safePatch } } : n,
          ),
        };
      }
      return {};
    }),
  removeJob: (jobId) =>
    set((s) => {
      if (!(jobId in s.jobNodeMap)) return {};
      const next = { ...s.jobNodeMap };
      delete next[jobId];
      return { jobNodeMap: next };
    }),
  addEdges: (newEdges) =>
    set((s) => ({
      edges: [...s.edges, ...newEdges.map((e) => ({ ...e, type: e.type || 'pea' }))],
      dirty: true,
    })),
  insertNodeForSelection: (kind, label) => {
    const s = get();
    const selIds = s.selectedIds;
    if (selIds.length === 0) return null;
    get().takeSnapshot();

    // 计算选中节点的包围盒中心（画布坐标）
    const selNodes = s.nodes.filter((n) => selIds.includes(n.id));
    if (selNodes.length === 0) return null;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    selNodes.forEach((n) => {
      const w = (n as any).width ?? 260;
      const h = (n as any).height ?? 160;
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      maxX = Math.max(maxX, n.position.x + w);
      maxY = Math.max(maxY, n.position.y + h);
    });
    const centerPos = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 + 80 }; // 稍偏下，避免遮挡

    // 创建新节点
    const nid = nextId(s.nodes);
    const store = useCanvas.getState();
    const ratio = kind === 'image'
      ? store.defaultAspectRatio
      : kind === 'video'
        ? '16:9'
        : undefined;
    const newNode: Node<PeaNodeData> = {
      id: nid,
      type: 'pea',
      position: centerPos,
      data: {
        kind,
        label,
        aspectRatio: ratio,
        meta: { error: false, ...(kind === 'image' ? { genParams: { aspectRatio: ratio, resolution: '2k' } } : {}) },
      } as PeaNodeData,
      selected: false, // 不选中新节点，保持多选状态
    };

    // 收集所有从选中节点出发的 source 边（这些边需要重连到新节点）
    // 同时找出这些边的原始 target 节点
    const sourceEdges = s.edges.filter((e) => selIds.includes(e.source));
    // 原始 target 集合（去重）
    const originalTargets = [...new Set(sourceEdges.map((e) => e.target))];

    // 构建新边：
    // 1. 仅把"确有右节点连线（将被重连）的选中节点"连到新节点左端。
    //    注意：只取 sourceEdges 里的 source，而**不是**对所有 selectedIds 建边——
    //    否则当某选中节点同时是另一条边的下游（如框选整条链 A->B 时 B 既被连入又被连出）
    //    会产生多余的环边（B->新节点 + 新节点->B）。
    const outgoingSources = [...new Set(sourceEdges.map((e) => e.source))];
    const edgesToNew = outgoingSources.map((sid, i) => ({
      id: `e${nid}_from_${i}`,
      source: sid,
      target: nid,
    }));

    // 2. 新节点 → 每个 original target（保留原有下游连接）
    const edgesFromNew = originalTargets.map((tgt, i) => ({
      id: `e${nid}_to_${i}`,
      source: nid,
      target: tgt,
    }));

    // 要删除的旧边 ID（被替换掉的 source 边）
    const oldEdgeIds = new Set(sourceEdges.map((e) => e.id));

    const nextEdges = [
      // 保留不被替换的边
      ...s.edges.filter((e) => !oldEdgeIds.has(e.id)),
      // 新增：选中→新节点 + 新节点→原目标
      ...edgesToNew,
      ...edgesFromNew,
    ];

    set({
      // 断线回收：A→B 被改写为 A→新节点→B 后，B 已不再直连 A，
      // 需清掉 B 上残留的对 A 的引用缩略图 / @ token（内容改由新节点中转）。
      nodes: pruneDetachedRefs(
        [...s.nodes, newNode],
        nextEdges,
        sourceEdges.map((e) => ({ source: e.source, target: e.target })),
      ),
      edges: nextEdges,
      dirty: true,
      // 保持当前多选状态不变（不切换到新节点）
    });

    return nid;
  },

  insertNodeAfter: (sourceId, newNodeId) => {
    const s = get();
    const sourceEdges = s.edges.filter((e) => e.source === sourceId);
    get().takeSnapshot();

    if (sourceEdges.length === 0) {
      set({
        edges: addEdge(
          { source: sourceId, target: newNodeId, sourceHandle: 'out', targetHandle: 'in', type: 'pea' },
          s.edges,
        ),
        dirty: true,
      });
      return;
    }

    // 源节点已有下游边：把新节点串进链路，保持原下游连接。
    const originalTargets = [...new Set(sourceEdges.map((e) => e.target))];
    const oldEdgeIds = new Set(sourceEdges.map((e) => e.id));
    let nextEdges = s.edges.filter((e) => !oldEdgeIds.has(e.id));

    nextEdges = addEdge(
      { source: sourceId, target: newNodeId, sourceHandle: 'out', targetHandle: 'in', type: 'pea' },
      nextEdges,
    );
    originalTargets.forEach((tgt) => {
      nextEdges = addEdge(
        { source: newNodeId, target: tgt, sourceHandle: 'out', targetHandle: 'in', type: 'pea' },
        nextEdges,
      );
    });

    set({
      edges: nextEdges,
      // 断线回收：原下游 target 不再直连 sourceId，需清理残留的引用缩略图 / @ token。
      nodes: pruneDetachedRefs(
        s.nodes,
        nextEdges,
        sourceEdges.map((e) => ({ source: e.source, target: e.target })),
      ),
      dirty: true,
    });
  },

  // 裁切结果作为源节点的【上游输入】：把新节点串接到源节点的输入侧（左侧）。
  // 与 insertNodeAfter 镜像——前者把新节点塞进「源 → 下游」，后者塞进「上游 → 源」。
  insertNodeBefore: (targetId, newNodeId) => {
    const s = get();
    const incoming = s.edges.filter((e) => e.target === targetId);
    get().takeSnapshot();

    const nextEdges = wireAsUpstream(s.edges, targetId, newNodeId);

    set({
      edges: nextEdges,
      // 断线回收：原上游 source 不再直连 targetId（改连 newNodeId），
      // 需清理 target 上对旧上游的引用缩略图 / @ token。
      nodes: pruneDetachedRefs(
        s.nodes,
        nextEdges,
        incoming.map((e) => ({ source: e.source, target: e.target })),
      ),
      dirty: true,
    });
  },

  // ═══════════════════════════════════════════════════════════════
  // 打组 / 解组 / 布局 / 下载
  // ═══════════════════════════════════════════════════════════════

  groupNodes: (nodeIds) => {
    const s = get();
    if (nodeIds.length < 2) return null;
    // 不干扰 SelectionOverlay 的自然 fade-out，让选择框先淡出再出现打组框
    setGroupingActive(true);
    get().takeSnapshot();
    const ids = [...new Set(nodeIds)];

    // 计算子节点包围盒
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    ids.forEach((id) => {
      const n = s.nodes.find((x) => x.id === id);
      if (!n) return;
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      // 用 width/height(如有)估算右下角，否则默认 200x160
      const w = (n as any).width ?? 200;
      const h = (n as any).height ?? 160;
      maxX = Math.max(maxX, n.position.x + w);
      maxY = Math.max(maxY, n.position.y + h);
    });

    const PAD = 0; // 严格按节点最左/右/上/下包裹，不留缝隙
    const gw = maxX - minX + PAD * 2;
    const gh = maxY - minY + PAD * 2;
    const gx = minX - PAD;
    const gy = minY - PAD;

    const gid = `group_${Date.now()}`;

    // 创建 Group 节点（容器）
    // - 显式 draggable/selectable：避免 ReactFlow 内部默认推断失败时子节点不跟随
    // - 不再在容器内渲染 header（GroupNode 改用 portal 浮层），故容器 height 不需要为 header 留余
    const groupNode: any = {
      id: gid,
      type: 'group',
      position: { x: gx, y: gy },
      data: { label: '新建组', layout: 'grid', childrenIds: ids },
      draggable: true,
      selectable: true,
      // ReactFlow 父子容器属性
      style: { width: gw, height: gh, padding: 0 },
    };

    // 将子节点的 parentNode 强制指向 group，并把坐标转为相对 group 原点。
    // 关键修复（拖动组时部分子节点不跟随）：
    //   ReactFlow 的 subflow 行为依赖「子节点 parentNode === groupId」+「子节点 extent === 'parent'」，
    //   拖动 group 时自动平移所有 parentNode 匹配的子节点。之前的实现是「如果节点已有 parentNode 就跳过」，
    //   导致被打组节点中若混杂了「已属于其它 group 的子节点」，会保留旧 parentNode，新 group 拖动时它不会跟随。
    //   现在显式对所有 ids 节点覆盖 parentNode/extent/position 相对坐标，确保每个子节点都正确归属新 group。
    const childUpdates = s.nodes.map((n) => {
      if (!ids.includes(n.id)) return n;
      return {
        ...n,
        parentNode: gid,
        // 关键修复（问题1）：移除 extent:'parent'。
        // 该约束会把子节点"焊死"在组框内，鼠标拖不出边界，从而永远触发不了"拖出即解组"。
        // ReactFlow 的父子跟随（拖组时子节点自动平移）由 parentNode 决定、与 extent 无关，
        // 因此移除 extent 后：拖组子节点仍跟随、子节点也能自由拖出组外。
        extent: undefined,
        draggable: true,
        position: { x: n.position.x - gx, y: n.position.y - gy },
        selected: false,
        // 子节点 zIndex 显式高于组容器(被 CSS 强制为 0)。
        // 这样即便组被选中、或 ReactFlow 未对子节点做选中抬升，子节点仍稳定位于组之上，
        // 不会被组容器 wrapper 拦截鼠标事件/遮挡连接点，从而能正常 hover 并显示连接点。
        zIndex: 1,
      };
    });

    set({ nodes: [groupNode, ...childUpdates], dirty: true });
    get().clearSelection();
    // 打组完成后主动选中 group 容器，让用户明确感知分组已创建；
    // 同时配合 CSS「非多选时隐藏 nodesselection-rect」，避免旧选区框残留
    // 与 group 容器边框叠加形成"两个框"。
    get().select(gid);
    setGroupingActive(false);
    return gid;
  },

  ungroupNode: (groupId) => {
    const s = get();
    const groupNode = s.nodes.find((n) => n.id === groupId);
    if (!groupNode || groupNode.type !== 'group') return;
    get().takeSnapshot();

    const grpData = groupNode.data as any;
    const childIds: string[] = grpData.childrenIds || [];

    // 子节点脱离父级：清除 parentNode/extent，将 position 转为绝对坐标
    const gp = groupNode.position;
    const updated = s.nodes.map((n) => {
      if (!childIds.includes(n.id)) return n;
      // 子节点当前 position 是相对于父容器的，加上父容器位置即为绝对坐标
      return {
        ...n,
        parentNode: undefined,
        extent: undefined,
        // 解组后恢复默认层级，避免遗留 group 时的 zIndex:1
        zIndex: 0,
        position: {
          x: n.position.x + gp.x,
          y: n.position.y + gp.y,
        },
      };
    });

    // 移除 Group 节点，并同步清空选中态（避免解组后残留选择框）
    set({
      nodes: updated.filter((n) => n.id !== groupId),
      dirty: true,
      selectedId: null,
      selectedIds: [],
    });
    // 强制 ReactFlow 节点 selected 字段与 store 一致
    get().select(null);
  },

  reLayoutGroup: (groupId, layout) => {
    const s = get();
    const gn = s.nodes.find((n) => n.id === groupId);
    if (!gn || gn.type !== 'group') return;
    get().takeSnapshot();

    const grpData = gn.data as any;
    const childIds: string[] = grpData.childrenIds || [];
    if (childIds.length === 0) return;

    const children = s.nodes.filter((n) => childIds.includes(n.id));
    const PAD = 24;   // 容器内边距，留出视觉呼吸空间
    const GAP = 32;   // 子节点间距（调大，避免拥挤）

    // ── 取节点实测尺寸（ReactFlow 渲染后写入 node.width/height）─────
    // 默认值对齐 CSS .pea-node { width: 340px } 及各类型节点的典型高度
    const nodeW = (n: any) => n.width ?? 340;
    const nodeH = (n: any) => n.height ?? 340;

    if (layout === 'horizontal') {
      // ── 水平布局：单行横向排列 ──
      let cx = PAD;
      children.forEach((n) => {
        const w = nodeW(n);
        Object.assign(n, { position: { x: cx, y: PAD } });
        cx += w + GAP;
      });
      const totalW = cx - GAP + PAD;
      const maxH = Math.max(...children.map((n) => nodeH(n))) + PAD * 2;
      set({
        nodes: s.nodes.map((n) => (n.id === gn.id ? { ...n, data: { ...gn.data, layout }, style: { width: totalW, height: maxH } } : children.find((c) => c.id === n.id) ?? n)),
        dirty: true,
      });
    } else {
      // ── 宫格布局：按 √n 列数网格（更方正的常规宫格），最多 4 列 ──
      // 用 √n 而非 Math.min(3,n)：节点少时（如 3 个）也能排成 2 列（2上1下），
      // 与"水平单行"明显区分；最多 4 列避免窄屏过宽。
      const cols = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(childIds.length))));
      const rows = Math.ceil(childIds.length / cols);
      // 用所有子节点中的最大宽高作为单元格尺寸，确保不重叠
      const cellW = Math.max(...children.map((n) => nodeW(n)));
      const cellH = Math.max(...children.map((n) => nodeH(n)));
      children.forEach((n, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        Object.assign(n, {
          position: { x: PAD + col * (cellW + GAP), y: PAD + row * (cellH + GAP) },
        });
      });
      const gw = cols * cellW + (cols - 1) * GAP + PAD * 2;
      const gh = rows * cellH + (rows - 1) * GAP + PAD * 2;
      set({
        nodes: s.nodes.map((n) => (n.id === gn.id ? { ...n, data: { ...gn.data, layout }, style: { width: gw, height: gh } } : children.find((c) => c.id === n.id) ?? n)),
        dirty: true,
      });
    }
  },

  /**
   * 处理"拖动节点使其进入/离开组"——根据节点当前画布坐标中心点判定：
   * - 已无 parentNode：扫一遍所有 group 节点，若中心点在 [gx, gy, gx+gw, gy+gh] 内则入组；
   *   若多个嵌套组都包含，取最深的（最小面积）以避免误归上级组。
   * - 已有 parentNode：把当前 rect 反算成画布绝对坐标（本地坐标 + parent.position），
   *   若中心点已落到父组视觉边界外，则脱离父级并转为绝对坐标。
   * 入组/脱离只更新父子关系与 childrenIds，组容器大小保持不变（用户要求打组后选择框固定）。
   */
  moveNodeToGroup: (nodeId) => {
    const s = get();
    const node = s.nodes.find((n) => n.id === nodeId);
    if (!node || node.type === 'group') return null;

    // 计算节点的画布绝对中心（处理 parentNode 子节点情况）
    const nodeW = (node as any).width ?? 240;
    const nodeH = (node as any).height ?? 180;
    const absCenter = node.parentNode
      ? (() => {
          const p = s.nodes.find((n) => n.id === node.parentNode);
          let absX = node.position.x, absY = node.position.y;
          if (p) { absX += p.position.x; absY += p.position.y; }
          return { x: absX + nodeW / 2, y: absY + nodeH / 2 };
        })()
      : { x: node.position.x + nodeW / 2, y: node.position.y + nodeH / 2 };

    if (node.parentNode) {
      // ── 已归属：判脱离 ──
      const parent = s.nodes.find((n) => n.id === node.parentNode);
      if (!parent || parent.type !== 'group') return null;
      const pw = (parent.style as any)?.width ?? parent.width ?? 240;
      const ph = (parent.style as any)?.height ?? parent.height ?? 160;
      const inside =
        absCenter.x >= parent.position.x &&
        absCenter.x <= parent.position.x + pw &&
        absCenter.y >= parent.position.y &&
        absCenter.y <= parent.position.y + ph;
      if (inside) return null; // 仍在组内，不动

      // 脱离：只解除父子关系，组容器大小保持不变
      get().takeSnapshot();
      const newChildren = ((parent.data as any).childrenIds || []).filter((cid: string) => cid !== nodeId);
      const updatedParent = {
        ...parent,
        data: { ...(parent.data as any), childrenIds: newChildren },
      };
      // 节点转为绝对坐标（保留当前视觉位置）
      const detached: any = {
        ...node,
        parentNode: undefined,
        extent: undefined,
        position: {
          x: node.position.x + parent.position.x,
          y: node.position.y + parent.position.y,
        },
        data: { ...(node.data as any), relativeOffset: undefined },
      };
      const finalNodes = s.nodes.map((n) => {
        if (n.id === parent.id) return updatedParent;
        if (n.id === nodeId) return detached;
        return n;
      });
      set({ nodes: finalNodes, dirty: true });
      return 'removed';
    }

    // ── 无 parentNode：扫一遍所有组找最深的容纳组 ──
    const groups = s.nodes.filter((n) => n.type === 'group');
    const candidates: { id: string; area: number }[] = [];
    for (const g of groups) {
      const gw = (g.style as any)?.width ?? g.width ?? 240;
      const gh = (g.style as any)?.height ?? g.height ?? 160;
      if (
        absCenter.x >= g.position.x &&
        absCenter.x <= g.position.x + gw &&
        absCenter.y >= g.position.y &&
        absCenter.y <= g.position.y + gh
      ) {
        candidates.push({ id: g.id, area: gw * gh });
      }
    }
    if (candidates.length === 0) return null;
    candidates.sort((a, b) => a.area - b.area); // 最深的（最小面积）
    const targetId = candidates[0].id;
    const target = s.nodes.find((n) => n.id === targetId);
    if (!target) return null;

    get().takeSnapshot();

    // 把节点坐标转为相对 target（保留当前视觉位置），组容器大小保持不变
    const newPos = {
      x: node.position.x - target.position.x,
      y: node.position.y - target.position.y,
    };

    const oldChildIds: string[] = ((target.data as any).childrenIds || []);
    const newChildIds = oldChildIds.includes(nodeId) ? oldChildIds : [...oldChildIds, nodeId];

    const updatedTarget = {
      ...target,
      data: { ...(target.data as any), childrenIds: newChildIds },
    };

    const updatedNodes = s.nodes.map((n) => {
      if (n.id === nodeId) {
        return {
          ...n,
          parentNode: targetId,
          extent: undefined,
          position: newPos,
        };
      }
      if (n.id === targetId) return updatedTarget;
      return n;
    });
    set({ nodes: updatedNodes, dirty: true });
    return 'added';
  },

  downloadGroup: (groupId) => {
    const s = get();
    const gn = s.nodes.find((n) => n.id === groupId);
    if (!gn || gn.type !== 'group') return;
    const grpData = gn.data as any;
    const childIds: string[] = grpData.childrenIds || [];

    const children = s.nodes
      .filter((n) => childIds.includes(n.id))
      .map((n) => ({
        id: n.id,
        type: n.type,
        label: (n.data as any)?.label,
        kind: (n.data as any)?.kind,
        prompt: (n.data as any)?.prompt,
        url: (n.data as any)?.url,
        resultUrl: (n.data as any)?.resultUrl,
        resultUrls: (n.data as any)?.resultUrls,
        html: (n.data as any)?.html,
      }));

    const edges = s.edges.filter(
      (e) => childIds.includes(e.source) && childIds.includes(e.target),
    );

    const payload = {
      group: { id: groupId, label: grpData.label || '新建组', layout: grpData.layout || 'grid' },
      nodes: children,
      edges: edges.map((e) => ({ source: e.source, target: e.target })),
      exportedAt: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${grpData.label || 'group'}_${groupId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
}));
