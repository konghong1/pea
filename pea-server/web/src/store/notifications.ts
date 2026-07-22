import { create } from 'zustand';

export type NotifLevel = 'info' | 'success' | 'warning' | 'error';

export interface NotifItem {
  id: string;
  title: string;
  body: string;
  level: NotifLevel;
  ts: number;
  read: boolean;
}

interface NotifState {
  items: NotifItem[];
  unread: number;
  add: (n: Omit<NotifItem, 'id' | 'read'>) => void;
  markAllRead: () => void;
}

/** 通知中心状态 (FR-G6)：由 WS notification 事件驱动填充。 */
export const useNotif = create<NotifState>((set) => ({
  items: [],
  unread: 0,
  add: (n) => {
    const item: NotifItem = {
      ...n,
      id: `n_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      read: false,
    };
    set((s) => ({ items: [item, ...s.items].slice(0, 50), unread: s.unread + 1 }));
  },
  markAllRead: () => set((s) => ({ items: s.items.map((i) => ({ ...i, read: true })), unread: 0 })),
}));
