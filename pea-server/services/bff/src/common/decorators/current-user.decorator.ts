import { createParamDecorator, ExecutionContext } from '@nestjs/common';

/** 从请求中取出当前用户 (JWT 守卫已校验并挂载). */
export const CurrentUser = createParamDecorator(
  (_data: unknown, ctx: ExecutionContext) => {
    const req = ctx.switchToHttp().getRequest();
    return req.user;
  },
);
