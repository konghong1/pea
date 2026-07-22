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

export type PeaNodeData = {
  label: string;
  kind: 'prompt' | 'image' | 'generate' | 'text';
  prompt?: string;
  html?: string;
};

interface CanvasState {
  canvasId: number | null;
  version: number;
  title: string;
  nodes: Node<PeaNodeData>[];
  edges: Edge[];
  selectedId: string | null;
  dirty: boolean;
  saveCount: number;
  clipboard: Node<PeaNodeData> | null;

  setCanvasMeta: (id: number, version: number, title?: string) => void;
  onNodesChange: (c: NodeChange[]) => void;
  onEdgesChange: (c: EdgeChange[]) => void;
  onConnect: (c: Connection) => void;
  addNode: (data: PeaNodeData, position: { x: number; y: number }) => void;
  updateNodeData: (id: string, patch: Partial<PeaNodeData>) => void;
  select: (id: string | null) => void;
  markSaved: (version: number) => void;
  loadGraph: (nodes: Node<PeaNodeData>[], edges: Edge[], version: number) => void;
  openCanvas: (id: number) => Promise<void>;
  removeNode: (id: string) => void;
  duplicateNode: (id: string) => void;
  copySelected: () => void;
  pasteNode: () => void;
  bumpSave: () => void;
}

let seq = 1;
const nextId = () => `n${seq++}`;

export const useCanvas = create<CanvasState>((set, get) => ({
  canvasId: null,
  version: 0,
  title: '我的画布',
  nodes: [],
  edges: [],
  selectedId: null,
  dirty: false,
  saveCount: 0,
  clipboard: null,

  setCanvasMeta: (id, version, title) =>
    set({ canvasId: id, version, ...(title !== undefined ? { title } : {}) }),
  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) as any, dirty: true }),
  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges), dirty: true }),
  onConnect: (conn) => set({ edges: addEdge(conn, get().edges), dirty: true }),
  addNode: (data, position) => {
    const id = nextId();
    const node: Node<PeaNodeData> = { id, type: 'pea', position, data };
    set({ nodes: [...get().nodes, node], dirty: true, selectedId: id });
  },
  updateNodeData: (id, patch) =>
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...patch } } : n,
      ),
      dirty: true,
    }),
  select: (id) => set({ selectedId: id }),
  markSaved: (version) => set({ version, dirty: false, saveCount: get().saveCount + 1 }),
  loadGraph: (nodes, edges, version) => set({ nodes, edges, version, dirty: false }),
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
    set({ nodes: graph.nodes ?? [], edges: graph.edges ?? [], version: g.data.version, dirty: false });
  },
  removeNode: (id) =>
    set({
      nodes: get().nodes.filter((n) => n.id !== id),
      edges: get().edges.filter((e) => e.source !== id && e.target !== id),
      selectedId: get().selectedId === id ? null : get().selectedId,
      dirty: true,
    }),
  duplicateNode: (id) => {
    const src = get().nodes.find((n) => n.id === id);
    if (!src) return;
    const nid = nextId();
    const copy: Node<PeaNodeData> = {
      id: nid,
      type: 'pea',
      position: { x: src.position.x + 40, y: src.position.y + 40 },
      data: { ...src.data },
    };
    set({ nodes: [...get().nodes, copy], selectedId: nid, dirty: true });
  },
  copySelected: () => {
    const sel = get().nodes.find((n) => n.id === get().selectedId);
    if (sel) set({ clipboard: sel });
  },
  pasteNode: () => {
    const clip = get().clipboard;
    if (!clip) return;
    const nid = nextId();
    const copy: Node<PeaNodeData> = {
      id: nid,
      type: 'pea',
      position: { x: clip.position.x + 60, y: clip.position.y + 60 },
      data: { ...clip.data },
    };
    set({ nodes: [...get().nodes, copy], selectedId: nid, dirty: true });
  },
  bumpSave: () => set({ saveCount: get().saveCount + 1 }),
}));
