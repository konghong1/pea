import { create } from 'zustand';

type Mode = 'light' | 'dark' | 'system';

function apply(mode: Mode) {
  const dark =
    mode === 'dark' ||
    (mode === 'system' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
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
