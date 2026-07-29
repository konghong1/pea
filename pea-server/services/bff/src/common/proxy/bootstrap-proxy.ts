import { Logger } from '@nestjs/common';

const logger = new Logger('EgressProxy');

/**
 * 可选出网代理引导 (镜像 ai-agent 的方案).
 *
 * 仅当容器设置了 HTTPS_PROXY / HTTP_PROXY 时生效 —— 这由 docker-compose.proxy-override.yml
 * 在 PEA_PROXY_FIX=1 时注入。无代理 env 时为空操作, 完全走直连。即便是设置了代理,
 * 若探测发现代理不可达也会退回直连(镜像 ai-agent 的 ensure_proxy_strategy 行为),
 * 不再因坏代理导致所有出网请求 ECONNREFUSED。
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
export async function installEgressProxyFromEnv(): Promise<void> {
  const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
  if (!proxy) return; // 无代理 env => 直连, 空操作

  // 镜像 ai-agent 的 ensure_proxy_strategy(): 先探测代理是否真可达。
  // 关键修复 —— 之前只要设了 HTTPS_PROXY 就无条件安装 dispatcher, 代理连不上 =>
  // 所有出网请求(含 fetch remote models)直接 ECONNREFUSED 全死。现在: 代理不可达时
  // 跳过安装、退回直连, 与 ai-agent 行为一致, 不再因坏代理硬崩。
  if (!(await isProxyReachable(proxy))) {
    // ★ 必须同时清掉环境变量: axios / got 等库会各自读 HTTP(S)_PROXY 走代理,
    //   仅"跳过 fetch dispatcher 安装"救不了它们。死代理不清 env 的直接后果就是
    //   /admin/providers/:id/fetch-models (axios) 报 connect ECONNREFUSED <代理IP>:33210。
    delete process.env.HTTPS_PROXY;
    delete process.env.HTTP_PROXY;
    delete process.env.https_proxy;
    delete process.env.http_proxy;
    logger.warn(
      `[egress-proxy] 代理 ${proxy} 不可达, 已清除代理环境变量并退回直连 (axios/fetch 均直连)`,
    );
    return;
  }

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

/**
 * TCP 探测代理地址是否可连通(超时即判不可达)。
 * 仅校验“端口有人监听”, 不校验代理能否真正出网 —— 足以区分“坏/不存在的代理”与“可用代理”。
 */
function isProxyReachable(proxyUrl: string, timeoutMs = 2000): Promise<boolean> {
  let host: string | undefined;
  let port = 80;
  try {
    const u = new URL(proxyUrl);
    host = u.hostname || undefined;
    port = u.port ? Number(u.port) : u.protocol === 'https:' ? 443 : 80;
  } catch {
    return Promise.resolve(false);
  }
  if (!host) return Promise.resolve(false);
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const net = require('net');
  return new Promise<boolean>((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(true));
    socket.once('timeout', () => done(false));
    socket.once('error', () => done(false));
    socket.connect(port, host);
  });
}
