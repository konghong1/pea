import { Injectable, Logger } from '@nestjs/common';

export interface StreamOpts {
  baseUrl: string;
  apiKey: string;
  model: string;
  prompt: string;
  system?: string;
  /** 无真实服务商时走本地 mock 流 (便于离线开发/测试)。 */
  mock?: boolean;
}

export interface UsageInfo {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

/**
 * 归一化 OpenAI 兼容 chat 端点 URL。
 * 与 orchestrator 的 _api_base / providers.normalizeModelsUrl 保持同一约定:
 * provider.base_url 可能已含 /v1 (本项目 OpenAI 兼容网关的存储约定) 或 /api/v3
 * (火山方舟等厂商的 OpenAI 兼容前缀), 这里做归一化, 避免出现
 * /v1/v1/chat/completions 或 /api/v3/v1/chat/completions 导致上游 404。
 */
export function buildOpenAIChatUrl(baseUrl: string): string {
  let base = (baseUrl || '').replace(/\/+$/, '');
  // 火山方舟: chat/completions 在 /api/v3/chat/completions (版本前缀即 /api/v3)。
  if (base.endsWith('/api/v3')) {
    return `${base}/chat/completions`;
  }
  if (base.endsWith('/v1')) base = base.slice(0, -3);
  return `${base}/v1/chat/completions`;
}

/**
 * OpenAI 兼容的流式文本客户端 (文本节点聊天用)。
 * 直接调用 provider.base_url/v1/chat/completions, 逐 delta 产出, 并尝试解析 usage。
 * 设计为纯 HTTP, 不持有状态, 便于替换/测试。
 */
@Injectable()
export class LlmStreamClient {
  private readonly logger = new Logger(LlmStreamClient.name);

  async *stream(
    opts: StreamOpts,
  ): AsyncGenerator<{ delta?: string; usage?: UsageInfo }> {
    if (opts.mock || !opts.baseUrl) {
      yield* this.mockStream(opts.prompt);
      return;
    }

    const url = buildOpenAIChatUrl(opts.baseUrl);
    const messages: any[] = [];
    if (opts.system) messages.push({ role: 'system', content: opts.system });
    messages.push({ role: 'user', content: opts.prompt });

    let resp: Response;
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${opts.apiKey}`,
        },
        body: JSON.stringify({
          model: opts.model,
          messages,
          stream: true,
          stream_options: { include_usage: true },
        }),
      });
    } catch (e: any) {
      throw new Error(`LLM upstream unreachable: ${e?.message ?? e}`);
    }

    if (!resp.ok || !resp.body) {
      const txt = await resp.text().catch(() => '');
      throw new Error(`LLM upstream ${resp.status}: ${txt.slice(0, 300)}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let usage: UsageInfo | undefined;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith('data:')) continue;
        const payload = t.slice(5).trim();
        if (payload === '[DONE]') continue;
        try {
          const json = JSON.parse(payload);
          const delta = json.choices?.[0]?.delta?.content;
          if (typeof delta === 'string' && delta.length) {
            yield { delta };
          }
          if (json.usage) {
            usage = {
              prompt_tokens: json.usage.prompt_tokens,
              completion_tokens: json.usage.completion_tokens,
              total_tokens: json.usage.total_tokens,
            };
          }
        } catch {
          // 忽略 keep-alive / 不完整分片
        }
      }
    }
    if (usage) yield { usage };
  }

  private async *mockStream(
    prompt: string,
  ): AsyncGenerator<{ delta?: string; usage?: UsageInfo }> {
    const text = `[mock] 你说了: ${prompt}`;
    for (const ch of text) {
      yield { delta: ch };
      await new Promise((r) => setTimeout(r, 8));
    }
    yield {
      usage: {
        prompt_tokens: 10,
        completion_tokens: text.length,
        total_tokens: 10 + text.length,
      },
    };
  }
}
