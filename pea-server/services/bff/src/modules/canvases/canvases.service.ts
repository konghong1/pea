import {
  Injectable,
  ConflictException,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import type {
  CreateCanvasDto,
  CreateFolderDto,
  ListCanvasesQueryDto,
  SaveCanvasDto,
  UpdateCanvasDto,
  UpdateFolderDto,
} from './canvases.dto';

/** 行类型（mysql2 RowDataPacket 是动态的，全部用 any 简化）。 */
type Row = any;

const SHARE_TOKEN_LEN = 22;
const SHARE_ALPHABET =
  'abcdefghijkmnpqrstuvwxyz23456789ABCDEFGHJKLMNPQRSTUVWXYZ';

/**
 * 画布 CRUD + 分享 + 文件夹 (FR-G2 / T-M3-01 升级)。
 *
 * - 软删除: canvases.deleted_at, 列表默认过滤 NULL；trash scope 才返回已删。
 * - owner 隔离: 所有写操作都校验 owner_id = u.sub。
 * - share_token: 公开只读端点用此入 (无 JWT)。
 */
@Injectable()
export class CanvasesService {
  constructor(private readonly db: DatabaseService) {}

  // =================================================================
  // 画布 CRUD
  // =================================================================
  async create(userId: number, dto: CreateCanvasDto) {
    const scope = dto.scope ?? 'personal';
    const folderId = dto.folder_id ?? null;
    const r = await this.db.query<any>(
      "INSERT INTO canvases (owner_id, title, scope, folder_id, graph_json, version) VALUES (?, ?, ?, ?, '{\"nodes\":[],\"edges\":[]}', 1)",
      [userId, dto.title ?? 'Untitled', scope, folderId],
    );
    return { id: (r as any).insertId, title: dto.title ?? 'Untitled', scope, version: 1 };
  }

  async save(userId: number, canvasId: number, graph_json: object, version: number) {
    const json = JSON.stringify(graph_json);
    const result = await this.db.query<any>(
      `UPDATE canvases SET graph_json = ?, version = version + 1, updated_at = NOW(3)
       WHERE id = ? AND owner_id = ? AND version = ? AND deleted_at IS NULL`,
      [json, canvasId, userId, version],
    );
    if ((result as any).affectedRows === 0) {
      const cur = await this.db.query<Row[]>(
        'SELECT version, deleted_at FROM canvases WHERE id = ? AND owner_id = ?',
        [canvasId, userId],
      );
      if (!cur.length) throw new NotFoundException('canvas not found');
      if (cur[0].deleted_at) throw new NotFoundException('canvas is in trash');
      throw new ConflictException({
        message: 'canvas version conflict',
        currentVersion: cur[0].version,
      });
    }
    await this.db.query(
      'INSERT INTO canvas_versions (canvas_id, version, graph_json) SELECT id, version, graph_json FROM canvases WHERE id = ?',
      [canvasId],
    );
    const after = await this.db.query<Row[]>(
      'SELECT version FROM canvases WHERE id = ?',
      [canvasId],
    );
    return { id: canvasId, version: after[0].version };
  }

  /**
   * 列表，支持 scope/folder_id/关键字过滤。
   * - scope=personal|team -> deleted_at IS NULL
   * - scope=trash         -> deleted_at IS NOT NULL
   * - scope=all           -> 包含已删（前端"全部"用）
   */
  async list(userId: number, q: ListCanvasesQueryDto = {}) {
    const scope = q.scope ?? 'personal';
    const limit = Math.min(q.limit ?? 60, 200);
    const conds: string[] = ['owner_id = ?'];
    const params: any[] = [userId];

    if (scope === 'trash') {
      conds[0] = 'owner_id = ? AND deleted_at IS NOT NULL';
    } else if (scope === 'all') {
      // 全部（含已删）；前端列表项可按 deleted_at 显示标记
    } else {
      conds.push('deleted_at IS NULL');
      conds.push('scope = ?');
      params.push(scope);
    }

    if (typeof q.folder_id === 'number' && q.folder_id >= 1) {
      conds.push('folder_id = ?');
      params.push(q.folder_id);
    } else if (scope !== 'trash') {
      // 根目录 = folder_id IS NULL
      conds.push('folder_id IS NULL');
    }

    if (q.q) {
      conds.push('title LIKE ?');
      params.push(`%${q.q}%`);
    }

    const sql = `SELECT id, title, scope, folder_id, share_token, thumbnail_url,
                        version, node_count, created_at, updated_at, deleted_at
                 FROM canvases WHERE ${conds.join(' AND ')}
                 ORDER BY updated_at DESC LIMIT ${limit}`;
    return this.db.query<Row[]>(sql, params);
  }

  async get(userId: number, canvasId: number) {
    const rows = await this.db.query<Row[]>(
      `SELECT id, title, scope, folder_id, share_token, thumbnail_url,
              graph_json, version, created_at, updated_at, deleted_at
       FROM canvases WHERE id = ? AND owner_id = ?`,
      [canvasId, userId],
    );
    if (!rows.length) throw new NotFoundException('canvas not found');
    return rows[0];
  }

  async update(userId: number, canvasId: number, dto: UpdateCanvasDto) {
    // 软删除 / 恢复
    if (dto.deleted === true) {
      await this.db.query(
        'UPDATE canvases SET deleted_at = NOW(3) WHERE id = ? AND owner_id = ?',
        [canvasId, userId],
      );
      return { id: canvasId, deleted: true };
    }
    if (dto.deleted === false) {
      await this.db.query(
        'UPDATE canvases SET deleted_at = NULL WHERE id = ? AND owner_id = ?',
        [canvasId, userId],
      );
      return { id: canvasId, deleted: false };
    }

    const sets: string[] = [];
    const params: any[] = [];
    if (dto.title !== undefined) { sets.push('title = ?'); params.push(dto.title); }
    if (dto.scope !== undefined) { sets.push('scope = ?'); params.push(dto.scope); }
    if (dto.folder_id !== undefined) {
      sets.push('folder_id = ?');
      params.push(dto.folder_id);
    }
    if (dto.thumbnail_url !== undefined) {
      sets.push('thumbnail_url = ?');
      params.push(dto.thumbnail_url);
    }
    if (!sets.length) {
      throw new BadRequestException('no updatable fields');
    }
    sets.push('updated_at = NOW(3)');
    params.push(canvasId, userId);
    const r = await this.db.query<any>(
      `UPDATE canvases SET ${sets.join(', ')} WHERE id = ? AND owner_id = ?`,
      params,
    );
    if ((r as any).affectedRows === 0) {
      throw new NotFoundException('canvas not found');
    }
    return { id: canvasId, ...dto };
  }

  /** 物理删除（仅软删除后再调用）；M3 阶段不开放前台入口。 */
  async hardDelete(userId: number, canvasId: number) {
    const r = await this.db.query<any>(
      'DELETE FROM canvases WHERE id = ? AND owner_id = ?',
      [canvasId, userId],
    );
    if ((r as any).affectedRows === 0) {
      throw new NotFoundException('canvas not found');
    }
    return { id: canvasId, deleted: true };
  }

  // =================================================================
  // 分享 (share_token)
  // =================================================================
  private genToken(): string {
    let s = '';
    const a = SHARE_ALPHABET;
    for (let i = 0; i < SHARE_TOKEN_LEN; i++) {
      s += a[Math.floor(Math.random() * a.length)];
    }
    return s;
  }

  /** 创建或返回已有的 share_token；保证唯一（碰撞则重试）。 */
  async ensureShareToken(userId: number, canvasId: number) {
    const cur = await this.db.query<Row[]>(
      'SELECT share_token FROM canvases WHERE id = ? AND owner_id = ?',
      [canvasId, userId],
    );
    if (!cur.length) throw new NotFoundException('canvas not found');
    if (cur[0].share_token) return { token: cur[0].share_token };

    for (let i = 0; i < 5; i++) {
      const t = this.genToken();
      try {
        await this.db.query(
          'UPDATE canvases SET share_token = ? WHERE id = ? AND owner_id = ? AND share_token IS NULL',
          [t, canvasId, userId],
        );
        return { token: t };
      } catch (e: any) {
        // 唯一冲突 -> 重试
        if (!/Duplicate entry/i.test(e?.message ?? '')) throw e;
      }
    }
    throw new ConflictException('failed to allocate share token');
  }

  async revokeShareToken(userId: number, canvasId: number) {
    await this.db.query(
      'UPDATE canvases SET share_token = NULL WHERE id = ? AND owner_id = ?',
      [canvasId, userId],
    );
    return { id: canvasId, share_token: null };
  }

  /** 公开只读 (无 JWT)：分享链接打开后用 token 取画布内容。 */
  async getByShareToken(token: string) {
    if (!token || token.length !== SHARE_TOKEN_LEN) {
      throw new NotFoundException('canvas not found');
    }
    const rows = await this.db.query<Row[]>(
      `SELECT id, owner_id, title, scope, thumbnail_url,
              graph_json, version, created_at, updated_at
       FROM canvases WHERE share_token = ? AND deleted_at IS NULL`,
      [token],
    );
    if (!rows.length) throw new NotFoundException('canvas not found');
    return rows[0];
  }

  // =================================================================
  // 文件夹 (canvas_folders)
  // =================================================================
  async listFolders(userId: number, scope: 'personal' | 'team' = 'personal') {
    return this.db.query<Row[]>(
      `SELECT id, name, scope, parent_id, created_at, updated_at
       FROM canvas_folders WHERE owner_id = ? AND scope = ?
       ORDER BY updated_at DESC`,
      [userId, scope],
    );
  }

  async createFolder(userId: number, dto: CreateFolderDto) {
    const r = await this.db.query<any>(
      'INSERT INTO canvas_folders (owner_id, name, scope, parent_id) VALUES (?, ?, ?, ?)',
      [userId, dto.name, dto.scope ?? 'personal', dto.parent_id ?? null],
    );
    return { id: (r as any).insertId, name: dto.name };
  }

  async updateFolder(userId: number, folderId: number, dto: UpdateFolderDto) {
    const sets: string[] = [];
    const params: any[] = [];
    if (dto.name !== undefined) { sets.push('name = ?'); params.push(dto.name); }
    if (dto.parent_id !== undefined) {
      // 防环：parent_id 不能等于自身或其后代 (M3 简化：仅防自指)
      if (dto.parent_id === folderId) {
        throw new BadRequestException('folder cannot be its own parent');
      }
      sets.push('parent_id = ?');
      params.push(dto.parent_id);
    }
    if (!sets.length) throw new BadRequestException('no updatable fields');
    sets.push('updated_at = NOW(3)');
    params.push(folderId, userId);
    const r = await this.db.query<any>(
      `UPDATE canvas_folders SET ${sets.join(', ')} WHERE id = ? AND owner_id = ?`,
      params,
    );
    if ((r as any).affectedRows === 0) throw new NotFoundException('folder not found');
    return { id: folderId, ...dto };
  }

  async deleteFolder(userId: number, folderId: number) {
    // ON DELETE SET NULL 已配 FK；删文件夹会让其中画布回到根目录。
    const r = await this.db.query<any>(
      'DELETE FROM canvas_folders WHERE id = ? AND owner_id = ?',
      [folderId, userId],
    );
    if ((r as any).affectedRows === 0) throw new NotFoundException('folder not found');
    return { id: folderId, deleted: true };
  }
}