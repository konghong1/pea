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
  /** 批量添加边（用于多选插入节点后的自动连线）。 */
  addEdges: (newEdges: Edge[]) => void;
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
  /** 切换组内布局：grid(宫格) / horizontal(水平)。 */
  reLayoutGroup: (groupId: string, layout: 'grid' | 'horizontal') => void;
  /** 下载组：将组内所有节点的数据打包导出为 JSON 文件。 */
  downloadGroup: (groupId: string) => void;
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
    let ids = get().selectedIds;

    // 检测框选（box-selection）产生的 select 类型变更：
    // ReactFlow 在拖拽框选时会发出 type='select' 的 change，
    // 把被框选中的节点标记 selected=true / 未选中的标记 selected=false。
    // 此时需要反向同步：从节点 selected 状态回写 selectedIds，
    // 否则多选工具条等依赖 selectedIds.length > 1 的功能无法感知框选结果。
    const hasSelectChanges = changes.some((c: any) => c.type === 'select');
    if (hasSelectChanges) {
      ids = next.filter((n: any) => n.selected).map((n: any) => n.id);
    }

    // 受控选中：强制 node.selected 与 selectedIds 一致，
    // 避免 ReactFlow 内部选中（如拖动节点）制造"选中但没弹框/弹错框"的错乱。
    const reconciled = next.map((n: any) =>
      n.selected === ids.includes(n.id) ? n : { ...n, selected: ids.includes(n.id) },
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
      ...(hasSelectChanges ? {
        selectedIds: ids,
        selectedId: ids.length ? ids[ids.length - 1] : null,
      } : {}),
    });
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
    // 加载完成后异步核对：所有 generating=true 的节点拿 lastJobId 去后端查真实状态，
    // 防止 WS 事件丢失/页面重开导致节点永远停「生成中」（stale state）。
    // 没 lastJobId 的旧节点直接置 false（无法重建关联的 job）。
    void get().reconcileGeneratingNodes();
  },
  removeNode: (id) =>
    set((s) => {
      // 若删除的是组节点（type:'group'），必须同步清理其子节点；
      // 否则子节点的 parentNode 仍指向已删除的组 id，
      // ReactFlow 渲染时按 parentNode 查父节点找不到 → "Couldn't find parent node" / 白屏崩溃。
      const target = s.nodes.find((n) => n.id === id);
      const childIds: string[] =
        target?.type === 'group' ? ((target.data as any)?.childrenIds ?? []) : [];
      // 同时把 parentNode 指向该组的孤立子节点也一并移除（防御：childrenIds 可能漏记）
      const orphanIds = s.nodes
        .filter((n) => n.parentNode === id && !childIds.includes(n.id))
        .map((n) => n.id);
      const removeSet = new Set([id, ...childIds, ...orphanIds]);
      return {
        nodes: s.nodes.filter((n) => !removeSet.has(n.id)),
        edges: s.edges.filter(
          (e) => !removeSet.has(e.source) && !removeSet.has(e.target),
        ),
        selectedId: s.selectedId != null && removeSet.has(s.selectedId) ? null : s.selectedId,
        selectedIds: s.selectedIds.filter((x) => !removeSet.has(x)),
        dirty: true,
      };
    }),
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
  addEdges: (newEdges) =>
    set((s) => ({
      edges: [...s.edges, ...newEdges.map((e) => ({ ...e, type: e.type || 'pea' }))],
      dirty: true,
    })),
  insertNodeForSelection: (kind, label) => {
    const s = get();
    const selIds = s.selectedIds;
    if (selIds.length === 0) return null;

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

    set({
      nodes: [...s.nodes, newNode],
      edges: [
        // 保留不被替换的边
        ...s.edges.filter((e) => !oldEdgeIds.has(e.id)),
        // 新增：选中→新节点 + 新节点→原目标
        ...edgesToNew,
        ...edgesFromNew,
      ],
      dirty: true,
      // 保持当前多选状态不变（不切换到新节点）
    });

    return nid;
  },

  // ═══════════════════════════════════════════════════════════════
  // 打组 / 解组 / 布局 / 下载
  // ═══════════════════════════════════════════════════════════════

  groupNodes: (nodeIds) => {
    const s = get();
    if (nodeIds.length < 2) return null;
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

    const PAD = 28; // 容器内边距
    const gw = maxX - minX + PAD * 2;
    const gh = maxY - minY + PAD * 2;
    const gx = minX - PAD;
    const gy = minY - PAD;

    const gid = `group_${Date.now()}`;

    // 创建 Group 节点
    const groupNode: any = {
      id: gid,
      type: 'group',
      position: { x: gx, y: gy },
      data: { label: '新建组', layout: 'grid', childrenIds: ids },
      // ReactFlow 父子容器属性
      style: { width: gw, height: gh },
    };

    // 将子节点的 parentNode 指向 group，并把坐标转为相对于 group 原点。
    // ReactFlow 的 subflow 中，子节点 position 是相对父容器而言的；保留绝对坐标会导致
    // 子节点跑到容器外部，出现"打组后节点不在组内"的问题。
    const childUpdates = s.nodes.map((n) => {
      if (!ids.includes(n.id)) return n;
      return {
        ...n,
        parentNode: gid,
        extent: 'parent' as const,
        position: { x: n.position.x - gx, y: n.position.y - gy },
        selected: false,
      };
    });

    set({ nodes: [groupNode, ...childUpdates], dirty: true });
    get().clearSelection();
    return gid;
  },

  ungroupNode: (groupId) => {
    const s = get();
    const groupNode = s.nodes.find((n) => n.id === groupId);
    if (!groupNode || groupNode.type !== 'group') return;

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
        position: {
          x: n.position.x + gp.x,
          y: n.position.y + gp.y,
        },
      };
    });

    // 移除 Group 节点
    set({
      nodes: updated.filter((n) => n.id !== groupId),
      dirty: true,
    });
  },

  reLayoutGroup: (groupId, layout) => {
    const s = get();
    const gn = s.nodes.find((n) => n.id === groupId);
    if (!gn || gn.type !== 'group') return;

    const grpData = gn.data as any;
    const childIds: string[] = grpData.childrenIds || [];
    if (childIds.length === 0) return;

    const children = s.nodes.filter((n) => childIds.includes(n.id));
    const PAD = 28;
    const GAP = 16;

    if (layout === 'horizontal') {
      // ── 水平布局：单行横向排列 ──
      let cx = PAD;
      children.forEach((n) => {
        const w = (n as any).width ?? 200;
        Object.assign(n, { position: { x: cx, y: PAD } });
        cx += w + GAP;
      });
      const totalW = cx - GAP + PAD;
      const maxH = Math.max(...children.map((n) => ((n as any).height ?? 160))) + PAD * 2;
      set({
        nodes: s.nodes.map((n) => (n.id === gn.id ? { ...n, data: { ...gn.data, layout }, style: { width: totalW, height: maxH } } : children.find((c) => c.id === n.id) ?? n)),
        dirty: true,
      });
    } else {
      // ── 宫格布局：尽量均分到 3 列（或更少） ──
      const cols = Math.min(3, childIds.length);
      const rows = Math.ceil(childIds.length / cols);
      const cellW = 220; // 近似节点宽度
      const cellH = 180; // 近似节点高度
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
