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

export type PeaNodeData = {
  label: string;
  kind: PeaNodeKind;
  prompt?: string;
  html?: string;
  url?: string;           // 用户上传的文件 URL
  resultUrl?: string;     // 模型生成的结果 URL（图片/视频等）
  generating?: boolean;   // 是否正在生成中
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
    set({ nodes: reconciled, dirty: true });
  },
  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges), dirty: true }),
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
    const g = await api.get(`/canvases/${id}`);
    const raw = g.data.graph_json;
    const graph =
      typeof raw === 'string'
        ? raw
          ? JSON.parse(raw)
          : { nodes: [], edges: [] }
        : raw ?? { nodes: [], edges: [] };
    set({ canvasId: g.data.id, version: g.data.version, title: g.data.title, dirty: false });
    set({
      nodes: graph.nodes ?? [],
      edges: (graph.edges ?? []).map((e: Edge) => (e.type ? e : { ...e, type: 'pea' })),
      version: g.data.version,
      dirty: false,
    });
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
}));
