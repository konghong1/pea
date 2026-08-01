import axios from 'axios';

/**
 * BFF 基址：统一以 /api 为前缀。
 *
 * - 开发期：vite proxy 把 /api/* 转发到 :4100。
 * - 生产：nginx location /api/ 把 /api 剥离后转发到 BFF
 *   (BFF 已在 main.ts 注册 setGlobalPrefix('api'), 所有 controller 自动带 /api 前缀)。
 *
 * 这样以后新增任何接口都自动落在 /api/* 下, 不用再维护 nginx 白名单。
 */
export const api = axios.create({
  baseURL: '/api',
});

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('pea_token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('pea_token');
      localStorage.removeItem('pea_user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

/**
 * 把接口响应安全地归一化为数组。
 *
 * 兜底场景：当某个 API 前缀未加入 nginx / vite 代理白名单时，该路由会落到 SPA
 * 回退、返回整页 index.html（一个字符串）。若前端直接把这段 HTML 当数组用
 * （.map / antd Table 的 .some），会抛 "x.some is not a function" 整树崩溃白屏。
 * 这里强制归一化为数组，从前端彻底杜绝此类白屏。
 */
export function asArray<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}
