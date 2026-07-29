import {
  Injectable,
  CanActivate,
  ExecutionContext,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { DatabaseService } from '../../database/database.service';

/**
 * 校验 Authorization: Bearer <token>, 挂载 req.user = { sub, email }。
 * 额外防御: 校验 users 表中确实存在该 id —— 避免 DB 重建/用户删除后, 旧 token 仍可过签名校验,
 * 却在写 canvases/assets 等带外键的表时炸出 500 的诡异现象 (T-OBS 实战: volume rm 重建库后旧 JWT 触发 FK 失败)。
 * DB 查询异常时 fail-open, 不阻断已签名合法的请求。
 */
@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly db: DatabaseService,
  ) {}

  async canActivate(ctx: ExecutionContext): Promise<boolean> {
    const req = ctx.switchToHttp().getRequest();
    const header = req.headers['authorization'] ?? '';
    const token = header.startsWith('Bearer ') ? header.slice(7) : null;
    if (!token) throw new UnauthorizedException('missing token');
    let payload: any;
    try {
      payload = this.jwt.verify(token, {
        secret: this.config.get('jwt.secret'),
      });
    } catch {
      throw new UnauthorizedException('invalid token');
    }
    const sub = Number(payload.sub);
    if (!Number.isFinite(sub)) throw new UnauthorizedException('invalid token');

    // 防御: 用户可能已被删除 / DB 已重建, 旧 token 签名仍有效 -> 让其重新登录 (避免下游 FK 500)
    try {
      const rows = await this.db.query<any[]>(
        'SELECT 1 FROM users WHERE id = ? LIMIT 1',
        [sub],
      );
      if (!rows.length) {
        throw new UnauthorizedException('user no longer exists, please re-login');
      }
    } catch (e) {
      if (e instanceof UnauthorizedException) throw e;
      // DB 暂不可用时 fail-open: 不阻断已签名合法的请求
    }

    req.user = { sub, email: payload.email };
    return true;
  }
}
