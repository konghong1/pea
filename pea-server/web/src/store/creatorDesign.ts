import { create } from 'zustand';

/**
 * 创作端（用户端）设计主题：在 Runway（电影感暗色）与 Figma（明亮创作）之间切换。
 * 与全局 light/dark（precision 后台）解耦 —— 创作端外观完全由该选择决定，
 * Runway 永远暗、Figma 永远亮，不受系统/后台主题影响。
 *
 * 持久化键：pea_creator_design（刷新后原样恢复）。
 */
export type CreatorDesign = 'runway' | 'figma';

/** 创作端设计 → 画布容器 data-surface 值 */
export const CREATOR_SURFACE: Record<CreatorDesign, 'cinematic' | 'figma'> = {
  runway: 'cinematic',
  figma: 'figma',
};

const STORAGE_KEY = 'pea_creator_design';

function read(): CreatorDesign {
  const v = localStorage.getItem(STORAGE_KEY);
  return v === 'figma' ? 'figma' : 'runway';
}

interface CreatorDesignState {
  design: CreatorDesign;
  setDesign: (d: CreatorDesign) => void;
  init: () => void;
}

export const useCreatorDesign = create<CreatorDesignState>((set) => ({
  design: read(),
  setDesign: (design) => {
    localStorage.setItem(STORAGE_KEY, design);
    set({ design });
  },
  init: () => {
    const d = read();
    set({ design: d });
  },
}));
