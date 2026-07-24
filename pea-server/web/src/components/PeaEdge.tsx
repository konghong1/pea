import { BaseEdge, EdgeLabelRenderer, getBezierPath, EdgeProps } from 'reactflow';
import { useCanvas } from '../store/canvas';

/**
 * 自定义边：选中时在连线中点显示一个删除按钮（×），
 * 让“删除连线”可见、可点，不再依赖键盘 Delete（用户反馈线删不掉）。
 */
export default function PeaEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  selected,
}: EdgeProps) {
  const removeEdge = useCanvas((s) => s.removeEdge);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      {selected && (
        <EdgeLabelRenderer>
          <button
            type="button"
            className="pea-edge-del"
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            onClick={(e) => {
              e.stopPropagation();
              removeEdge(id);
            }}
            onMouseDown={(e) => e.stopPropagation()}
            title="删除连线"
            aria-label="删除连线"
          >
            ×
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
