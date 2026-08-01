import { create } from 'zustand';
import { api } from '../api/client';
import { getMe } from '../api/catalog';
import { clearFileCache } from '../api/files';

export interface AuthUser {
  id: number;
  email: string;
  displayName: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  balance: number;
  /** 是否管理员 (来自 /users/me, 权限单一真源在服务端, 前端仅用于显示入口)。 */
  isAdmin: boolean;
  /** 名义权益等级 (可能已过期)。 */
  planLevel: number;
  /** 生效权益等级 (过期回落 0), 用于模型解锁展示。 */
  effectivePlanLevel: number;
  planExpiresAt: string | null;
  setAuth: (token: string, user: AuthUser) => void;
  setBalance: (b: number) => void;
  /**
   * 轻量拉取 /billing/balance 同步余额。
   * 用于生成提交/完成/退款等余额必然变动的时刻做兜底刷新——
   * WS 的 balance.changed 事件是「快路径」，此接口是「慢路径保底」，两者幂等。
   */
  refreshBalance: () => Promise<void>;
  /** 拉取 /users/me 同步余额 + 角色 + 权益。返回是否成功。 */
  refreshMe: () => Promise<boolean>;
  /** 静默续期：用当前有效 token 换发新 token（延长会话）。失败返回 false（不动 user）。 */
  refreshToken: () => Promise<boolean>;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem('pea_token'),
  user: JSON.parse(localStorage.getItem('pea_user') ?? 'null'),
  balance: 0,
  isAdmin: false,
  planLevel: 0,
  effectivePlanLevel: 0,
  planExpiresAt: null,
  setAuth: (token, user) => {
    localStorage.setItem('pea_token', token);
    localStorage.setItem('pea_user', JSON.stringify(user));
    set({ token, user });
  },
  setBalance: (balance) => set({ balance }),
  refreshBalance: async () => {
    try {
      const { data } = await api.get<{ balance: number }>('/billing/balance');
      if (typeof data?.balance === 'number') set({ balance: data.balance });
    } catch {
      /* 网络抖动时静默失败：WS 事件或下一次刷新会补上，不打扰用户 */
    }
  },
  refreshMe: async () => {
    try {
      const me = await getMe();
      set({
        balance: me.balance ?? 0,
        isAdmin: !!me.isAdmin,
        planLevel: me.planLevel ?? 0,
        effectivePlanLevel: me.effectivePlanLevel ?? 0,
        planExpiresAt: me.planExpiresAt ?? null,
        // 同步展示名 (注册后可能变更), 但不覆盖 token
        user: {
          id: me.id,
          email: me.email,
          displayName: me.displayName || me.email?.split('@')[0] || '用户',
        },
      });
      return true;
    } catch {
      return false;
    }
  },
  refreshToken: async () => {
    try {
      const { data } = await api.post<{ token: string }>('/auth/refresh');
      if (data?.token) {
        localStorage.setItem('pea_token', data.token);
        set({ token: data.token });
        return true;
      }
    } catch {
      /* token 失效或网络异常：返回 false，由 401 拦截器决定是否登出 */
    }
    return false;
  },
  logout: () => {
    clearFileCache();
    localStorage.removeItem('pea_token');
    localStorage.removeItem('pea_user');
    set({
      token: null,
      user: null,
      balance: 0,
      isAdmin: false,
      planLevel: 0,
      effectivePlanLevel: 0,
      planExpiresAt: null,
    });
  },
}));
