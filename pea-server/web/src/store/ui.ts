import { create } from 'zustand';

export type PageKey = 'home' | 'canvas' | 'account' | 'settings' | 'ecom' | 'tvtv' | 'arena';

interface UiState {
  active: PageKey;
  setActive: (p: PageKey) => void;
}

/** SPA 单实例页面状态：切换导航不卸载画布，保留编辑态 (FR-G1)。 */
export const useUi = create<UiState>((set) => ({
  active: 'canvas',
  setActive: (active) => set({ active }),
}));
