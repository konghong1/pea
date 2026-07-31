import React, { useState, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  DownloadOutlined,
  AppstoreOutlined,
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
}

type GridLayout = 'grid' | 'horizontal';

/** 浮层 header 离 group 框顶部的间距(px)。 */
const HEADER_GAP = 12;
/** 浮层 header 高度(px)，与 .pgn-header-portal 实际渲染一致。 */
const HEADER_HEIGHT = 36;

/**
 * GroupNode — 打组容器节点。
 *
 * 视觉与交互：
 * - 容器本身：透明背景 + 细边框 + padding 0，画布点阵透出（参考图样式）。
 * - 顶部工具栏：createPortal 到 body，固定浮在 group 框**外顶部上方 8px**,
 *   和单节点的 NodeChatPrompt 工具条同款（不再占容器内部空间）。
 * - 子节点：通过 ReactFlow 的 parentNode + extent:'parent' 机制渲染在容器内,
 *   拖动 group 时子节点由 ReactFlow subflow 自动跟随移动。
 */
export default function GroupNode({ id, data, selected }: NodeProps) {
  const { ungroupNode, reLayoutGroup, downloadGroup } = useCanvas();
  const [showLayoutMenu, setShowLayoutMenu] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [headerPos, setHeaderPos] = useState<{ left: number; top: number } | null>(null);

  const grp = data as any;
  const label: string = grp.label || '新建组';
  const layout: GridLayout = grp.layout || 'grid';

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

  // ── 浮层 header 内容（与单节点工具条同款视觉） ──
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
      <div className="pgn-header-left">
        <AppstoreOutlined className="pgn-icon" />
        <span className="pgn-label">{label}</span>
      </div>

      <div className="pgn-header-actions">
        {/* 第一组：选择框背景颜色 + 切换布局 */}
        <button
          className="pgn-btn pgn-color-btn"
          title="切换选择框背景颜色"
          onClick={(e) => {
            e.stopPropagation();
            // TODO: 打开颜色选择器，修改当前组选择框背景色
            console.log('[GroupNode] open color picker for selection box:', id);
          }}
        >
          <svg
            className="pgn-color-icon"
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            aria-hidden
          >
            <path
              d="M2 9.5V11a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V9.5L7 4 2 9.5z"
              fill="currentColor"
            />
            <path d="M2 9.5h10" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </button>

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
                <AppstoreOutlined /> 宫格布局
              </button>
              <button
                className={`pgn-layout-item ${layout === 'horizontal' ? 'active' : ''}`}
                onClick={() => handleLayout('horizontal')}
              >
                <UnorderedListOutlined /> 水平布局
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
      {/* group 容器本体：透明 + 细边框，子节点由 ReactFlow 自动渲染到内部。
          容器本身不渲染任何内容（不留 header 占位），让画布点阵与子节点视觉贯通。 */}
      <div
        className={`pea-group-node ${selected ? 'selected' : ''}`}
        data-group-container={id}
      >
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
