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

/** 按 level 自适应的默认 duration —— 错误消息更长（往往是技术摘要），
 *  需要更长可读时间；warn 居中；success/info 短闪即可。
 *  调用方可显式传第 3 参覆盖 (e.g. 业务方希望更长 / 更短)。
 */
const DEFAULT_DURATION_MS: Record<ToastLevel, number> = {
  error: 4500,
  warning: 3000,
  success: 1800,
  info: 1800,
};

/**
 * 全局轻提示 (FR-G4)：默认按 level 自适应持续时间、支持堆叠不重叠。
 * 用 window 计时器驱动，避免依赖 antd message 的不可控样式。
 */
export const useToast = create<ToastState>((set, get) => ({
  items: [],
  push: (level, content, duration) => {
    const ms = duration ?? DEFAULT_DURATION_MS[level];
    const id = `t_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    set((s) => ({ items: [...s.items, { id, level, content }] }));
    window.setTimeout(() => get().dismiss(id), ms);
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
  info: (c: string, duration?: number) => useToast.getState().push('info', c, duration),
  success: (c: string, duration?: number) => useToast.getState().push('success', c, duration),
  warning: (c: string, duration?: number) => useToast.getState().push('warning', c, duration),
  error: (c: string, duration?: number) => useToast.getState().push('error', c, duration),
};
