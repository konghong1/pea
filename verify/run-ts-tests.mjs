#!/usr/bin/env node
/**
 * verify/*.test.ts 统一 runner。
 *
 * 项目里的前端单测是「零依赖手写断言 + 直接 import 生产源码」的风格
 * （见 crop_math.test.ts / crop_export.test.ts），不引入 vitest/jest，
 * 保持 web 端依赖树干净。本 runner 负责把它们编译并逐个执行。
 *
 * 复用 pea-server/web 已有的 esbuild（vite 的传递依赖），不新增任何依赖。
 * 编译产物写入 .workbuddy/artifacts/ts-test-build/（已被 .gitignore 忽略），
 * 不污染仓库。
 *
 * 用法：
 *   node verify/run-ts-tests.mjs              # 跑全部 verify/*.test.ts
 *   node verify/run-ts-tests.mjs crop_export  # 只跑名字匹配的
 *
 * 退出码：任一测试文件失败 → 1（可直接用于 CI 门禁）。
 */
import { readdirSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, join, basename } from 'node:path';
import { spawnSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..');
const WEB_PKG = resolve(REPO_ROOT, 'pea-server/web/package.json');
const OUT_DIR = resolve(REPO_ROOT, '.workbuddy/artifacts/ts-test-build');

// ── 定位 esbuild（web 的 devDependency，随 vite 一起装）────────────────────
let esbuild;
try {
  const requireFromWeb = createRequire(WEB_PKG);
  esbuild = requireFromWeb('esbuild');
} catch {
  console.error('✗ 找不到 esbuild。请先安装 web 依赖：');
  console.error('    cd pea-server/web && npm install');
  process.exit(1);
}

// ── 收集测试文件 ────────────────────────────────────────────────────────────
const filter = process.argv[2];
const testFiles = readdirSync(__dirname)
  .filter((f) => f.endsWith('.test.ts'))
  .filter((f) => (filter ? f.includes(filter) : true))
  .sort()
  .map((f) => join(__dirname, f));

if (testFiles.length === 0) {
  console.error(filter ? `✗ 没有匹配 "${filter}" 的测试文件` : '✗ verify/ 下没有 *.test.ts');
  process.exit(1);
}

// ── 编译 + 执行 ─────────────────────────────────────────────────────────────
// 幂等覆盖写入：不做删除操作（部分环境会拦截 rm，且删除对 runner 无必要）。
// 每次 build 都会覆盖同名 outfile，产物目录已被 .gitignore 忽略。
mkdirSync(OUT_DIR, { recursive: true });

console.log(`\n运行 ${testFiles.length} 个前端单测文件\n${'═'.repeat(60)}`);

const failed = [];
for (const file of testFiles) {
  const name = basename(file, '.test.ts');
  const outfile = join(OUT_DIR, `${name}.mjs`);
  console.log(`\n▶ ${basename(file)}`);

  try {
    esbuild.buildSync({
      entryPoints: [file],
      bundle: true,
      platform: 'node',
      format: 'esm',
      target: 'node18',
      outfile,
      logLevel: 'error',
    });
  } catch (err) {
    console.error(`  编译失败: ${err?.message ?? err}`);
    failed.push(name);
    continue;
  }

  const run = spawnSync(process.execPath, [outfile], { stdio: 'inherit' });
  if (run.status !== 0) failed.push(name);
}

// ── 汇总 ────────────────────────────────────────────────────────────────────
console.log(`\n${'═'.repeat(60)}`);
if (failed.length === 0) {
  console.log(`✅ 全部通过（${testFiles.length} 个文件）`);
  process.exit(0);
} else {
  console.error(`❌ ${failed.length} 个文件失败: ${failed.join(', ')}`);
  console.error(`   编译产物在 ${OUT_DIR} 供排查`);
  process.exit(1);
}
