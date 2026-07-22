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

export type PeaNodeData = {
  label: string;
  kind: 'prompt' | 'image' | 'generate' | 'text';
  prompt?: string;
};

interface CanvasState {
  canvasId: number | null;
  version: number;
  nodes: Node<PeaNodeData>[];
  edges: Edge[];
  selectedId: string | null;
  dirty: boolean;

  setCanvasMeta: (id: number, version: number) => void;
  onNodesChange: (c: NodeChange[]) => void;
  onEdgesChange: (c: EdgeChange[]) => void;
  onConnect: (c: Connection) => void;
  addNode: (data: PeaNodeData, position: { x: number; y: number }) => void;
  updateNodeData: (id: string, patch: Partial<PeaNodeData>) => void;
  select: (id: string | null) => void;
  markSaved: (version: number) => void;
  loadGraph: (nodes: Node<PeaNodeData>[], edges: Edge[], version: number) => void;
}

let seq = 1;
const nextId = () => `n${seq++}`;

export const useCanvas = create<CanvasState>((set, get) => ({
  canvasId: null,
  version: 0,
  nodes: [],
  edges: [],
  selectedId: null,
  dirty: false,

  setCanvasMeta: (id, version) => set({ canvasId: id, version }),
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
  markSaved: (version) => set({ version, dirty: false }),
  loadGraph: (nodes, edges, version) => set({ nodes, edges, version, dirty: false }),
}));
