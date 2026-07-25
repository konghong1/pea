import {
  Injectable,
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  UnauthorizedException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

/**
 * 管理员守卫: 在 JwtAuthGuard 之后使用, 校验 users.role='admin'。
 * 角色为权限单一真源 (不放进 JWT, 避免授予/撤销管理员后旧 token 仍有权)。
 * 每次请求查库一次 (users 主键点查, 成本可忽略)。
 */
@Injectable()
export class AdminGuard implements CanActivate {
  constructor(private readonly db: DatabaseService) {}

  async canActivate(ctx: ExecutionContext): Promise<boolean> {
    const req = ctx.switchToHttp().getRequest();
    const sub = req.user?.sub;
    if (!sub) throw new UnauthorizedException('missing user');
    const rows = await this.db.query<any[]>(
      'SELECT role FROM users WHERE id = ?',
      [sub],
    );
    if (!rows.length || rows[0].role !== 'admin') {
      throw new ForbiddenException('admin only');
    }
    return true;
  }
}
