import { create } from 'zustand';

export type PageKey = 'home' | 'workspace' | 'canvas' | 'account' | 'settings' | 'ecom' | 'tvtv' | 'arena';

/** 账户中心 7 面板 (对齐 pea-canvas-v12.html `.acct-layout`)。 */
export type AccountPane =
  | 'profile'
  | 'general'
  | 'aiprov'
  | 'billing'
  | 'invite'
  | 'notif'
  | 'support';

interface UiState {
  active: PageKey;
  /** 账户中心当前面板，供 UserMenu 深层链接（如「AI Provider 设置」直达 aiprov）。 */
  accountPane: AccountPane;
  setActive: (p: PageKey) => void;
  setAccountPane: (pane: AccountPane) => void;
}

/** SPA 单实例页面状态：切换导航不卸载画布，保留编辑态 (FR-G1)。 */
export const useUi = create<UiState>((set) => ({
  active: 'workspace',
  accountPane: 'profile',
  setActive: (active) => set({ active }),
  setAccountPane: (accountPane) => set({ accountPane }),
}));
