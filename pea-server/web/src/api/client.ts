import axios from 'axios';

/** BFF 基址: 开发期由 vite proxy 转发到 :4000, 生产可改为网关地址. */
export const api = axios.create({
  baseURL: '/',
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
