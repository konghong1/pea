import { create } from 'zustand';

export type ToastLevel = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  level: ToastLevel;
  content: string;
  leaving?: boolean;
}

interface ToastState {
  items: ToastItem[];
  push: (level: ToastLevel, content: string, duration?: number) => void;
  dismiss: (id: string) => void;
}

/**
 * 全局轻提示 (FR-G4)：默认 1.8s 自动消失、支持堆叠不重叠。
 * 用 window 计时器驱动，避免依赖 antd message 的不可控样式。
 */
export const useToast = create<ToastState>((set, get) => ({
  items: [],
  push: (level, content, duration = 1800) => {
    const id = `t_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    set((s) => ({ items: [...s.items, { id, level, content }] }));
    window.setTimeout(() => get().dismiss(id), duration);
  },
  dismiss: (id) => {
    set((s) => ({ items: s.items.map((t) => (t.id === id ? { ...t, leaving: true } : t)) }));
    window.setTimeout(() => {
      set((s) => ({ items: s.items.filter((t) => t.id !== id) }));
    }, 200);
  },
}));

/** 便捷调用入口，组件外也可直接用。 */
export const toast = {
  info: (c: string) => useToast.getState().push('info', c),
  success: (c: string) => useToast.getState().push('success', c),
  warning: (c: string) => useToast.getState().push('warning', c),
  error: (c: string) => useToast.getState().push('error', c),
};
