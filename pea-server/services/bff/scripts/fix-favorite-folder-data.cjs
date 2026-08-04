/**
 * 数据修复脚本：清理「收藏素材仍挂在 folder_id 下」的历史脏数据。
 *
 * 业务规则：收藏素材只应在「收藏」入口出现，不应再属于任何文件夹。
 * 之前的 bug 导致收藏时未把 folder_id 置空，因此需要一次性修复。
 *
 * 用法：
 *   node scripts/fix-favorite-folder-data.cjs           # 只预览影响行数
 *   node scripts/fix-favorite-folder-data.cjs --apply   # 执行修复
 */
const fs = require('fs');
const path = require('path');
const mysql = require('mysql2/promise');

const ENV_PATH = path.resolve(__dirname, '../.env');

function loadEnv(filePath) {
  if (!fs.existsSync(filePath)) return;
  const content = fs.readFileSync(filePath, 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (!(key in process.env)) process.env[key] = value;
  }
}

loadEnv(ENV_PATH);

const host = process.env.PEA_DB_HOST ?? 'mysql';
const port = parseInt(process.env.PEA_DB_PORT ?? '3306', 10);
const user = process.env.PEA_DB_USER ?? 'pea';
const password = process.env.PEA_DB_PASSWORD ?? 'pea_dev';
const database = process.env.PEA_DB_NAME ?? 'pea';

const APPLY = process.argv.includes('--apply');

async function main() {
  const connection = await mysql.createConnection({ host, port, user, password, database });
  try {
    const [rows] = await connection.execute(
      `SELECT COUNT(*) AS count FROM assets WHERE is_favorite = 1 AND folder_id IS NOT NULL`
    );
    const count = rows[0].count;
    console.log(`[preview] 满足 "is_favorite=1 AND folder_id IS NOT NULL" 的记录数：${count}`);

    if (count === 0) {
      console.log('没有需要修复的数据。');
      return;
    }

    if (!APPLY) {
      console.log('这是预览模式，未执行修改。如需修复请追加 --apply 参数。');
      return;
    }

    const [result] = await connection.execute(
      `UPDATE assets SET folder_id = NULL WHERE is_favorite = 1 AND folder_id IS NOT NULL`
    );
    console.log(`[applied] 已修复记录数：${result.affectedRows}`);
  } finally {
    await connection.end();
  }
}

main().catch((err) => {
  console.error('脚本执行失败：', err.message);
  process.exit(1);
});
