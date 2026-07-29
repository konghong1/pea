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
      `[egress-proxy] 代理 ${proxy} 端口不通或无法经它出网到外部 AI, 已清除代理环境变量并退回直连 (axios/fetch 均直连)`,
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
 * 校验代理是否“真正可用” —— 不仅端口有人听, 还要能经它建隧道出网到外部 AI (apihub)。
 * 仅 TCP 连通会漏报“端口有人听但代理是废的/无法出网”的情况: 那会导致 fetch-models
 * 报 read ECONNRESET 这类令人困惑的错误。这里额外做一次真实 HTTP CONNECT 隧道到
 * apihub:443, 只有隧道建成功才认为代理可用。
 */
async function isProxyReachable(proxyUrl: string, timeoutMs = 3000): Promise<boolean> {
  let host: string | undefined;
  let port = 80;
  try {
    const u = new URL(proxyUrl);
    host = u.hostname || undefined;
    port = u.port ? Number(u.port) : u.protocol === 'https:' ? 443 : 80;
  } catch {
    return false;
  }
  if (!host) return false;

  const net = require('net');
  // 1) 先快速 TCP 连通性(端口有人听?)
  const tcpOk = await new Promise<boolean>((resolve) => {
    const s = net.connect(port, host as string);
    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      s.destroy();
      resolve(ok);
    };
    s.setTimeout(timeoutMs);
    s.once('connect', () => done(true));
    s.once('timeout', () => done(false));
    s.once('error', () => done(false));
  });
  if (!tcpOk) return false;

  // 2) 真实隧道测试: 经代理 CONNECT 到外部 AI (apihub:443), 验证能否真正出网
  return tunnelTest('apihub.agnes-ai.com', 443, host, port, timeoutMs);
}

/**
 * 经 HTTP 代理向 targetHost:targetPort 发起 CONNECT 隧道, 验证代理能否真正出网。
 * 收到 “2xx Connection established” 即视为可用(只验证 TCP/TLS 隧道可达, 不依赖对端应用层)。
 */
function tunnelTest(
  targetHost: string,
  targetPort: number,
  proxyHost: string,
  proxyPort: number,
  timeoutMs: number,
): Promise<boolean> {
  const net = require('net');
  return new Promise<boolean>((resolve) => {
    const sock = net.connect(proxyPort, proxyHost);
    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      try {
        sock.destroy();
      } catch {
        /* ignore */
      }
      resolve(ok);
    };
    sock.setTimeout(timeoutMs);
    sock.once('timeout', () => done(false));
    sock.once('error', () => done(false));
    sock.once('connect', () => {
      sock.write(
        `CONNECT ${targetHost}:${targetPort} HTTP/1.1\r\nHost: ${targetHost}:${targetPort}\r\n\r\n`,
      );
    });
    let buf = '';
    sock.once('data', (d: Buffer) => {
      buf += d.toString();
      if (buf.includes('\r\n\r\n')) {
        const statusLine = buf.split('\r\n')[0];
        done(/^HTTP\/\d\.\d 2\d\d /.test(statusLine));
      }
    });
  });
}
