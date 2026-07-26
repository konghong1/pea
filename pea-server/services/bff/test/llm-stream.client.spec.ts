import { buildOpenAIChatUrl } from '../src/modules/chat/llm-stream.client';

/**
 * 回归测试: 文本节点聊天 URL 归一化 (T-CHAT-URL)。
 *
 * 复现并锁定 bug: 当 provider.base_url 已含 /v1 (本项目 OpenAI 兼容网关的存储约定,
 * 与 orchestrator._api_base / providers.normalizeModelsUrl 同一约定) 时,
 * 旧实现 `baseUrl + '/v1/chat/completions'` 会拼出 /v1/v1/chat/completions -> 上游 404。
 * 修复后无论 base_url 是否带 /v1, 最终都应为单一的 /v1/chat/completions。
 */
describe('buildOpenAIChatUrl', () => {
  it('不带 /v1 时补上 /v1', () => {
    expect(buildOpenAIChatUrl('https://gateway')).toBe(
      'https://gateway/v1/chat/completions',
    );
  });

  it('带尾部斜杠时不重复', () => {
    expect(buildOpenAIChatUrl('https://gateway/')).toBe(
      'https://gateway/v1/chat/completions',
    );
  });

  it('已含 /v1 (无尾部斜杠) 不叠加 -> 锁定回归', () => {
    const url = buildOpenAIChatUrl('https://gateway/v1');
    expect(url).toBe('https://gateway/v1/chat/completions');
    expect(url).not.toContain('/v1/v1');
  });

  it('已含 /v1/ (带尾部斜杠) 不叠加', () => {
    const url = buildOpenAIChatUrl('https://gateway/v1/');
    expect(url).toBe('https://gateway/v1/chat/completions');
    expect(url).not.toContain('/v1/v1');
  });

  it('任意情况都不应出现 /v1/v1', () => {
    const samples = [
      'https://api.openai.com',
      'https://api.openai.com/',
      'https://gateway.example.com/v1',
      'https://gateway.example.com/v1/',
      'http://host.docker.internal:9199/v1',
    ];
    for (const s of samples) {
      const url = buildOpenAIChatUrl(s);
      expect(url).not.toContain('/v1/v1');
      expect(url.endsWith('/v1/chat/completions')).toBe(true);
    }
  });
});
