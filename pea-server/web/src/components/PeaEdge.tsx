import { useEffect, useMemo, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { EdgeLabelRenderer, getBezierPath, EdgeProps, useReactFlow } from 'reactflow';
import { useCanvas } from '../store/canvas';
import { HANDLE_GAP, HANDLE_HALF } from './PeaNode';

/**
 * PeaEdge — 科技感分层连线
 * ═══════════════════════════════════════════════════════════════════════════
 * 设计目标（用户诉求）：
 *  1. 空闲连线不抢视线 —— 低对比 + 微模糊，"融进"背景（亮/暗主题各自取值）。
 *  2. 选中连线 / 选中节点 / 拖动节点 时，相关连线高亮并出现「按连接方向流动」的感觉。
 *  3. 删除按钮换成科技感 HUD 芯片（见 .pea-edge-del 一族样式），且**出现在鼠标点击处**。
 *
 * 分层结构（由下到上，全部共用同一条贝塞尔 d）：
 *   ① .pea-edge-halo   —— 宽而柔的辉光垫底，仅 active 时出现（blur 由 CSS filter 给）
 *   ② .pea-edge-line   —— 主线，空闲低透明 + 轻微 blur；active 时提亮加粗
 *   ③ .pea-edge-flow   —— 方向渐变虚线，CSS 动画 stroke-dashoffset 负向位移
 *                          → 视觉上从 source 流向 target
 *   ④ .pea-edge-beads  —— 流动光珠**串**：极短 round dash 在画布坐标系下按固定周期
 *                          铺满整条路径（不做 pathLength 归一化），因此
 *                          「珠子数量 ∝ 连线长度、间距/速度恒定」，长线自然更多珠。
 *                          动画只位移一个 dash 周期即无缝循环。相比 SMIL
 *                          animateMotion，CSS dashoffset 在拖动节点、d 每帧变化时
 *                          **不会重置动画时间线**，因此不闪烁。
 *   ⑤ .react-flow__edge-interaction —— 22px 透明命中区，保证细线也点得中
 *
 * 性能：
 *  - 仅 active 边渲染 ①③④，空闲边只有 ②⑤ 两条 path；
 *  - active 判定用 zustand 选择器返回**布尔基元**，值不变不触发重渲染；
 *  - 动画全部走 CSS（合成层友好），无 JS 逐帧。
 */

/** 复用的离屏测量用 path（不入 DOM）—— getTotalLength/getPointAtLength 在游离节点上同样可用。 */
let measurePath: SVGPathElement | null = null;
function getMeasurePath(d: string): SVGPathElement | null {
  try {
    if (!measurePath) {
      measurePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    }
    measurePath.setAttribute('d', d);
    return measurePath;
  } catch {
    return null;
  }
}

/** 取路径上比例 t(0~1) 处的坐标（画布坐标系）。 */
function pointAtFraction(d: string, t: number): { x: number; y: number } | null {
  const p = getMeasurePath(d);
  if (!p) return null;
  try {
    const total = p.getTotalLength();
    if (!total || !isFinite(total)) return null;
    const pt = p.getPointAtLength(total * Math.min(1, Math.max(0, t)));
    return { x: pt.x, y: pt.y };
  } catch {
    return null;
  }
}

/**
 * 求点 (x,y) 在路径上的最近点比例 t —— 先粗采样再二分细化。
 * 用「比例」而不是「绝对坐标」记录点击位置，节点被拖动导致 d 变化时，
 * 删除芯片仍吸附在线上同一相对位置，不会脱线。
 */
function fractionAtPoint(d: string, x: number, y: number): number | null {
  const p = getMeasurePath(d);
  if (!p) return null;
  try {
    const total = p.getTotalLength();
    if (!total || !isFinite(total)) return null;
    const dist2 = (len: number) => {
      const pt = p.getPointAtLength(len);
      return (pt.x - x) * (pt.x - x) + (pt.y - y) * (pt.y - y);
    };
    const N = 48;
    let best = 0;
    let bestD = Infinity;
    for (let i = 0; i <= N; i++) {
      const len = (total * i) / N;
      const dd = dist2(len);
      if (dd < bestD) {
        bestD = dd;
        best = len;
      }
    }
    let step = total / N;
    for (let iter = 0; iter < 8; iter++) {
      step /= 2;
      for (const cand of [best - step, best + step]) {
        if (cand < 0 || cand > total) continue;
        const dd = dist2(cand);
        if (dd < bestD) {
          bestD = dd;
          best = cand;
        }
      }
    }
    return best / total;
  } catch {
    return null;
  }
}

export default function PeaEdge({
  id,
  source,
  target,
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
  const { screenToFlowPosition } = useReactFlow();

  // 点击落点在路径上的比例（0~1）。null = 未记录 → 退回连线中点。
  const [clickT, setClickT] = useState<number | null>(null);
  // 取消选中后清空，下次若由键盘/程序选中则回到中点，不残留上次的落点。
  useEffect(() => {
    if (!selected) setClickT(null);
  }, [selected]);

  // ── active：本边被选中，或它连接的任一端点节点被选中 / 正在被拖动 ──────────
  // 返回布尔基元 → zustand 浅比较，拖动过程中值不翻转就不会重渲染。
  const endpointActive = useCanvas((s) => {
    if (s.selectedIds.includes(source) || s.selectedIds.includes(target)) return true;
    const ns = s.nodes as any[];
    for (let i = 0; i < ns.length; i++) {
      const n = ns[i];
      if (n.dragging && (n.id === source || n.id === target)) return true;
    }
    return false;
  });
  const active = !!selected || endpointActive;

  // ReactFlow 的边端点取手柄"外缘"（远离节点框的一侧）。
  // 该 sourceX/targetX 在边创建时由 ReactFlow 根据当前 zoom 下手柄的 DOM 位置计算，
  // 之后即使 zoom 变化也不会更新（ReactFlow 只在节点移动/边创建时重算）。
  // 手柄外缘距节点框 = HANDLE_GAP + HANDLE_HALF（flow/屏幕坐标在 zoom=1 下 1:1，
  // 且 ReactFlow 记录的端点偏移就是该 creation-time 值），因此用恒定回退量。
  // ⚠️ 绝不除以 zoom、绝不读 useStore —— 见项目记忆「连线端点恒定回退」。
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

  // 方向渐变：起点淡、终点亮 —— 即便动画被 reduced-motion 关掉，
  // 明暗梯度本身也在传达"从哪流向哪"。
  const gradId = useMemo(() => `pea-edge-grad-${String(id).replace(/[^\w-]/g, '_')}`, [id]);

  // 删除芯片锚点：优先用「点击落点比例」换算出的路径坐标（跟随节点移动），
  // 拿不到时（程序/键盘选中）退回连线中点。每次渲染同步计算，永远与当前 d 一致。
  const chipPt = (clickT != null ? pointAtFraction(edgePath, clickT) : null) ?? {
    x: labelX,
    y: labelY,
  };

  // 记录点击落点 —— 注意**不要 stopPropagation**，否则 ReactFlow 收不到点击、边不会被选中。
  const recordClick = (e: ReactMouseEvent<SVGPathElement>) => {
    try {
      const flow = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const t = fractionAtPoint(edgePath, flow.x, flow.y);
      if (t != null) setClickT(t);
    } catch {
      /* 定位失败就退回中点，不影响选中 */
    }
  };

  return (
    <>
      {active && (
        <defs>
          <linearGradient
            id={gradId}
            gradientUnits="userSpaceOnUse"
            x1={sX}
            y1={sY}
            x2={tX}
            y2={tY}
          >
            <stop className="pea-edge-grad-from" offset="0%" />
            <stop className="pea-edge-grad-mid" offset="55%" />
            <stop className="pea-edge-grad-to" offset="100%" />
          </linearGradient>
        </defs>
      )}

      {/* ① 辉光垫底 */}
      {active && <path className="pea-edge-halo" d={edgePath} fill="none" />}

      {/* ② 主线（保留 react-flow__edge-path 类名以兼容 RF 内部样式/查询） */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        markerEnd={markerEnd}
        style={style}
        data-edge-id={id}
        data-active={active ? '1' : '0'}
        className={`react-flow__edge-path pea-edge-line${active ? ' is-active' : ''}${
          selected ? ' is-selected' : ''
        }`}
      />

      {/* ③ 方向流动虚线 */}
      {active && (
        <path
          className="pea-edge-flow"
          d={edgePath}
          fill="none"
          stroke={`url(#${gradId})`}
        />
      )}

      {/* ④ 流动光珠串（画布坐标系固定周期铺满，长线自然更多珠；d 变化不重置动画） */}
      {active && <path className="pea-edge-beads" d={edgePath} fill="none" />}

      {/* ⑤ 命中区：细线也要好点；同时负责记录点击落点给删除芯片定位 */}
      <path
        className="react-flow__edge-interaction"
        d={edgePath}
        fill="none"
        strokeOpacity={0}
        strokeWidth={22}
        onPointerDown={recordClick}
      />

      {selected && (
        <EdgeLabelRenderer>
          {/* 定位锚：只负责「定位 + counter-scale」，内联 transform 会压过样式表，
              所以 hover 的缩放/位移必须放在内层 button 上，否则会被内联样式吃掉。 */}
          <div
            className="pea-edge-del-anchor"
            data-chip-anchored={clickT != null ? '1' : '0'}
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${chipPt.x}px, ${chipPt.y}px) scale(var(--pea-inv-zoom, 1))`,
              pointerEvents: 'all',
            }}
          >
          <button
            type="button"
            className="pea-edge-del"
            onClick={(e) => {
              e.stopPropagation();
              removeEdge(id);
            }}
            onMouseDown={(e) => e.stopPropagation()}
            title="断开连接"
            aria-label="断开连接"
          >
            <svg viewBox="0 0 30 30" width="30" height="30" aria-hidden focusable="false">
              {/* 外圈扫描环：虚线圆环缓慢自转，HUD 感的来源 */}
              <circle className="pea-edge-del-ring" cx="15" cy="15" r="13.2" />
              {/* 六边形玻璃核心 */}
              <path
                className="pea-edge-del-hex"
                d="M15 3.6 L24.9 9.3 L24.9 20.7 L15 26.4 L5.1 20.7 L5.1 9.3 Z"
              />
              {/* 顶/底 HUD 装饰刻线 */}
              <path className="pea-edge-del-tick" d="M15 3.6 L15 6.2 M15 23.8 L15 26.4" />
              {/* 断开符号 × */}
              <path className="pea-edge-del-x" d="M11.4 11.4 L18.6 18.6 M18.6 11.4 L11.4 18.6" />
            </svg>
          </button>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
