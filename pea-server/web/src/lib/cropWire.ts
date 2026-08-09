// cropWire.ts — 裁切生成节点的连线接线（纯函数，可单测，不依赖 reactflow 运行时）
//
// 设计：裁切结果是被裁切节点(input 源)的【上游预处理】，应作为它的输入插入：
//   - 源节点无上游：newNode → source（newNode 在源左侧，作为新输入）
//   - 源节点有上游（左节点）：把 newNode 串到「上游 → 源」之间 → 上游 → newNode → 源
// 这样无论是否已存在左节点，裁切生成节点都连接在【左/输入】侧，而非下游输出侧。
//
// 使用 WireEdge 结构（只取 reactflow Edge 的接线相关字段），避免在本模块引入 reactflow
// 运行时依赖，便于 node 直接单测。

export interface WireEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  type?: string;
}

let __seq = 0;
function __newId(): string {
  __seq += 1;
  return `cw_${Date.now().toString(36)}_${__seq}`;
}

function __addEdgeSafe(edges: WireEdge[], e: Omit<WireEdge, 'id'>): WireEdge[] {
  const exists = edges.some(
    (x) =>
      x.source === e.source &&
      x.target === e.target &&
      (x.sourceHandle ?? null) === (e.sourceHandle ?? null) &&
      (x.targetHandle ?? null) === (e.targetHandle ?? null),
  );
  if (exists) return edges;
  return [...edges, { id: __newId(), ...e }];
}

/**
 * 把 newNodeId 作为 targetId 的上游输入串接进连线图。
 * @returns 新的连线数组（不修改入参）
 */
export function wireAsUpstream(edges: WireEdge[], targetId: string, newNodeId: string): WireEdge[] {
  const incoming = edges.filter((e) => e.target === targetId);

  if (incoming.length === 0) {
    // 源节点无上游：新节点直接作为源节点的新输入
    return __addEdgeSafe(edges, {
      source: newNodeId,
      target: targetId,
      sourceHandle: 'out',
      targetHandle: 'in',
      type: 'pea',
    });
  }

  // 源节点已有上游（左节点）：断开 上游→源，改为 上游→newNode→源
  const sources = [...new Set(incoming.map((e) => e.source))];
  const oldIds = new Set(incoming.map((e) => e.id));
  let next = edges.filter((e) => !oldIds.has(e.id));

  sources.forEach((src) => {
    next = __addEdgeSafe(next, {
      source: src,
      target: newNodeId,
      sourceHandle: 'out',
      targetHandle: 'in',
      type: 'pea',
    });
  });
  next = __addEdgeSafe(next, {
    source: newNodeId,
    target: targetId,
    sourceHandle: 'out',
    targetHandle: 'in',
    type: 'pea',
  });
  return next;
}
