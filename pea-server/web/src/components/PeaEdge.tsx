import { BaseEdge, EdgeLabelRenderer, getBezierPath, EdgeProps } from 'reactflow';
import { useCanvas } from '../store/canvas';
import { HANDLE_GAP, HANDLE_HALF } from './PeaNode';

/**
 * 自定义边：选中时在连线中点显示一个删除按钮（×），
 * 让“删除连线”可见、可点，不再依赖键盘 Delete（用户反馈线删不掉）。
 *
 * 关键：连线要连到「节点框」，而不是悬浮在框外的连接点圆点。
 * 连接点圆点距框 HANDLE_GAP（屏幕 px），这里把边的两端点朝对应节点框方向
 * 回退 HANDLE_GAP，使线落在框边；连接点圆点仍浮在框外并保持“弹开”跟随，
 * 两者解耦——线固定连框、点独立浮动。
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
  // ReactFlow 的边端点取手柄"外缘"（远离节点框的一侧）。
  // 该 sourceX/targetX 在边创建时由 ReactFlow 根据当前 zoom 下手柄的 DOM 位置计算，
  // 之后即使 zoom 变化也不会更新（ReactFlow 只在节点移动/边创建时重算）。
  // 手柄外缘距节点框 = HANDLE_GAP + HANDLE_HALF（flow/屏幕坐标在 zoom=1 下 1:1，
  // 且 ReactFlow 记录的端点偏移就是该 creation-time 值），因此用恒定回退量。
  const gap = HANDLE_GAP + HANDLE_HALF;

  // 源点：从悬浮连接点回退到节点框边缘
  let sX = sourceX;
  let sY = sourceY;
  if (sourcePosition === 'right') sX -= gap; // 源在右 → 框在左
  else if (sourcePosition === 'left') sX += gap; // 源在左 → 框在右
  else if (sourcePosition === 'top') sY += gap;
  else if (sourcePosition === 'bottom') sY -= gap;

  // 目标点：同理回退到目标节点框边缘
  let tX = targetX;
  let tY = targetY;
  if (targetPosition === 'left') tX += gap; // 目标在左 → 框在右
  else if (targetPosition === 'right') tX -= gap; // 目标在右 → 框在左
  else if (targetPosition === 'top') tY += gap;
  else if (targetPosition === 'bottom') tY -= gap;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: sX,
    sourceY: sY,
    sourcePosition,
    targetX: tX,
    targetY: tY,
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
