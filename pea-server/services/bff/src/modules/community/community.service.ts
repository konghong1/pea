import { Injectable, NotFoundException, BadRequestException } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

export interface WorkRow {
  id: number;
  user_id: number;
  media_urls: string | null;
  caption: string;
  created_at: Date;
  likes_count: number;
  comments_count: number;
  favorites_count: number;
  display_name: string;
  liked_by_me: number;
  favorited_by_me: number;
}

export interface CommentRow {
  id: number;
  work_id: number;
  user_id: number;
  content: string;
  created_at: Date;
  display_name: string;
}

/** E9 社区 / TapTV (T-M4-01/02): feed、发布、点赞、收藏、评论。 */
@Injectable()
export class CommunityService {
  constructor(private readonly db: DatabaseService) {}

  async feed(userId: number, limit = 20): Promise<WorkRow[]> {
    const rows = await this.db.query<WorkRow[]>(
      `SELECT w.id, w.user_id, w.media_urls, w.caption, w.created_at,
              w.likes_count, w.comments_count, w.favorites_count,
              u.display_name,
              EXISTS(SELECT 1 FROM work_likes wl WHERE wl.work_id = w.id AND wl.user_id = ?) AS liked_by_me,
              EXISTS(SELECT 1 FROM work_favorites wf WHERE wf.work_id = w.id AND wf.user_id = ?) AS favorited_by_me
       FROM works w
       JOIN users u ON u.id = w.user_id
       ORDER BY w.id DESC
       LIMIT ?`,
      [userId, userId, limit],
    );
    return rows;
  }

  async detail(userId: number, workId: number): Promise<WorkRow> {
    const rows = await this.db.query<WorkRow[]>(
      `SELECT w.id, w.user_id, w.media_urls, w.caption, w.created_at,
              w.likes_count, w.comments_count, w.favorites_count,
              u.display_name,
              EXISTS(SELECT 1 FROM work_likes wl WHERE wl.work_id = w.id AND wl.user_id = ?) AS liked_by_me,
              EXISTS(SELECT 1 FROM work_favorites wf WHERE wf.work_id = w.id AND wf.user_id = ?) AS favorited_by_me
       FROM works w
       JOIN users u ON u.id = w.user_id
       WHERE w.id = ?`,
      [userId, userId, workId],
    );
    if (!rows.length) throw new NotFoundException('work not found');
    return rows[0];
  }

  async create(userId: number, caption: string, mediaUrls: string[] = []): Promise<WorkRow> {
    if (!caption.trim() && (!mediaUrls || mediaUrls.length === 0)) {
      throw new BadRequestException('caption or media required');
    }
    const res = await this.db.query(
      'INSERT INTO works (user_id, media_urls, caption, created_at) VALUES (?, ?, ?, NOW(3))',
      [userId, JSON.stringify(mediaUrls), caption],
    );
    const insertId = (res as any).insertId;
    return this.detail(userId, insertId);
  }

  /** 点赞: 幂等插入 + 计数 +1。 */
  async like(userId: number, workId: number): Promise<{ ok: true }> {
    await this.detail(userId, workId); // 校验存在
    const exists = await this.db.query<any[]>(
      'SELECT 1 FROM work_likes WHERE work_id = ? AND user_id = ?',
      [workId, userId],
    );
    if (!exists.length) {
      await this.db.query(
        'INSERT INTO work_likes (work_id, user_id, created_at) VALUES (?, ?, NOW(3))',
        [workId, userId],
      );
      await this.db.query('UPDATE works SET likes_count = likes_count + 1 WHERE id = ?', [workId]);
    }
    return { ok: true };
  }

  /** 取消点赞: 存在则删除 + 计数 -1（下限 0）。 */
  async unlike(userId: number, workId: number): Promise<{ ok: true }> {
    await this.detail(userId, workId);
    const exists = await this.db.query<any[]>(
      'SELECT 1 FROM work_likes WHERE work_id = ? AND user_id = ?',
      [workId, userId],
    );
    if (exists.length) {
      await this.db.query('DELETE FROM work_likes WHERE work_id = ? AND user_id = ?', [workId, userId]);
      await this.db.query('UPDATE works SET likes_count = GREATEST(likes_count - 1, 0) WHERE id = ?', [workId]);
    }
    return { ok: true };
  }

  async favorite(userId: number, workId: number): Promise<{ ok: true }> {
    await this.detail(userId, workId);
    const exists = await this.db.query<any[]>(
      'SELECT 1 FROM work_favorites WHERE work_id = ? AND user_id = ?',
      [workId, userId],
    );
    if (!exists.length) {
      await this.db.query(
        'INSERT INTO work_favorites (work_id, user_id, created_at) VALUES (?, ?, NOW(3))',
        [workId, userId],
      );
      await this.db.query('UPDATE works SET favorites_count = favorites_count + 1 WHERE id = ?', [workId]);
    }
    return { ok: true };
  }

  async unfavorite(userId: number, workId: number): Promise<{ ok: true }> {
    await this.detail(userId, workId);
    const exists = await this.db.query<any[]>(
      'SELECT 1 FROM work_favorites WHERE work_id = ? AND user_id = ?',
      [workId, userId],
    );
    if (exists.length) {
      await this.db.query('DELETE FROM work_favorites WHERE work_id = ? AND user_id = ?', [workId, userId]);
      await this.db.query('UPDATE works SET favorites_count = GREATEST(favorites_count - 1, 0) WHERE id = ?', [workId]);
    }
    return { ok: true };
  }

  async comments(workId: number): Promise<CommentRow[]> {
    return this.db.query<CommentRow[]>(
      `SELECT c.id, c.work_id, c.user_id, c.content, c.created_at, u.display_name
       FROM work_comments c JOIN users u ON u.id = c.user_id
       WHERE c.work_id = ?
       ORDER BY c.id ASC`,
      [workId],
    );
  }

  async addComment(userId: number, workId: number, content: string): Promise<CommentRow> {
    await this.detail(userId, workId);
    const res = await this.db.query(
      'INSERT INTO work_comments (work_id, user_id, content, created_at) VALUES (?, ?, ?, NOW(3))',
      [workId, userId, content],
    );
    const insertId = (res as any).insertId;
    await this.db.query('UPDATE works SET comments_count = comments_count + 1 WHERE id = ?', [workId]);
    const rows = await this.db.query<CommentRow[]>(
      `SELECT c.id, c.work_id, c.user_id, c.content, c.created_at, u.display_name
       FROM work_comments c JOIN users u ON u.id = c.user_id
       WHERE c.id = ?`,
      [insertId],
    );
    return rows[0];
  }
}
