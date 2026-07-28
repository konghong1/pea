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
  savedToLibrary?: boolean; // 是否已保存到素材库
  generating?: boolean;   // 是否正在生成中
  /** 最近一次生成任务的 jobId（受理成功后写入）。
   *  关键：用于加载画布时与后端核对真实状态，防止 WS 事件丢失后节点永远卡在 generating。 */
  lastJobId?: string;
  error?: string;         // 生成失败原因（终态写回节点，用于节点内失败卡展示）
  /** 新建节点时的画幅比例（如 "9:16"、"16:9"），用于空白节点框比例。
      有内容后节点按实际媒体比例包裹，此字段不再影响显示。 */
  aspectRatio?: string;
  params?: Record<string, unknown>; // 生成参数（模型、分辨率、比例等，供 lightbox 信息面板展示）
  meta?: Record<string, unknown>;
};

interface CanvasState {
  canvasId: number | null;
  version: number;
  title: string;
  nodes: Node<PeaNodeData>[];
  edges: Edge[];
  selectedId: string | null;
  selectedIds: string[];
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
  updateNodeData: (id: string, patch: Partial<PeaNodeData>) => void;
  select: (id: string | null) => void;
  toggleSelect: (id: string) => void;
  setSelection: (ids: string[]) => void;
  clearSelection: () => void;
  markSaved: (version: number) => void;
  loadGraph: (nodes: Node<PeaNodeData>[], edges: Edge[], version: number) => void;
  openCanvas: (id: number) => Promise<void>;
  removeNode: (id: string) => void;
  duplicateNode: (id: string) => void;
  addConnected: (fromId: string) => void;
  copySelected: () => void;
  pasteNode: () => void;
  bumpSave: () => void;
  /** 获取某节点的直接上游输入节点（按边建立顺序排序）。 */
  getUpstreamInputs: (nodeId: string) => Node<PeaNodeData>[];
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

export const useCanvas = create<CanvasState>((set, get) => ({
  canvasId: null,
  version: 0,
  title: '我的画布',
  nodes: [],
  edges: [],
  selectedId: null,
  selectedIds: [],
  dirty: false,
  lastSavedAt: null,
  saveCount: 0,
  clipboard: null,
  jobNodeMap: {},
  defaultAspectRatio: '9:16',   // 图片节点默认竖海报比例

  setDefaultAspectRatio: (ratio) => set({ defaultAspectRatio: ratio }),

  setCanvasMeta: (id, version, title) =>
    set({ canvasId: id, version, ...(title !== undefined ? { title } : {}) }),
  onNodesChange: (changes) => {
    const next = applyNodeChanges(changes, get().nodes) as any;
    const ids = get().selectedIds;
    // 受控选中：强制 node.selected 与 selectedIds 一致，
    // 避免 ReactFlow 内部选中（如拖动节点）制造“选中但没弹框/弹错框”的错乱。
    const reconciled = next.map((n: any) =>
      n.selected === ids.includes(n.id) ? n : { ...n, selected: ids.includes(n.id) },
    );
    // 仅用户实质变更（拖动 position / 增删 / replace）才标脏。
    // dimensions(ReactFlow 加载时尺寸测量) 与 select(受控选中) 是内部事件，
    // 不标脏——否则「进入画布即被自动保存」，导致 version 无谓递增、写放大、乐观锁冲突。
    const isUserChange = changes.some(
      (c: any) => c.type === 'position' || c.type === 'remove' || c.type === 'add' || c.type === 'replace',
    );
    set({ nodes: reconciled, dirty: isUserChange ? true : get().dirty });
  },
  onEdgesChange: (changes) => {
    // 同上：select(受控选中) 不标脏，仅 remove/add/position 等实质变更标脏。
    const isUserChange = changes.some(
      (c: any) => c.type === 'remove' || c.type === 'add' || c.type === 'position',
    );
    set({ edges: applyEdgeChanges(changes, get().edges), dirty: isUserChange ? true : get().dirty });
  },
  onConnect: (conn) => set({ edges: addEdge({ ...conn, type: 'pea' }, get().edges), dirty: true }),
  removeEdge: (id) => set({ edges: get().edges.filter((e) => e.id !== id), dirty: true }),
  addNode: (data, position) => {
    const nodes = get().nodes;
    const id = nextId(nodes);
    const node: Node<PeaNodeData> = { id, type: 'pea', position, data, selected: true };
    set({
      nodes: [...nodes.map((n) => ({ ...n, selected: false })), node],
      dirty: true,
      selectedId: id,
      selectedIds: [id],
    });
    return id;
  },
  updateNodeData: (id, patch) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...patch } } : n,
      ),
      dirty: true,
    }),
  select: (id) =>
    set((s) => ({
      selectedId: id,
      selectedIds: id ? [id] : [],
      nodes: s.nodes.map((n) => ({ ...n, selected: !!id && n.id === id })),
    })),
  toggleSelect: (id) =>
    set((s) => {
      const has = s.selectedIds.includes(id);
      const next = has ? s.selectedIds.filter((x) => x !== id) : [...s.selectedIds, id];
      const selId = next.length ? (has ? next[next.length - 1] || id : id) : null;
      return {
        selectedIds: next,
        selectedId: selId,
        nodes: s.nodes.map((n) => ({ ...n, selected: next.includes(n.id) })),
      };
    }),
  setSelection: (ids) =>
    set((s) => ({
      selectedIds: ids,
      selectedId: ids.length ? ids[ids.length - 1] : null,
      nodes: s.nodes.map((n) => ({ ...n, selected: ids.includes(n.id) })),
    })),
  clearSelection: () =>
    set((s) => ({
      selectedIds: [],
      selectedId: null,
      nodes: s.nodes.map((n) => ({ ...n, selected: false })),
    })),
  markSaved: (version) => set({ version, dirty: false, lastSavedAt: Date.now(), saveCount: get().saveCount + 1 }),
  loadGraph: (nodes, edges, version) =>
    set({
      nodes,
      edges: (edges ?? []).map((e: Edge) => (e.type ? e : { ...e, type: 'pea' })),
      version,
      dirty: false,
    }),
  openCanvas: async (id) => {
    // 打开前先清空上一个画布的残留状态（nodes/edges/选中），
    // 防止切换项目时旧画布内容闪现，或请求失败时旧内容被误当作新画布展示。
    set({ nodes: [], edges: [], selectedId: null, selectedIds: [], dirty: false, jobNodeMap: {} });
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
    const cleanNode = (n: any) => ({
      id: n.id,
      type: n.type || 'pea',
      position: n.position || { x: 0, y: 0 },
      data: n.data || {},
    });
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
    // 加载完成后异步核对：所有 generating=true 的节点拿 lastJobId 去后端查真实状态，
    // 防止 WS 事件丢失/页面重开导致节点永远停「生成中」（stale state）。
    // 没 lastJobId 的旧节点直接置 false（无法重建关联的 job）。
    void get().reconcileGeneratingNodes();
  },
  removeNode: (id) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
      selectedIds: s.selectedIds.filter((x) => x !== id),
      dirty: true,
    })),
  duplicateNode: (id) => {
    const src = get().nodes.find((n) => n.id === id);
    if (!src) return;
    const nid = nextId(get().nodes);
    const copy: Node<PeaNodeData> = {
      id: nid,
      type: 'pea',
      position: { x: src.position.x + 40, y: src.position.y + 40 },
      data: { ...src.data },
      selected: true,
    };
    set({
      nodes: [...get().nodes.map((n) => ({ ...n, selected: false })), copy],
      selectedId: nid,
      selectedIds: [nid],
      dirty: true,
    });
  },
  addConnected: (fromId) => {
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
      // 1) 正常路径: jobNodeMap 找到 -> 直接 patch
      const nodeId = s.jobNodeMap[jobId];
      if (nodeId) {
        return {
          dirty: true,
          nodes: s.nodes.map((n) =>
            n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n,
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
            n.id === fallbackId ? { ...n, data: { ...n.data, ...patch } } : n,
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
}));
