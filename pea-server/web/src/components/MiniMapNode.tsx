import { memo, useEffect, useState } from 'react';
import type { MiniMapNodeProps } from '@reactflow/minimap';
import { useCanvas, type PeaNodeData } from '../store/canvas';
import { kindColor } from './NodeIcon';
import { getFileUrl } from '../api/files';

/** 从节点数据中提取可展示的缩略图 URL（与 PeaNode 优先级一致）。 */
function pickSyncThumb(data?: PeaNodeData): string {
  if (!data) return '';
  const index = Math.max(0, Math.min(data.resultIndex ?? 0, (data.resultUrls?.length ?? 1) - 1));
  return data.resultUrl || data.resultUrls?.[index] || data.url || '';
}

const kindName: Record<string, string> = {
  text: '文本',
  image: '图片',
  video: '视频',
  audio: '音频',
  ref: '引用',
  generate: '生成',
  agent: '智能体',
  story: '故事',
  world3d: '3D 世界',
  camera: '相机',
  light: '灯光',
  playlist: '播放列表',
  replace: '替换',
  prompt: '提示词',
};

/**
 * 自定义 ReactFlow MiniMap 节点：
 * - 媒体节点直接渲染缩略图（与主画布节点一致的图片预览），无图片时按 kind 着色
 * - 节点尺寸足够大时在矩形下方显示 label，便于在缩略图中识别节点
 * - 始终提供原生 SVG <title> 提示（label + kind 中文名）
 * - 关键修复：必须把 MiniMap 传入的 onClick 转发到节点元素，否则点击不会触发跳转
 */
function MiniMapNodeInner(props: MiniMapNodeProps) {
  const { id, x, y, width, height, borderRadius, color: baseColor, strokeColor, strokeWidth, shapeRendering, onClick } = props;

  const node = useCanvas((s) => s.nodes.find((n) => n.id === id));
  const data = node?.data;
  const kind = data?.kind ?? 'prompt';
  const label = data?.label || data?.kind || id;
  const fill = baseColor || kindColor(kind);

  // 同步可见的缩略图（resultUrl / resultUrls[index] / url）
  const syncThumb = pickSyncThumb(data);
  // 仅当没有同步 URL、但有 fileKey 时，异步解析私有资源 URL
  const needsResolve = !syncThumb && !!data?.fileKey;
  const [resolvedThumb, setResolvedThumb] = useState('');
  useEffect(() => {
    let alive = true;
    if (needsResolve && data?.fileKey) {
      getFileUrl(data.fileKey)
        .then((u) => { if (alive) setResolvedThumb(u); })
        .catch(() => { if (alive) setResolvedThumb(''); });
    } else {
      setResolvedThumb('');
    }
    return () => { alive = false; };
  }, [needsResolve, data?.fileKey]);

  const thumbUrl = syncThumb || resolvedThumb;

  // 节点在缩略图中太小时不显示文字，避免堆叠成一片色块
  const showLabel = width > 38 && height > 22;
  const fontSize = Math.max(6, Math.min(11, Math.min(width, height) / 5));
  const maxChars = Math.max(3, Math.floor(width / (fontSize * 0.62)));
  const displayLabel = label.length > maxChars ? `${label.slice(0, maxChars)}…` : label;

  const clipId = `pea-mm-clip-${id}`;

  return (
    <g
      className="pea-minimap-node"
      data-id={id}
      data-kind={kind}
      onClick={onClick ? (e) => onClick(e, id) : undefined}
      style={{ cursor: 'pointer' }}
    >
      {/* 缩略图：有图时填充，无图时回退到按 kind 着色的圆角矩形 */}
      {thumbUrl ? (
        <>
          <clipPath id={clipId}>
            <rect x={x} y={y} width={width} height={height} rx={borderRadius} ry={borderRadius} />
          </clipPath>
          <image
            href={thumbUrl}
            x={x}
            y={y}
            width={width}
            height={height}
            preserveAspectRatio="xMidYMid slice"
            clipPath={`url(#${clipId})`}
            style={{ pointerEvents: 'none' }}
          />
          {/* 描边层同时作为点击命中层：transparent 填充可捕获节点内部点击，事件冒泡到 <g> onClick */}
          <rect
            x={x}
            y={y}
            width={width}
            height={height}
            rx={borderRadius}
            ry={borderRadius}
            fill="transparent"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            shapeRendering={shapeRendering}
            style={{ pointerEvents: 'all' }}
          />
        </>
      ) : (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          rx={borderRadius}
          ry={borderRadius}
          fill={fill}
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          shapeRendering={shapeRendering}
          style={{ pointerEvents: 'all' }}
        />
      )}

      <title>{`${label} · ${kindName[kind] ?? kind}`}</title>
      {showLabel && (
        <text
          x={x + width / 2}
          y={y + height + fontSize + 2}
          textAnchor="middle"
          className="pea-minimap-node-label"
          style={{ fontSize, pointerEvents: 'none' }}
        >
          {displayLabel}
        </text>
      )}
    </g>
  );
}

export default memo(MiniMapNodeInner);
