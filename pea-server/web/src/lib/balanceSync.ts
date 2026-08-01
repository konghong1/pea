/**
 * 余额兜底同步。
 *
 * 背景：余额的「快路径」是 WS 的 balance.changed 事件（后端 billing.service 预扣/退款时发布）。
 * 但 WS 天生不可靠——断连、后台休眠、代理超时都会丢事件，用户就会看到
 * 「点了生成，余额纹丝不动，手动点一下才更新」。
 *
 * 这里提供「慢路径」：在余额必然变动的时刻（受理成功 / 任务终态 / 退款）主动拉一次
 * GET /billing/balance。与 WS 事件天然幂等——两者都是把服务端权威值写进 store。
 *
 * 去抖：批量生成会连续受理多个任务，合并成一次请求即可。
 *
 * 实现说明：用动态 import 取 auth store，是为了打破 catalog.ts → auth.ts → catalog.ts 的
 * 模块循环（auth.refreshMe 依赖 catalog.getMe）。调用发生在定时器回调里，此时模块图早已就绪。
 */
let timer: ReturnType<typeof setTimeout> | null = null;

export function syncBalance(delayMs = 400): void {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = null;
    void import('../store/auth')
      .then(({ useAuth }) => useAuth.getState().refreshBalance())
      .catch(() => {
        /* 拉取失败不打扰用户：WS 事件或下次操作会补上 */
      });
  }, delayMs);
}
