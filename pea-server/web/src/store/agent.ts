import { create } from 'zustand';

export type ChatRole = 'user' | 'assistant';
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  ts: number;
}

export type AgentModel = 'fast' | 'standard' | 'pro';

interface AgentState {
  open: boolean;
  model: AgentModel;
  messages: ChatMessage[];
  typing: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
  setModel: (m: AgentModel) => void;
  push: (role: ChatRole, content: string) => void;
  setTyping: (v: boolean) => void;
  reset: () => void;
}

let mid = 1;
const nextMsgId = () => `m${mid++}`;

export const useAgent = create<AgentState>((set, get) => ({
  open: false,
  model: 'standard',
  messages: [],
  typing: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set({ open: !get().open }),
  setModel: (m) => set({ model: m }),
  push: (role, content) =>
    set({ messages: [...get().messages, { id: nextMsgId(), role, content, ts: Date.now() }] }),
  setTyping: (v) => set({ typing: v }),
  reset: () =>
    set({
      messages: [
        {
          id: nextMsgId(),
          role: 'assistant',
          content: '对话已清空。需要我做什么？',
          ts: Date.now(),
        },
      ],
    }),
}));
