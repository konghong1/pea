import React, { useState, useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  DownloadOutlined,
  UnorderedListOutlined,
  PlayCircleOutlined,
  CopyOutlined,
  GroupOutlined,
} from '@ant-design/icons';
import type { NodeProps } from 'reactflow';
import { useCanvas } from '../store/canvas';

/** 组内布局类型 */
export type GroupLayout = 'grid' | 'horizontal';

/** Group 节点的 data 结构 */
export interface GroupNodeData {
  label: string;
  layout: GridLayout;
  childrenIds: string[];
  bgColor?: string;
}

export type GridLayout = 'grid' | 'horizontal';

/** 浮层 header 离 group 框顶部的间距(px)。 */
const HEADER_GAP = 18;
/** 浮层 header 高度(px)，与 .pgn-header-portal 实际渲染一致。 */
const HEADER_HEIGHT = 36;

/** 可选的组背景色（与图3色板对应）。 */
const COLOR_PRESETS: { color: string; label: string }[] = [
  { color: 'transparent', label: '透明' },
  { color: 'rgba(255,255,255,0.08)', label: '浅白' },
  { color: 'rgba(99,102,241,0.16)', label: '靛' },
  { color: 'rgba(239,68,68,0.16)', label: '红' },
  { color: 'rgba(34,197,94,0.16)', label: '绿' },
  { color: 'rgba(234,179,8,0.16)', label: '黄' },
  { color: 'rgba(168,85,247,0.16)', label: '紫' },
  { color: 'rgba(249,115,22,0.16)', label: '橙' },
];

/** 把背景色转换成更醒目的色环颜色（提高 alpha，让颜色能被看见）。 */
function swatchRingColor(color: string): string {
  if (color === 'transparent') return 'rgba(255,255,255,0.35)';
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (m) {
    const [_, r, g, b, a] = m;
    const alpha = a ? Math.min(parseFloat(a) * 4, 0.9) : 0.9;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return color;
}

/**
 * GroupNode — 打组容器节点。
 *
 * 视觉与交互：
 * - 容器本身：可选半透明背景 + 细边框 + padding 0，画布点阵透出（参考图样式）。
 * - 组名称：显示在容器左上角，无图标（参考图2）。
 * - 顶部工具栏：createPortal 到 body，固定浮在 group 框**外顶部上方**，
 *   仅保留操作按钮，不再显示组名。
 * - 子节点：通过 ReactFlow 的 parentNode + extent:'parent' 机制渲染在容器内,
 *   拖动 group 时子节点由 ReactFlow subflow 自动跟随移动。
 */
export default function GroupNode({ id, data, selected }: NodeProps) {
  const { ungroupNode, reLayoutGroup, downloadGroup, updateNodeData } = useCanvas();
  const [showLayoutMenu, setShowLayoutMenu] = useState(false);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [headerPos, setHeaderPos] = useState<{ left: number; top: number } | null>(null);
  const colorBtnRef = useRef<HTMLButtonElement>(null);

  const grp = data as any;
  const label: string = grp.label || '新建组';
  const layout: GridLayout = grp.layout || 'grid';
  const bgColor: string = grp.bgColor || 'transparent';

  // ── 布局切换 ──
  const handleLayout = useCallback(
    (l: GridLayout) => {
      reLayoutGroup(id, l);
      setShowLayoutMenu(false);
    },
    [id, reLayoutGroup],
  );

  // ── 解组 ──
  const handleUngroup = useCallback(() => {
    ungroupNode(id);
  }, [id, ungroupNode]);

  // ── 下载 ──
  const handleDownload = useCallback(() => {
    downloadGroup(id);
  }, [id, downloadGroup]);

  // ── 背景色切换 ──
  const handleSetBgColor = useCallback(
    (color: string) => {
      updateNodeData(id, { bgColor: color } as Partial<any>, true);
      setShowColorPicker(false);
    },
    [id, updateNodeData],
  );

  // 点击面板外部关闭颜色选择器
  useEffect(() => {
    if (!showColorPicker) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (colorBtnRef.current && colorBtnRef.current.contains(target)) return;
      const panel = document.querySelector('.pgn-color-panel');
      if (panel && panel.contains(target)) return;
      setShowColorPicker(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [showColorPicker]);

  // ── Portal 头部浮层位置：rAF 读 group 节点 DOM rect，跟随 group 移动/缩放 ──
  useEffect(() => {
    if (!selected) {
      setHeaderPos(null);
      return;
    }
    setPortalReady(true);
    const rafRef = { id: 0 };
    const update = () => {
      const el = document.querySelector<HTMLElement>(
        `.react-flow__node[data-id="${id}"]`,
      );
      if (el) {
        const r = el.getBoundingClientRect();
        setHeaderPos({
          left: Math.round(r.left + r.width / 2),
          top: Math.round(r.top - HEADER_HEIGHT - HEADER_GAP),
        });
      }
      rafRef.id = requestAnimationFrame(update);
    };
    rafRef.id = requestAnimationFrame(update);
    return () => {
      cancelAnimationFrame(rafRef.id);
    };
  }, [id, selected]);

  // ── 浮层 header 内容（仅操作按钮，组名已移至框内左上角） ──
  const headerNode = (
    <div
      className="pgn-header-portal"
      style={
        headerPos
          ? { left: headerPos.left, top: headerPos.top }
          : { left: -9999, top: -9999, visibility: 'hidden' }
      }
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      data-group-id={id}
    >
      <div className="pgn-header-actions">
        {/* 第一组：选择框背景颜色 + 切换布局 */}
        <div className="pgn-color-wrap">
          <button
            ref={colorBtnRef}
            className={`pgn-btn pgn-color-btn ${showColorPicker ? 'active' : ''}`}
            title="切换背景"
            onClick={(e) => {
              e.stopPropagation();
              setShowColorPicker((v) => !v);
            }}
          >
            <span
              className="pgn-color-swatch"
              style={{
                '--pgn-swatch-color': swatchRingColor(bgColor),
              } as React.CSSProperties}
            />
            <span>切换背景</span>
          </button>

          {showColorPicker && (
            <div className="pgn-color-panel" onClick={(e) => e.stopPropagation()}>
              {COLOR_PRESETS.map((preset) => (
                <button
                  key={preset.color}
                  className={`pgn-color-option ${bgColor === preset.color ? 'active' : ''}`}
                  title={preset.label}
                  onClick={() => handleSetBgColor(preset.color)}
                >
                  <span
                    className="pgn-color-dot"
                    style={{
                      background:
                        preset.color === 'transparent'
                          ? 'linear-gradient(135deg, rgba(255,255,255,0.25) 45%, transparent 45%, transparent 55%, rgba(255,255,255,0.25) 55%)'
                          : preset.color,
                    }}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 布局切换 */}
        <div className="pgn-layout-wrap">
          <button
            className={`pgn-btn pgn-layout-trigger ${showLayoutMenu ? 'active' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              setShowLayoutMenu((v) => !v);
            }}
            title="切换布局"
          >
            <UnorderedListOutlined />
          </button>

          {showLayoutMenu && (
            <div className="pgn-layout-menu" onClick={(e) => e.stopPropagation()}>
              <button
                className={`pgn-layout-item ${layout === 'grid' ? 'active' : ''}`}
                onClick={() => handleLayout('grid')}
              >
                <span className="pgn-layout-icon pgn-layout-icon-grid" /> 宫格布局
              </button>
              <button
                className={`pgn-layout-item ${layout === 'horizontal' ? 'active' : ''}`}
                onClick={() => handleLayout('horizontal')}
              >
                <span className="pgn-layout-icon pgn-layout-icon-list" /> 水平布局
              </button>
            </div>
          )}
        </div>

        <div className="pgn-actions-sep" />

        {/* 第二组：剩余功能（整组执行 / 创建模板 / 解组） */}
        <button className="pgn-btn" title="整组执行">
          <PlayCircleOutlined />
          <span>整组执行</span>
        </button>

        <button className="pgn-btn" title="创建模板">
          <CopyOutlined />
          <span>创建模板</span>
        </button>

        <button
          className="pgn-btn pgn-ungroup"
          title="解组"
          onClick={(e) => {
            e.stopPropagation();
            handleUngroup();
          }}
        >
          <GroupOutlined />
          <span>解组</span>
        </button>

        <div className="pgn-actions-sep" />

        {/* 第三组：下载 */}
        <button
          className="pgn-btn"
          title="下载组"
          onClick={(e) => {
            e.stopPropagation();
            handleDownload();
          }}
        >
          <DownloadOutlined />
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* group 容器本体：可选半透明背景 + 细边框，子节点由 ReactFlow 自动渲染到内部。 */}
      <div
        className={`pea-group-node ${selected ? 'selected' : ''}`}
        data-group-container={id}
        style={bgColor === 'transparent' ? undefined : { background: bgColor }}
      >
        {/* 组名称：左上角，无图标（参考图2） */}
        <div className="pea-group-node-label">{label}</div>
        {/* 子节点由 ReactFlow 通过 parentNode 机制渲染在此容器内 */}
      </div>

      {/* Portal 浮层 header：createPortal 到 body，浮在 group 框外顶部。
          选中 group 时才显示；不选中立即消失，避免和单节点工具条/多选工具条堆叠。 */}
      {selected && portalReady && typeof document !== 'undefined'
        ? createPortal(headerNode, document.body)
        : null}
    </>
  );
}
