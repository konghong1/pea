// 验证裁切生成节点的连线方向（问题1修复）：裁切结果应作为源节点的【上游输入】(左侧)，
// 串接到「上游 → 源」之间，而非原来的下游输出(右侧)。
import { wireAsUpstream, type WireEdge } from '../pea-server/web/src/lib/cropWire';

let failures = 0;
function check(cond: boolean, msg: string) {
  if (cond) console.log('  PASS  ', msg);
  else { console.error('  FAIL  ', msg); failures++; }
}
function approx(a: number, b: number, eps = 1e-6) { return Math.abs(a - b) <= eps; }

const E = (source: string, target: string): WireEdge => ({
  id: `e_${source}_${target}`,
  source, target, sourceHandle: 'out', targetHandle: 'in', type: 'pea',
});

console.log('— 场景A：源节点无上游 —');
{
  const out = wireAsUpstream([], 'src', 'new');
  check(out.length === 1, '生成 1 条连线');
  check(out[0].source === 'new' && out[0].target === 'src', 'new → src（新节点是源的上游输入）');
  check(out[0].targetHandle === 'in', '连线进入源节点的 in 手柄（左侧输入）');
}

console.log('— 场景B：源节点已有左上游 L —');
{
  const edges = [E('L', 'src')];
  const out = wireAsUpstream(edges, 'src', 'new');
  // 期望：L→new, new→src（L 不再直连 src）
  check(out.some((e) => e.source === 'L' && e.target === 'new'), 'L 改连到新节点（new 串在 L 与 src 之间）');
  check(out.some((e) => e.source === 'new' && e.target === 'src'), '新节点连到源节点');
  check(!out.some((e) => e.source === 'L' && e.target === 'src'), '旧的 L→src 直连已断开');
  check(out.length === 2, '共 2 条连线（无多余/丢失）');
}

console.log('— 场景C：源节点有多个左上游 L1/L2 —');
{
  const edges = [E('L1', 'src'), E('L2', 'src')];
  const out = wireAsUpstream(edges, 'src', 'new');
  check(out.some((e) => e.source === 'L1' && e.target === 'new'), 'L1 → new');
  check(out.some((e) => e.source === 'L2' && e.target === 'new'), 'L2 → new');
  check(out.some((e) => e.source === 'new' && e.target === 'src'), 'new → src');
  check(!out.some((e) => e.target === 'src' && e.source !== 'new'), 'src 的所有上游输入都经过 new');
  check(out.length === 3, '共 3 条连线');
}

console.log('— 场景D：源节点同时有左上游 L 与右下游 R（用户截图场景）—');
{
  const edges = [E('L', 'src'), E('src', 'R')];
  const out = wireAsUpstream(edges, 'src', 'new');
  // 关键：新节点连到【左】节点一侧（L→new→src），右下游 R 保持 src→R 不变。
  check(out.some((e) => e.source === 'L' && e.target === 'new'), 'L → new（连到左节点）✓');
  check(out.some((e) => e.source === 'new' && e.target === 'src'), 'new → src');
  check(out.some((e) => e.source === 'src' && e.target === 'R'), 'src → R 下游保持（右节点未被错误连接）✓');
  check(!out.some((e) => e.source === 'new' && e.target === 'R'), '新节点没有错误地连到右节点 ✗修复前会这样');
  check(out.length === 3, '共 3 条连线');
}

console.log('— 不变量：所有新连线都带 out→in 手柄且 type=pea —');
{
  const out = wireAsUpstream([E('L', 'src')], 'src', 'new');
  check(out.every((e) => e.sourceHandle === 'out' && e.targetHandle === 'in' && e.type === 'pea'),
    '每条边 sourceHandle=out / targetHandle=in / type=pea');
}

console.log(failures === 0 ? '\n✅ ALL PASS' : `\n❌ ${failures} FAILED`);
if (failures > 0) process.exit(1);
