import { create } from 'zustand';

type Mode = 'light' | 'dark' | 'system';

function systemPrefersDark() {
  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function apply(mode: Mode) {
  const dark = mode === 'dark' || (mode === 'system' && systemPrefersDark());
  document.documentElement.classList.toggle('dark', dark);
  localStorage.setItem('pea_theme', mode);
}

interface ThemeState {
  mode: Mode;
  setMode: (m: Mode) => void;
  init: () => void;
}

export const useTheme = create<ThemeState>((set) => ({
  mode: (localStorage.getItem('pea_theme') as Mode) ?? 'system',
  setMode: (mode) => {
    apply(mode);
    set({ mode });
  },
  init: () => {
    const m = (localStorage.getItem('pea_theme') as Mode) ?? 'system';
    apply(m);
    set({ mode: m });
  },
}));

// 监听系统配色变化，使"跟随系统"实时生效。
// 画布内表面由 creatorDesign 接管（body[data-surface] 存在时跳过），避免覆盖创作端外观。
if (typeof window !== 'undefined') {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', () => {
    const mode = (localStorage.getItem('pea_theme') as Mode) ?? 'system';
    if (mode !== 'system') return;
    if (document.body.dataset.surface) return;
    apply('system');
  });
}
