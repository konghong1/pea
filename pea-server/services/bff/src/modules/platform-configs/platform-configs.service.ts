import { Injectable, NotFoundException, ForbiddenException, BadRequestException } from '@nestjs/common';
import { randomUUID } from 'crypto';
import { DatabaseService } from '../../database/database.service';
import {
  CreatePlatformConfigDto,
  UpdatePlatformConfigDto,
} from './platform-configs.dto';

type Row = any;

/**
 * 平台提示词配置 (Phase2): 用户对图片/视频节点所选"平台"的提示词构造参数。
 *
 * - owner 隔离: 所有写操作校验 owner_id = u.sub。
 * - 节点级 platform_config_id (前端绑定) -> 未绑时回退用户默认 (is_default)。
 * - CRUD 归 BFF; 编排器只按 id 读 platform_configs 表 (只读)。
 */
@Injectable()
export class PlatformConfigsService {
  constructor(private readonly db: DatabaseService) {}

  async list(userId: number, kind?: 'image' | 'video') {
    const sql =
      'SELECT id, name, platform, kind, prompt_mode, presets_json, expand_model, is_default, created_at, updated_at ' +
      'FROM platform_configs WHERE owner_id = ?' +
      (kind ? ' AND kind = ?' : '') +
      ' ORDER BY is_default DESC, created_at ASC';
    const rows = await this.db.query<Row[]>(sql, kind ? [userId, kind] : [userId]);
    return rows.map(this.toDto);
  }

  async get(userId: number, id: string) {
    const rows = await this.db.query<Row[]>(
      'SELECT * FROM platform_configs WHERE id = ? AND owner_id = ?',
      [id, userId],
    );
    if (!rows.length) throw new NotFoundException('platform config not found');
    return this.toDto(rows[0]);
  }

  async create(userId: number, dto: CreatePlatformConfigDto) {
    const id = `pc_${randomUUID().replace(/-/g, '').slice(0, 20)}`;
    const presets = dto.presets ?? {};
    if (dto.isDefault) {
      await this.clearDefault(userId, dto.kind);
    }
    await this.db.query(
      `INSERT INTO platform_configs
       (id, owner_id, name, platform, kind, prompt_mode, presets_json, expand_model, is_default)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        id, userId, dto.name, dto.platform ?? 'generic', dto.kind, dto.promptMode ?? 'plain',
        JSON.stringify(presets), dto.expandModel ?? null, dto.isDefault ? 1 : 0,
      ],
    );
    return this.get(userId, id);
  }

  async update(userId: number, id: string, dto: UpdatePlatformConfigDto) {
    const existing = await this.get(userId, id); // 校验归属
    if (dto.isDefault) {
      await this.clearDefault(userId, existing.kind);
    }
    const sets: string[] = [];
    const vals: any[] = [];
    if (dto.name !== undefined) { sets.push('name = ?'); vals.push(dto.name); }
    if (dto.platform !== undefined) { sets.push('platform = ?'); vals.push(dto.platform); }
    if (dto.promptMode !== undefined) { sets.push('prompt_mode = ?'); vals.push(dto.promptMode); }
    if (dto.presets !== undefined) { sets.push('presets_json = ?'); vals.push(JSON.stringify(dto.presets)); }
    if (dto.expandModel !== undefined) { sets.push('expand_model = ?'); vals.push(dto.expandModel); }
    if (dto.isDefault !== undefined) { sets.push('is_default = ?'); vals.push(dto.isDefault ? 1 : 0); }
    if (!sets.length) return existing;
    vals.push(id, userId);
    await this.db.query(
      `UPDATE platform_configs SET ${sets.join(', ')} WHERE id = ? AND owner_id = ?`,
      vals,
    );
    return this.get(userId, id);
  }

  async remove(userId: number, id: string) {
    const existing = await this.get(userId, id);
    await this.db.query(
      'DELETE FROM platform_configs WHERE id = ? AND owner_id = ?',
      [id, userId],
    );
    return { id, deleted: true };
  }

  async setDefault(userId: number, id: string) {
    const existing = await this.get(userId, id);
    await this.clearDefault(userId, existing.kind);
    await this.db.query(
      'UPDATE platform_configs SET is_default = 1 WHERE id = ? AND owner_id = ?',
      [id, userId],
    );
    return this.get(userId, id);
  }

  /** 解析节点生效配置: 指定 id 优先, 否则用户默认, 再否则返回 null (编排器原样用聊天文本)。 */
  async resolveEffective(userId: number, kind: 'image' | 'video', id?: string | null) {
    if (id) {
      try {
        return await this.get(userId, id);
      } catch (e) {
        if (!(e instanceof NotFoundException)) throw e;
      }
    }
    const rows = await this.db.query<Row[]>(
      'SELECT * FROM platform_configs WHERE owner_id = ? AND kind = ? AND is_default = 1 LIMIT 1',
      [userId, kind],
    );
    return rows.length ? this.toDto(rows[0]) : null;
  }

  // ── 内部 ──────────────────────────────────────────────
  private async clearDefault(userId: number, kind: 'image' | 'video') {
    await this.db.query(
      'UPDATE platform_configs SET is_default = 0 WHERE owner_id = ? AND kind = ?',
      [userId, kind],
    );
  }

  private toDto(r: Row) {
    return {
      id: r.id,
      name: r.name,
      platform: r.platform,
      kind: r.kind,
      promptMode: r.prompt_mode,
      presets: typeof r.presets_json === 'string' ? JSON.parse(r.presets_json || '{}') : (r.presets_json ?? {}),
      expandModel: r.expand_model ?? null,
      isDefault: !!r.is_default,
      createdAt: r.created_at,
      updatedAt: r.updated_at,
    };
  }
}
