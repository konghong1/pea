import { api } from './client';
import type { PromptMediaType, PromptRewriteOptions, PromptResult } from '../lib/promptRewriter';

/**
 * 提示词改写 API 客户端
 *
 * 独立于 Agent 聊天接口，走专用 /prompts/rewrite 端点
 */

export interface PromptRewriteRequest {
  /** 用户输入的原始文本 */
  input: string;
  /** 目标媒体类型 */
  mediaType?: PromptMediaType;
  /** 风格模板 */
  style?: string;
  /** 语言偏好 */
  language?: 'zh' | 'en';
  /** 是否自动增强细节 */
  autoEnhance?: boolean;
}

export interface PromptRewriteResponse {
  code: number;
  data: PromptResult;
  message: string;
}

/**
 * 调用后端改写提示词
 *
 * @param input - 用户输入的简短描述（如"女孩"、"赛博朋克城市"）
 * @param options - 改写选项
 * @returns 结构化改写结果
 */
export async function rewritePrompt(
  input: string,
  options?: Partial<PromptRewriteRequest>,
): Promise<PromptResult> {
  const res = await api.post<PromptRewriteResponse>(
    '/prompts/rewrite',
    { ...options, input: input.trim() },
  );

  if (res.data.code !== 0) {
    throw new Error(res.data.message || '提示词改写失败');
  }

  return res.data.data;
}

/**
 * 快速改写：仅传入输入文本，使用默认选项
 */
export async function quickRewrite(input: string): Promise<string> {
  const result = await rewritePrompt(input);
  return result.rewritten;
}

/**
 * 图片提示词改写
 */
export async function rewriteImagePrompt(input: string, style?: string): Promise<string> {
  const result = await rewritePrompt(input, { mediaType: 'image', style });
  return result.rewritten;
}

/**
 * 视频提示词改写
 */
export async function rewriteVideoPrompt(input: string, style?: string): Promise<string> {
  const result = await rewritePrompt(input, { mediaType: 'video', style });
  return result.rewritten;
}
