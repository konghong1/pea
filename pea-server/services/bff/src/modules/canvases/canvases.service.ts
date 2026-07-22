import {
  Injectable,
  ConflictException,
  NotFoundException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

/**
 * 画布自动保存 (E3 / T-CANVAS-SAVE): 解决 PRD 痛点 "刷新即丢".
 * 乐观锁: 保存携带客户端 version, 冲突返回 409 由前端提示解决.
 */
@Injectable()
export class CanvasesService {
  constructor(private readonly db: DatabaseService) {}

  async create(userId: number, title = 'Untitled') {
    // DatabaseService.query already unwraps to OkPacket for writes / RowDataPacket[] for reads.
    const r = await this.db.query<any>(
      "INSERT INTO canvases (owner_id, title, graph_json, version) VALUES (?, ?, '{\"nodes\":[],\"edges\":[]}', 1)",
      [userId, title],
    );
    return { id: (r as any).insertId, title, version: 1 };
  }

  async save(userId: number, canvasId: number, graph_json: object, version: number) {
    const json = JSON.stringify(graph_json);
    const result = await this.db.query<any>(
      `UPDATE canvases SET graph_json = ?, version = version + 1, updated_at = NOW(3)
       WHERE id = ? AND owner_id = ? AND version = ?`,
      [json, canvasId, userId, version],
    );
    if ((result as any).affectedRows === 0) {
      // 版本不符 = 并发编辑冲突
      const cur = await this.db.query<any[]>(
        'SELECT version FROM canvases WHERE id = ? AND owner_id = ?',
        [canvasId, userId],
      );
      if (!cur.length) throw new NotFoundException('canvas not found');
      throw new ConflictException({
        message: 'canvas version conflict',
        currentVersion: cur[0].version,
      });
    }
    // 写历史版本
    await this.db.query(
      'INSERT INTO canvas_versions (canvas_id, version, graph_json) SELECT id, version, graph_json FROM canvases WHERE id = ?',
      [canvasId],
    );
    const after = await this.db.query<any[]>(
      'SELECT version FROM canvases WHERE id = ?',
      [canvasId],
    );
    return { id: canvasId, version: after[0].version };
  }

  async list(userId: number) {
    const rows = await this.db.query<any[]>(
      `SELECT id, title, version, node_count, updated_at
       FROM canvases WHERE owner_id = ? ORDER BY updated_at DESC LIMIT 20`,
      [userId],
    );
    return rows;
  }

  async get(userId: number, canvasId: number) {
    const rows = await this.db.query<any[]>(
      'SELECT id, title, graph_json, version, updated_at FROM canvases WHERE id = ? AND owner_id = ?',
      [canvasId, userId],
    );
    if (!rows.length) throw new NotFoundException('canvas not found');
    return rows[0];
  }
}
