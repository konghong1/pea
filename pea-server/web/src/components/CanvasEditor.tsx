import { useEffect, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { App, Button, Tooltip } from 'antd';
import { api } from '../api/client';
import { useCanvas, PeaNodeData } from '../store/canvas';
import PeaNode from './PeaNode';
import Inspector from './Inspector';

const nodeTypes = { pea: PeaNode };

function Flow() {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, select, canvasId, version, dirty, setCanvasMeta, markSaved, loadGraph } =
    useCanvas();
  const { screenToFlowPosition } = useReactFlow();
  const { message } = App.useApp();
  const saveTimer = useRef<number>();

  // 首次进入: 确保有一个画布并载入其图
  useEffect(() => {
    (async () => {
      if (canvasId != null) return;
      const { data } = await api.post('/canvases', { title: '我的画布' });
      setCanvasMeta(data.id, data.version);
      const g = await api.get(`/canvases/${data.id}`);
      const graph = typeof g.data.graph_json === 'string' ? JSON.parse(g.data.graph_json) : g.data.graph_json;
      loadGraph(graph.nodes ?? [], graph.edges ?? [], g.data.version);
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

  const add = (kind: PeaNodeData['kind'], label: string) => {
    const pos = screenToFlowPosition({ x: 200 + Math.random() * 120, y: 120 + Math.random() * 120 });
    addNode({ kind, label, prompt: kind === 'generate' ? '' : undefined }, pos);
  };

  return (
    <div className="flex h-full">
      <div className="relative flex-1">
        <div className="absolute left-3 top-3 z-10 flex gap-2">
          <Tooltip title="添加文本节点">
            <Button size="small" onClick={() => add('text', '文本')}>文本</Button>
          </Tooltip>
          <Tooltip title="添加图片节点">
            <Button size="small" onClick={() => add('image', '图片')}>图片</Button>
          </Tooltip>
          <Tooltip title="添加生成节点">
            <Button size="small" type="primary" onClick={() => add('generate', '生成')}>⚡ 生成</Button>
          </Tooltip>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, n) => select(n.id)}
          onPaneClick={() => select(null)}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
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
