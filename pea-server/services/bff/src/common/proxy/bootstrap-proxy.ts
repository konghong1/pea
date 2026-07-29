import { Logger } from '@nestjs/common';

const logger = new Logger('EgressProxy');

/**
 * 可选出网代理引导 (镜像 ai-agent 的方案).
 *
 * 仅当容器设置了 HTTPS_PROXY / HTTP_PROXY 时生效 —— 这由 docker-compose.proxy-override.yml
 * 在 PEA_PROXY_FIX=1 时注入。默认(无代理 env)为空操作, 完全走直连, 不影响任何现有行为。
 *
 * 为什么必须这段代码:
 *   bff 用 Node 内置 fetch(内部 undici) 调外部 AI (apihub)。Node 内置 fetch 用的 undici
 *   与 npm 安装的 undici 是两套独立的 global dispatcher, 因此:
 *     - 仅设置 HTTPS_PROXY env 不够; axios 会自动读 env 走代理, 但内置 fetch 不会。
 *     - 必须用 npm undici 的 EnvHttpProxyAgent 作为全局 dispatcher, 并显式用 npm undici
 *       的 fetch 覆盖 globalThis.fetch, 才能让全局 fetch 也走代理。
 *
 * 内部地址 (bff / generation-orchestrator / mysql / redis / minio) 已在 NO_PROXY 中,
 * 出网时直连, 不经代理。
 */
export function installEgressProxyFromEnv(): void {
  const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
  if (!proxy) return; // 无代理 env => 直连, 空操作

  try {
    // 动态 require: 即便未安装 undici 也不会让启动时崩溃(回退直连)
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const undici = require('undici');
    if (!undici?.setGlobalDispatcher || !undici?.EnvHttpProxyAgent || !undici?.fetch) {
      logger.warn('[egress-proxy] undici 不可用, 跳过代理安装(回退直连)');
      return;
    }
    // EnvHttpProxyAgent 自动读取 HTTPS_PROXY/HTTP_PROXY/NO_PROXY 环境, 含 NO_PROXY 白名单
    undici.setGlobalDispatcher(new undici.EnvHttpProxyAgent());
    // 覆盖内置 fetch, 使其走上面的代理 dispatcher
    (globalThis as unknown as { fetch: unknown }).fetch = undici.fetch;
    logger.log(`[egress-proxy] 已启用出网代理, 上游=${proxy}`);
  } catch (e: any) {
    logger.warn(`[egress-proxy] 安装失败, 回退直连: ${e?.message ?? e}`);
  }
}
