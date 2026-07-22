import { useEffect, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { App, Button, Tooltip } from 'antd';
import { MenuOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import { useCanvas, PeaNodeData } from '../store/canvas';
import PeaNode from './PeaNode';
import Inspector from './Inspector';
import AgentPanel from './AgentPanel';
import SidePanel from './SidePanel';

const nodeTypes = { pea: PeaNode };

interface MenuState {
  x: number;
  y: number;
  nodeId: string | null;
}

function Flow() {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    select,
    canvasId,
    version,
    dirty,
    setCanvasMeta,
    markSaved,
    loadGraph,
    removeNode,
    duplicateNode,
    copySelected,
    pasteNode,
  } = useCanvas();
  const { screenToFlowPosition, fitView } = useReactFlow();
  const { message } = App.useApp();
  const saveTimer = useRef<number>();
  const [sideOpen, setSideOpen] = useState(false);
  const [menu, setMenu] = useState<MenuState | null>(null);

  // 首次进入: 确保有一个画布并载入其图
  useEffect(() => {
    (async () => {
      if (canvasId != null) return;
      const { data } = await api.post('/canvases', { title: '我的画布' });
      setCanvasMeta(data.id, data.version, '我的画布');
      const g = await api.get(`/canvases/${data.id}`);
      const raw = g.data.graph_json;
      const graph =
        typeof raw === 'string'
          ? raw
            ? JSON.parse(raw)
            : { nodes: [], edges: [] }
          : raw ?? { nodes: [], edges: [] };
      loadGraph(graph.nodes ?? [], graph.edges ?? [], g.data.version);
      if (g.data.title) setCanvasMeta(g.data.id, g.data.version, g.data.title);
    })().catch(() => message.error('画布初始化失败'));
  }, [canvasId, setCanvasMeta, loadGraph]);

  // 防抖自动保存 (PRD 痛点: 刷新即丢) — debounce 1s
  useEffect(() => {
    if (!dirty || canvasId == null) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      try {
        const graph = { nodes, edges };
        const { data } = await api.put(`/canvases/${canvasId}`, { graph_json: graph, version });
        markSaved(data.version);
      } catch (e: any) {
        if (e?.response?.status === 409) {
          message.warning('画布已被他人更新，请刷新');
        } else {
          message.error('保存失败');
        }
      }
    }, 1000);
    return () => window.clearTimeout(saveTimer.current);
  }, [nodes, edges, dirty, canvasId, version, markSaved]);

  // 立即保存 (Ctrl+S)
  const saveNow = async () => {
    if (canvasId == null) return;
    try {
      const { data } = await api.put(`/canvases/${canvasId}`, { graph_json: { nodes, edges }, version });
      markSaved(data.version);
      message.success('已保存');
    } catch {
      message.error('保存失败');
    }
  };

  const add = (kind: PeaNodeData['kind'], label: string) => {
    const pos = screenToFlowPosition({ x: 200 + Math.random() * 120, y: 120 + Math.random() * 120 });
    addNode({ kind, label, prompt: kind === 'generate' ? '' : undefined }, pos);
  };

  // 快捷键 (T-M1-Next-02, FR-M1-70~71)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const editing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
      const sel = useCanvas.getState().selectedId;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        saveNow();
        return;
      }
      if (editing) return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && sel) {
        e.preventDefault();
        removeNode(sel);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        copySelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
        pasteNode();
      } else if (e.key.toLowerCase() === 'f') {
        fitView();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [removeNode, copySelected, pasteNode, fitView]);

  const onNodeCtx = (e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, nodeId: node.id });
  };
  const onPaneCtx = (e: React.MouseEvent) => {
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, nodeId: null });
  };

  return (
    <div className="flex h-full">
      <div className="relative flex-1">
        {/* 顶部工具栏 */}
        <div className="absolute left-3 top-3 z-10 flex gap-2">
          <Tooltip title="侧边面板">
            <Button size="small" icon={<MenuOutlined />} aria-label="侧边面板" onClick={() => setSideOpen((v) => !v)} />
          </Tooltip>
          <Tooltip title="添加文本节点">
            <Button size="small" aria-label="添加文本节点" onClick={() => add('text', '文本')}>文本</Button>
          </Tooltip>
          <Tooltip title="添加图片节点">
            <Button size="small" aria-label="添加图片节点" onClick={() => add('image', '图片')}>图片</Button>
          </Tooltip>
          <Tooltip title="添加生成节点">
            <Button size="small" type="primary" aria-label="添加生成节点" onClick={() => add('generate', '生成')}>⚡ 生成</Button>
          </Tooltip>
        </div>

        {sideOpen && <SidePanel onClose={() => setSideOpen(false)} />}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, n) => select(n.id)}
          onPaneClick={() => {
            select(null);
            setMenu(null);
          }}
          onNodeContextMenu={onNodeCtx}
          onPaneContextMenu={onPaneCtx}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>

        <AgentPanel />

        {/* 右键上下文菜单 */}
        {menu && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
            <div
              className="fixed z-50 min-w-[140px] rounded-lg border border-black/10 bg-white py-1 text-sm shadow-xl dark:border-white/10 dark:bg-[#1c1c24]"
              style={{ left: menu.x, top: menu.y }}
            >
              {menu.nodeId ? (
                <>
                  <button
                    className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10"
                    onClick={() => {
                      select(menu.nodeId);
                      setMenu(null);
                    }}
                  >
                    重命名
                  </button>
                  <button
                    className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10"
                    onClick={() => {
                      duplicateNode(menu.nodeId!);
                      setMenu(null);
                    }}
                  >
                    复制
                  </button>
                  <button
                    className="block w-full px-3 py-1.5 text-left text-red-500 hover:bg-red-500/10"
                    onClick={() => {
                      removeNode(menu.nodeId!);
                      setMenu(null);
                    }}
                  >
                    删除
                  </button>
                </>
              ) : (
                <>
                  <button className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10" onClick={() => { add('text', '文本'); setMenu(null); }}>添加文本</button>
                  <button className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10" onClick={() => { add('image', '图片'); setMenu(null); }}>添加图片</button>
                  <button className="block w-full px-3 py-1.5 text-left hover:bg-pea-brand/10" onClick={() => { add('generate', '生成'); setMenu(null); }}>添加生成</button>
                </>
              )}
            </div>
          </>
        )}
      </div>
      <Inspector />
    </div>
  );
}

export default function CanvasEditor() {
  return (
    <ReactFlowProvider>
      <Flow />
    </ReactFlowProvider>
  );
}
