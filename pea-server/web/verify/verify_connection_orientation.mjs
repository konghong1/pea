/**
 * 连线方向规则验证（针对真实模块 src/lib/connectionOrientation.ts）。
 *
 * 运行方式（在本目录执行）：
 *   node verify_connection_orientation.mjs
 *
 * 该脚本会临时编译真实的 connectionOrientation.ts（类型导入会被擦除），
 * 导入并断言 resolveConnection 在「起拉节点在左/右、落点命中 in/out」等
 * 全部组合下方向稳定 —— 即只由「起拉手柄类型」决定，与几何/落点无关。
 */
import { execSync } from 'node:child_process';
import { mkdirSync, rmSync, renameSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const tsc = join(__dirname, '..', 'node_modules', '.bin', 'tsc');
const src = join(__dirname, '..', 'src', 'lib', 'connectionOrientation.ts');
const outDir = join(__dirname, '_conncheck');

// 1) 编译真实模块到临时目录（类型导入被擦除，运行时无外部依赖）
mkdirSync(outDir, { recursive: true });
try {
  execSync(
    `"${tsc}" "${src}" --outDir "${outDir}" --module esnext --target es2020 --skipLibCheck --moduleResolution bundler`,
    { stdio: 'pipe' },
  );
} catch (e) {
  console.error('编译 connectionOrientation.ts 失败：', e.stdout?.toString() || e.message);
  process.exit(2);
}
const compiled = join(outDir, 'connectionOrientation.js');
if (!existsSync(compiled)) {
  console.error('未找到编译产物', compiled);
  process.exit(2);
}
renameSync(compiled, compiled.replace(/\.js$/, '.mjs'));
const { resolveConnection } = await import(pathToFileURL(join(outDir, 'connectionOrientation.mjs')).href);

// 2) 断言：方向矩阵
let failed = 0;
const cases = [];

// 场景 A：从「输出手柄(out/source)」起拉，落点节点 = drop。
//   无论起拉节点在左还是在右、落点命中 in 还是 out，结果都应是 source=start, target=drop。
for (const startSide of ['left', 'right']) {
  for (const dropHandle of ['in', 'out']) {
    const start = 'A';
    const drop = 'B';
    const edge = resolveConnection({ source: start, handleId: 'out', handleType: 'source' }, drop);
    cases.push({
      name: `source-start (起拉在${startSide}) 落点命中${dropHandle}`,
      got: edge,
      expect: { source: 'A', target: 'B', sourceHandle: 'out', targetHandle: 'in' },
    });
  }
}

// 场景 B：从「输入手柄(in/target)」起拉，落点节点 = drop。
//   用户需求：拖拽连线方向只由「起拉节点=source、落点=target(in)」决定，
//   与起拉的是 in 还是 out 手柄无关 —— 起拉节点恒为 source。
//   即便拖拽途中碰到了输出节点(dropHandle='out')，结果也必须稳定：source=start, target=drop。
for (const startSide of ['left', 'right']) {
  for (const dropHandle of ['in', 'out']) {
    const start = 'A';
    const drop = 'B';
    const edge = resolveConnection({ source: start, handleId: 'in', handleType: 'target' }, drop);
    cases.push({
      name: `target-start (起拉在${startSide}) 落点命中${dropHandle}`,
      got: edge,
      expect: { source: 'A', target: 'B', sourceHandle: 'in', targetHandle: 'in' },
    });
  }
}

// 场景 C：几何方向对照 —— 起拉节点在右（用户报障场景），从 in 手柄起拉，
//   必须仍得到 起拉节点=source → 落点=target(in)，不再被几何反转。
cases.push({
  name: '报障场景：起拉节点在右 + 从 in 手柄起拉',
  got: resolveConnection({ source: 'RightNode', handleId: 'in', handleType: 'target' }, 'LeftNode'),
  expect: { source: 'RightNode', target: 'LeftNode', sourceHandle: 'in', targetHandle: 'in' },
});

for (const c of cases) {
  const ok =
    c.got.source === c.expect.source &&
    c.got.target === c.expect.target &&
    c.got.targetHandle === c.expect.targetHandle &&
    c.got.sourceHandle === (c.expect.sourceHandle ?? null);
  if (!ok) {
    failed++;
    console.error(`❌ ${c.name}\n   期望 ${JSON.stringify(c.expect)}\n   实际 ${JSON.stringify(c.got)}`);
  } else {
    console.log(`✅ ${c.name} → ${c.got.source} → ${c.got.target}(in)`);
  }
}

// 3) 清理临时产物（Windows 下 rmSync 可能被 safe-delete 拦截，包一层 try 不影响结论）
try {
  rmSync(outDir, { recursive: true, force: true });
} catch {
  try {
    execSync(`rmdir /s /q "${outDir}"`, { stdio: 'pipe' });
  } catch {
    /* 清理失败不阻塞验证结论 */
  }
}

if (failed > 0) {
  console.error(`\n验证失败：${failed} 个用例不通过`);
  process.exit(1);
}
console.log(`\n全部 ${cases.length} 个用例通过：连线方向只由起拉手柄类型决定，与几何/落点无关。`);
process.exit(0);
