import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useViewport } from 'reactflow';
import { useCanvas, PeaNodeData } from '../store/canvas';
import { PeaNodeKind, NODE_DEF_OF } from '../constants/nodeTypes';
import {
  PlusOutlined,
  DownloadOutlined,
  AppstoreOutlined,
  CommentOutlined,
  DeleteOutlined,
  MoreOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';

/**
 * 多选工具条 —— 当选中多个节点（selectedIds.length > 1）时显示。
 *
 * 包含两部分：
 * 1. 选择区域**下方**的浮动工具栏（操作按钮）
 * 2. 选择区域**中心**的圆形"+"添加按钮（点击弹出节点选择器）
 *
 * 定位方式：rAF 循环读取选中节点的 DOM getBoundingClientRect，
 * 计算包围盒，分别定位工具栏（底部居中）和+按钮（中心）。
 * 与 TextNodeToolbar 同模式，支持拖拽跟随。
 */
export default function MultiSelectToolbar() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const nodes = useCanvas((s) => s.nodes);
  const edges = useCanvas((s) => s.edges);
  const insertNodeForSelection = useCanvas((s) => s.insertNodeForSelection);
  const clearSelection = useCanvas((s) => s.clearSelection);
  const groupNodes = useCanvas((s) => s.groupNodes);
  const viewport = useViewport();

  const isMultiSelect = selectedIds.length > 1;

  // 延迟显示：让 SelectionOverlay 先完成淡出（120ms），再展示打组工具栏
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (isMultiSelect) {
      timerRef.current = setTimeout(() => setVisible(true), 150);
    } else {
      setVisible(false);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isMultiSelect]);

  // 计算选中节点的包围盒（用于定位）
  const [bounds, setBounds] = useState<{
    /** 工具栏位置（选择区域下方居中） */
    bar: { left: number; top: number } | null;
    /** + 按钮位置（选择区域正中心） */
    plus: { left: number; top: number } | null;
  } | null>(null);

  // 节点选择器弹窗状态
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerAt, setPickerAt] = useState<{ left: number; top: number } | null>(null);

  // 选中节点的 source 边信息（用于选择器中展示"将被连接的线"）
  const sourceEdgesInfo = (() => {
    if (!isMultiSelect) return [];
    return edges
      .filter((e) => selectedIds.includes(e.source))
      .map((e) => ({
        edgeId: e.id,
        sourceId: e.source,
        targetId: e.target,
        sourceLabel: nodes.find((n) => n.id === e.source)?.data.label ?? e.source,
        targetLabel: nodes.find((n) => n.id === e.target)?.data.label ?? e.target,
      }));
  })();

  const rafRef = useRef<number>();
  const lastKeyRef = useRef('');

  // rAF 定位循环
  useEffect(() => {
    if (!isMultiSelect) {
      setBounds(null);
      lastKeyRef.current = '';
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const updatePos = () => {
      const els: DOMRect[] = [];
      for (const id of selectedIds) {
        const el = document.querySelector(`.react-flow__node[data-id="${id}"]`) as HTMLElement | null;
        if (el) els.push(el.getBoundingClientRect());
      }
      if (els.length === 0) return;

      // 合并所有选中节点的包围盒
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      els.forEach((r) => {
        minX = Math.min(minX, r.left);
        minY = Math.min(minY, r.top);
        maxX = Math.max(maxX, r.right);
        maxY = Math.max(maxY, r.bottom);
      });

      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;

      // 工具栏：在包围盒**上方**居中，间距 24px（对齐参考图：功能条在选择框正上方，留出清晰间距）
      const barLeft = Math.round(centerX);
      const barTop = Math.round(minY - 24 - 40); // 40 ≈ 工具栏高度，让工具栏底部与选区顶部保持 24px 间距

      // + 按钮：在包围盒「右侧」，垂直居中，与节点框同距（复用 HANDLE_GAP=24）。
      // 按钮半宽约 23px，故 center = maxX + 24(同距) + 23，使按钮近边距框 = 24px。
      const NODE_GAP = 24;
      const plusLeft = Math.round(maxX + NODE_GAP + 23);
      const plusTop = Math.round(centerY);

      const key = `${barLeft},${barTop},${plusLeft},${plusTop},${selectedIds.join(',')}`;
      if (lastKeyRef.current !== key) {
        lastKeyRef.current = key;
        setBounds({
          bar: { left: barLeft, top: barTop },
          plus: { left: plusLeft, top: plusTop },
        });
      }
    };

    const loop = () => {
      updatePos();
      rafRef.current = requestAnimationFrame(loop);
    };

    updatePos();
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isMultiSelect, selectedIds.join(','), viewport.x, viewport.y, viewport.zoom]);

  // --- 操作 handlers ---

  const handleAddNode = useCallback(() => {
    if (!bounds?.plus) return;
    setPickerAt(bounds.plus);
    setPickerOpen(true);
  }, [bounds]);

  const handlePickNode = useCallback((kind: PeaNodeKind) => {
    const def = NODE_DEF_OF(kind);
    const newId = insertNodeForSelection(kind, def.label);
    setPickerOpen(false);
    return newId;
  }, [insertNodeForSelection]);

  const handleDeleteSelected = useCallback(() => {
    // 一次性删除所有选中节点（合并为单条撤销项，removeNodes 会自动级联清理关联边与子节点）
    const ids = [...selectedIds];
    useCanvas.getState().removeNodes(ids);
  }, [selectedIds]);

  const handlePack = useCallback(() => {
    groupNodes(selectedIds);
  }, [selectedIds, groupNodes]);

  const handleJoinConversation = useCallback(() => {
    // TODO: 加入对话功能 — 后续实现
    console.log('[MultiSelectToolbar] join conversation:', selectedIds);
  }, [selectedIds]);

  const handleDownload = useCallback(() => {
    // TODO: 批量下载 — 后续实现
    console.log('[MultiSelectToolbar] download selected:', selectedIds);
  }, [selectedIds]);

  // 渲染守卫：必须是多选且延迟已到期才渲染
  if (!isMultiSelect || !visible || !bounds || !bounds.bar || !bounds.plus) return null;
  const { bar, plus } = bounds;

  const toolbar = (
    <>
      {/* ====== 1. 选中框右侧「添加节点」按钮（节点卡样式） ====== */}
      <div
        className="multiselect-plus-btn"
        data-pea-canvas-portal
        style={{ left: plus.left, top: plus.top }}
        onClick={handleAddNode}
        title="在此处插入节点"
        role="button"
        aria-label="插入节点"
        tabIndex={0}
      >
        <span className="multiselect-plus-inner">
          <PlusOutlined className="mpi-icon" />
          <span className="mpi-label">添加</span>
        </span>
      </div>

      {/* ====== 2. 下方工具栏 ====== */}
      <div
        className="multiselect-toolbar"
        data-pea-canvas-portal
        style={{ left: bar.left, top: bar.top }}
        role="toolbar"
        aria-label="多选操作"
        data-selected-count={selectedIds.length}
      >
        <div className="mst-inner">
          <button className="mst-btn" onClick={handleJoinConversation} title="加入对话">
            <CommentOutlined /> <span>加入对话</span>
          </button>
          <button className="mst-btn" onClick={handlePack} title="打组">
            <AppstoreOutlined /> <span>打组</span>
          </button>

          <div className="mst-sep" />

          {/* 插入节点按钮（高亮） */}
          <button className="mst-btn mst-primary" onClick={handleAddNode} title="插入节点">
            <PlusOutlined />
          </button>

          <div className="mst-sep" />

          <button className="mst-btn" onClick={handleDownload} title="下载">
            <DownloadOutlined />
          </button>

          <button className="mst-btn mst-more" title="更多操作">
            <MoreOutlined />
          </button>

          <div className="mst-sep" />

          <button
            className="mst-btn mst-danger"
            onClick={handleDeleteSelected}
            title={`删除选中 (${selectedIds.length})`}
          >
            <DeleteOutlined />
          </button>
        </div>

        {/* 选中数量角标 */}
        <span className="mst-count">{selectedIds.length}</span>
      </div>

      {/* ====== 3. 节点选择器弹窗 ====== */}
      {pickerOpen && pickerAt && (
        <MultiSelectNodePicker
          at={pickerAt}
          sourceEdges={sourceEdgesInfo}
          selectedCount={selectedIds.length}
          onPick={handlePickNode}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </>
  );

  // 使用 Portal 渲染到 body，避免被 ReactFlow viewport / 组节点 / 选中节点等高 z-index 元素遮挡
  return typeof document !== 'undefined' ? createPortal(toolbar, document.body) : null;
}

/**
 * 多选场景下的节点选择器。
 * 展示可选节点类型列表，以及当前选中节点的 source 连线预览，
 * 让用户直观看到"哪些线会被连接到新节点"。
 */
function MultiSelectNodePicker({
  at,
  sourceEdges,
  selectedCount,
  onPick,
  onClose,
}: {
  at: { left: number; top: number };
  sourceEdges: { edgeId: string; sourceId: string; sourceLabel: string; targetId: string; targetLabel: string }[];
  selectedCount: number;
  onPick: (k: PeaNodeKind) => void;
  onClose: () => void;
}) {
  const [hoverKind, setHoverKind] = useState<PeaNodeKind | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // 常用节点类型（多选插入场景下的推荐类型）
  const pickItems: { kind: PeaNodeKind; icon: string; label: string; desc?: string }[] = [
    { kind: 'generate', icon: '⚡', label: 'AI 生成', desc: '图像/视频生成' },
    { kind: 'text', icon: '📝', label: '文本', desc: '文字内容' },
    { kind: 'image', icon: '🖼️', label: '图片', desc: '图片素材' },
    { kind: 'video', icon: '🎬', label: '视频', desc: '视频素材' },
    { kind: 'agent', icon: '🤖', label: '智能体', desc: 'AI 智能体' },
    { kind: 'story', icon: '📖', label: '故事', desc: '叙事脚本' },
  ];

  // 弹窗位置：按钮在选区右侧，故选择器向左展开（朝向节点），避免超出视口
  const menuStyle: React.CSSProperties = {
    position: 'fixed',
    left: Math.max(12, at.left - 300),
    top: Math.min(Math.max(at.top - 60, 12), window.innerHeight - 400),
    zIndex: 60,
  };

  return (
    <>
      {/* 遮罩层 */}
      <div className="fixed inset-0 z-50" onClick={onClose} />

      {/* 选择器面板 */}
      <div
        className="msnp-picker"
        style={menuStyle}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="选择要插入的节点类型"
      >
        {/* 标题区 */}
        <div className="msnp-header">
          <span className="msnp-title">插入节点</span>
          <span className="msnp-subtitle">将连接 {selectedCount} 个选中节点的输出</span>
        </div>

        {/* 连线预览区（有 source 边时才显示） */}
        {sourceEdges.length > 0 && (
          <div className="msnp-edges-preview">
            <div className="msnp-edges-label">将重连的连线 ({sourceEdges.length})</div>
            <div className="msnp-edges-list">
              {sourceEdges.map((se) => (
                <div key={se.edgeId} className="msnp-edge-item">
                  <span className="msnp-edge-src">{se.sourceLabel}</span>
                  <ArrowRightOutlined className="msnp-edge-arrow" />
                  <span className="msnp-edge-tgt">{se.targetLabel}</span>
                  <span className="msnp-edge-badge">→ 新节点</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 节点类型网格 */}
        <div className="msnp-grid">
          {pickItems.map((item) => {
            const hl = hoverKind === item.kind;
            return (
              <button
                key={item.kind}
                className={`msnp-item ${hl ? 'hl' : ''}`}
                onMouseEnter={() => setHoverKind(item.kind)}
                onMouseLeave={() => setHoverKind(null)}
                onClick={() => onPick(item.kind)}
              >
                <span className="msnp-item-icon">{item.icon}</span>
                <span className="msnp-item-info">
                  <span className="msnp-item-label">{item.label}</span>
                  {item.desc && <span className="msnp-item-desc">{item.desc}</span>}
                </span>
              </button>
            );
          })}
        </div>

        {/* 底部提示 */}
        <div className="msnp-footer">
          新节点将插入到选中节点与其下游之间
        </div>
      </div>
    </>
  );
}
