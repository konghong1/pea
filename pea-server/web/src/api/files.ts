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

/** 清理缓存（登出时调用） */
export function clearFileCache() {
  fileCache.forEach((url) => URL.revokeObjectURL(url));
  fileCache.clear();
}
