import { Injectable, NotFoundException } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

@Injectable()
export class UsersService {
  constructor(private readonly db: DatabaseService) {}

  async getProfile(userId: number) {
    const rows = await this.db.query<any[]>(
      'SELECT id, email, display_name, avatar_url, created_at FROM users WHERE id = ?',
      [userId],
    );
    if (!rows.length) throw new NotFoundException('user not found');
    return rows[0];
  }
}
