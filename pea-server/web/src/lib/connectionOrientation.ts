/**
 * 连线方向归一化（单一事实来源 / Single Source of Truth）
 * ============================================================================
 * 背景：画布使用 ConnectionMode.Loose，节点有「左侧 target 手柄(id='in')」与
 * 「右侧 source 手柄(id='out')」。从某个手柄起拉、落在另一节点上时，ReactFlow 在
 * onConnect 里返回的 conn.source/conn.target 会按「起拉手柄类型 + 落点附近最近手柄 +
 * 几何位置」推断方向，导致：起拉节点在目标节点右侧（自然从左侧 'in' 手柄向左拖拽）时，
 * 连线被几何反转（变成 落点→起拉(in)），与用户「连到另一个节点的输入」本意相反。
 *
 * 用户需求（来自报障）：
 *   "从一个节点去拉取连线，本意是要连接到另一个节点的输入节点……只要从输入节点拉出的线
 *    连接的其他节点时，这个点就要连接到输入节点，就算连线时碰到的输出节点。"
 * 即：拖拽连线的方向【只】由「起拉节点 = source、落点节点 = target('in')」决定，
 * 与几何位置、起拉的是 in 还是 out 手柄、落点是否碰到了输出节点【完全无关】。
 *
 * 因此本函数对「拖拽连线」采用统一规则：
 *   - source = 起拉节点(pending.source)，target = 落点节点(dropNodeId)；
 *   - targetHandle 恒为 'in'（所有入边固定落在目标节点左侧输入手柄）；
 *   - sourceHandle 用起拉手柄（从 'in' 起拉即从 'in' 出线，从 'out' 起拉即从 'out' 出线）。
 *
 * 说明：单击连接点→新建并连接(addConnectedAt)是另一套交互（点 'in' = 新建节点喂我），
 * 不在本规则内，保持其原有 handleType 分支逻辑，避免回归。
 */
import type { Connection } from 'reactflow';

export type HandleType = 'source' | 'target' | null;

export interface PendingEdge {
  /** 起拉节点 id（字段名沿用历史 pendingEdge.current.source；可能为 null，调用方需先校验） */
  source: string | null;
  /** 起拉手柄 id（'out' / 'in' / null） */
  handleId: string | null;
  /** 起拉手柄类型：'source'=输出手柄，'target'=输入手柄 */
  handleType: HandleType;
}

/**
 * 把一次「从 pending 起拉、落在 dropNodeId」的拖拽归一化成一条确定方向的边。
 *
 * 方向规则（拖拽连线）：起拉节点恒为 source，落点节点恒为 target，与几何/手柄类型无关。
 * 这彻底消除「起拉节点在右就永远连反」的 bug。
 *
 * @param pending     起拉信息（节点 id / 起拉手柄 id / 起拉手柄类型）
 * @param dropNodeId  鼠标释放时所在（或最近）的节点 id
 * @returns           可直接交给 store.onConnect 的 Connection（targetHandle 恒为 'in'）
 */
export function resolveConnection(pending: PendingEdge, dropNodeId: string): Connection {
  // 调用方（onConnect / onConnectEnd）已用 `if (!pending?.source) return;` 保证 source 非空；
  // 此处兜底用 '' 仅为通过类型检查，正常使用不会触发。
  const source = pending.source ?? '';
  return {
    source,
    target: dropNodeId,
    sourceHandle: pending.handleId ?? null,
    targetHandle: 'in',
  } as Connection;
}
