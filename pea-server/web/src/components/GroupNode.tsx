import React, { useState, useCallback, useMemo } from 'react';
import {
  DeleteOutlined,
  DownloadOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  PlayCircleOutlined,
  CopyOutlined,
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

/**
 * GroupNode — 打组容器节点。
 *
 * 渲染为深色圆角容器，顶部工具栏含：
 *   - 整组执行 / 创建模板 / 布局切换(宫格|水平) / 解组 / 下载
 *
 * 子节点通过 ReactFlow 的 parentNode + extent:'parent' 机制
 * 自动成为本节点的子级，拖动组时子节点跟随移动。
 */
export default function GroupNode({ id, data, selected }: NodeProps) {
  const { ungroupNode, reLayoutGroup, downloadGroup, removeNode } =
    useCanvas();
  const [showLayoutMenu, setShowLayoutMenu] = useState(false);

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

  return (
    <div className={`pea-group-node ${selected ? 'selected' : ''}`}>
      {/* ====== 顶部工具栏 ====== */}
      <div className="pgn-header">
        <div className="pgn-header-left">
          <span className="pgn-dot" />
          <AppstoreOutlined className="pgn-icon" />
          <span className="pgn-label">{label}</span>
        </div>

        <div className="pgn-header-actions">
          {/* 整组执行 */}
          <button className="pgn-btn" title="整组执行">
            <PlayCircleOutlined />
            <span>整组执行</span>
          </button>

          {/* 创建模板 */}
          <button className="pgn-btn" title="创建模板">
            <CopyOutlined />
            <span>创建模板</span>
          </button>

          {/* 布局切换 / 解组 */}
          <div className="pgn-layout-wrap">
            <button
              className={`pgn-btn pgn-layout-trigger ${showLayoutMenu ? 'active' : ''}`}
              onClick={() => setShowLayoutMenu((v) => !v)}
              title="布局 / 解组"
            >
              <UnorderedListOutlined />
            </button>

            {showLayoutMenu && (
              <div className="pgn-layout-menu">
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
                <div className="pgn-layout-sep" />
                <button className="pgn-layout-item pgn-danger" onClick={handleUngroup}>
                  <DeleteOutlined /> 解组
                </button>
              </div>
            )}
          </div>

          {/* 下载 */}
          <button className="pgn-btn" title="下载组" onClick={handleDownload}>
            <DownloadOutlined />
          </button>
        </div>
      </div>

      {/* 子节点由 ReactFlow 通过 parentNode 渲染在此容器内 */}
    </div>
  );
}
