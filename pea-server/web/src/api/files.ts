import { api } from './client';

const fileCache = new Map<string, string>();

/**
 * 获取上传的私有资源 URL。
 * 由于 <img src> 不携带 Authorization header，必须用 fetch + blob URL。
 * 结果会缓存在内存中，避免重复请求。
 */
export async function getFileUrl(key: string): Promise<string> {
  if (fileCache.has(key)) {
    return fileCache.get(key)!;
  }
  try {
    const resp = await api.get(`/files/download?key=${encodeURIComponent(key)}`, {
      responseType: 'blob',
    });
    const url = URL.createObjectURL(resp.data);
    fileCache.set(key, url);
    return url;
  } catch {
    return '';
  }
}

/**
 * 获取可对外传输/外链访问的签名 URL（用于把用户私有上传图作为参考图发给外部模型）。
 * 与 getFileUrl (blob, 仅浏览器内显示) 不同，这里返回真实 http(s) 签名地址，
 * 模型侧 (Agnes 等) 才能真实下载。有效期 1h，足够单次生成。结果按 key 缓存。
 */
const presignCache = new Map<string, string>();

export async function getPresignedUrl(key: string): Promise<string> {
  if (!key) return '';
  if (presignCache.has(key)) return presignCache.get(key)!;
  try {
    const { data } = await api.get(`/files/url?key=${encodeURIComponent(key)}`);
    const url: string = data?.downloadUrl || '';
    if (url && (url.startsWith('http') || url.startsWith('data:'))) {
      presignCache.set(key, url);
      return url;
    }
    return '';
  } catch {
    return '';
  }
}

/** 清理缓存（登出时调用） */
export function clearFileCache() {
  fileCache.forEach((url) => URL.revokeObjectURL(url));
  fileCache.clear();
}
