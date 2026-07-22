import {
  Injectable,
  CanActivate,
  ExecutionContext,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

/** 内部服务鉴权: 仅允许携带正确 X-Service-Token 的下游服务 (如 orchestrator 退款). */
@Injectable()
export class InternalAuthGuard implements CanActivate {
  constructor(private readonly config: ConfigService) {}

  canActivate(ctx: ExecutionContext): boolean {
    const req = ctx.switchToHttp().getRequest();
    const token = req.headers['x-service-token'];
    if (token !== this.config.get('internalToken')) {
      throw new UnauthorizedException('invalid service token');
    }
    return true;
  }
}
