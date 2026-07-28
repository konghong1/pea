import {
  Injectable,
  NotFoundException,
  BadRequestException,
  ForbiddenException,
} from '@nestjs/common';
import { randomUUID } from 'crypto';
import { DatabaseService } from '../../database/database.service';
import { FilesService } from '../files/files.service';
import type {
  CreateAssetFolderDto,
  UpdateAssetFolderDto,
  ListAssetsQueryDto,
  UpdateAssetDto,
} from './assets.dto';

type Row = any;

/** 素材库 Service：个人/团队双范围，文件夹 + 资源元数据 + 对象存储签名访问。 */
@Injectable()
export class AssetsService {
  constructor(
    private readonly db: DatabaseService,
    private readonly files: FilesService,
  ) {}

  // =================================================================
  // 文件夹
  // =================================================================
  async listFolders(userId: number, scope: 'personal' | 'team' = 'personal') {
    return this.db.query<Row[]>(
      `SELECT id, name, scope, parent_id, created_at, updated_at
       FROM asset_folders WHERE owner_id = ? AND scope = ?
       ORDER BY updated_at DESC`,
      [userId, scope],
    );
  }

  async createFolder(userId: number, dto: CreateAssetFolderDto) {
    const r = await this.db.query<any>(
      'INSERT INTO asset_folders (owner_id, name, scope, parent_id) VALUES (?, ?, ?, ?)',
      [userId, dto.name, dto.scope ?? 'personal', dto.parent_id ?? null],
    );
    return { id: (r as any).insertId, name: dto.name };
  }

  async updateFolder(
    userId: number,
    folderId: number,
    dto: UpdateAssetFolderDto,
  ) {
    const sets: string[] = [];
    const params: any[] = [];
    if (dto.name !== undefined) {
      sets.push('name = ?');
      params.push(dto.name);
    }
    if (dto.parent_id !== undefined) {
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
      `UPDATE asset_folders SET ${sets.join(', ')} WHERE id = ? AND owner_id = ?`,
      params,
    );
    if ((r as any).affectedRows === 0) throw new NotFoundException('folder not found');
    return { id: folderId, ...dto };
  }

  async deleteFolder(userId: number, folderId: number) {
    const r = await this.db.query<any>(
      'DELETE FROM asset_folders WHERE id = ? AND owner_id = ?',
      [folderId, userId],
    );
    if ((r as any).affectedRows === 0) throw new NotFoundException('folder not found');
    return { id: folderId, deleted: true };
  }

  // =================================================================
  // 资源
  // =================================================================
  async list(userId: number, q: ListAssetsQueryDto = {}) {
    const scope = q.scope ?? 'personal';
    const limit = Math.min(q.limit ?? 200, 500);
    const conds: string[] = ['owner_id = ?', 'scope = ?'];
    const params: any[] = [userId, scope];

    if (typeof q.folder_id === 'number' && q.folder_id >= 1) {
      conds.push('folder_id = ?');
      params.push(q.folder_id);
    }
    // 不传 folder_id (或 <=0) 时不做文件夹过滤, 返回该 scope 下全部素材。
    // 收藏视图需要跨文件夹聚合, 故此处不过滤 folder_id IS NULL。

    if (q.q) {
      conds.push('name LIKE ?');
      params.push(`%${q.q}%`);
    }

    const rows = await this.db.query<Row[]>(
      `SELECT id, folder_id, name, object_key, content_type, size,
              scope, source, is_favorite, created_at, updated_at
       FROM assets WHERE ${conds.join(' AND ')}
       ORDER BY is_favorite DESC, updated_at DESC LIMIT ${limit}`,
      params,
    );

    // 一次性签名访问 URL（1 小时）
    const items = await Promise.all(
      rows.map(async (row: Row) => ({
        ...row,
        url: await this.files.presignGet(row.object_key, userId, 3600),
      })),
    );
    return items;
  }

  async upload(
    userId: number,
    file: { originalname: string; mimetype: string; size: number; buffer: Buffer },
    folderId?: number,
    scope: 'personal' | 'team' = 'personal',
  ) {
    await this.ensureFolderOwner(userId, folderId);
    const suffix = file.originalname || 'untitled';
    const objectKey = `u:${userId}/assets/${randomUUID()}-${suffix}`;
    await this.files.putObject(objectKey, file.buffer, file.mimetype);

    const r = await this.db.query<any>(
      `INSERT INTO assets
       (owner_id, folder_id, name, object_key, content_type, size, scope, source)
       VALUES (?, ?, ?, ?, ?, ?, ?, 'upload')`,
      [userId, folderId ?? null, file.originalname, objectKey, file.mimetype, file.size ?? 0, scope],
    );
    const url = await this.files.presignGet(objectKey, userId, 3600);
    return {
      id: (r as any).insertId,
      name: file.originalname,
      object_key: objectKey,
      content_type: file.mimetype,
      size: file.size ?? 0,
      scope,
      url,
    };
  }

  async update(userId: number, assetId: number, dto: UpdateAssetDto) {
    const sets: string[] = [];
    const params: any[] = [];
    if (dto.name !== undefined) {
      sets.push('name = ?');
      params.push(dto.name);
    }
    if (dto.is_favorite !== undefined) {
      sets.push('is_favorite = ?');
      params.push(dto.is_favorite ? 1 : 0);
    }
    if (dto.folder_id !== undefined) {
      await this.ensureFolderOwner(userId, dto.folder_id ?? undefined);
      sets.push('folder_id = ?');
      params.push(dto.folder_id ?? null);
    }
    if (!sets.length) throw new BadRequestException('no updatable fields');
    sets.push('updated_at = NOW(3)');
    params.push(assetId, userId);

    const r = await this.db.query<any>(
      `UPDATE assets SET ${sets.join(', ')} WHERE id = ? AND owner_id = ?`,
      params,
    );
    if ((r as any).affectedRows === 0) throw new NotFoundException('asset not found');
    return { id: assetId, ...dto };
  }

  async delete(userId: number, assetId: number) {
    const rows = await this.db.query<Row[]>(
      'SELECT object_key FROM assets WHERE id = ? AND owner_id = ?',
      [assetId, userId],
    );
    if (!rows.length) throw new NotFoundException('asset not found');
    await this.db.query('DELETE FROM assets WHERE id = ? AND owner_id = ?', [assetId, userId]);
    try {
      await this.files.remove(rows[0].object_key, userId);
    } catch {
      // 元数据已删，对象清理失败不影响接口语义；后台可定期扫 orphan
    }
    return { id: assetId, deleted: true };
  }

  private async ensureFolderOwner(userId: number, folderId?: number) {
    if (!folderId) return;
    const rows = await this.db.query<Row[]>(
      'SELECT id FROM asset_folders WHERE id = ? AND owner_id = ?',
      [folderId, userId],
    );
    if (!rows.length) throw new ForbiddenException('folder not found');
  }
}
