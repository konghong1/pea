import { create } from 'zustand';

export type PageKey =
  | 'home'
  | 'workspace'
  | 'canvas'
  | 'account'
  | 'settings'
  | 'ecom'
  | 'tvtv'
  | 'arena'
  | 'plans'
  | 'admin';

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
  /** 导航历史栈 (末位为当前页)，供浏览器回退还原上一页。 */
  _stack: PageKey[];
  /** 用户侧导航：切换页面并压入浏览器历史（支持浏览器回退）。 */
  setActive: (p: PageKey) => void;
  /** 内部：仅改 active，不压历史（供 popstate 回退使用，避免循环压栈）。 */
  _restore: (p: PageKey) => void;
  setAccountPane: (pane: AccountPane) => void;
}

/** SPA 单实例页面状态：切换导航不卸载画布，保留编辑态 (FR-G1)。 */
export const useUi = create<UiState>((set, get) => ({
  active: 'workspace',
  accountPane: 'profile',
  _stack: ['workspace'],
  setActive: (p) => {
    const { active, _stack } = get();
    if (p === active) return; // 同页不重复压栈
    const stack = [..._stack, p];
    window.history.pushState({ pea: stack.length - 1 }, '');
    set({ active: p, _stack: stack });
  },
  _restore: (p) => set({ active: p }),
  setAccountPane: (accountPane) => set({ accountPane }),
}));

/**
 * 安装浏览器历史回退支持 (Q3)。
 * - 标记根 entry 为 {pea:0}，使首次回退落在 workspace 而非离开应用。
 * - 监听 popstate：浏览器回退/前进时，按 state.pea 索引还原对应历史页。
 * 幂等（重复安装只注册一次监听）。
 */
let _popInstalled = false;
export function installPopState() {
  if (_popInstalled) return;
  _popInstalled = true;
  // 标记当前（根）历史 entry，避免首次回退直接离开应用。
  window.history.replaceState({ pea: 0 }, '');
  window.addEventListener('popstate', (e: PopStateEvent) => {
    const idx = e.state && typeof e.state.pea === 'number' ? e.state.pea : 0;
    const { _stack, _restore } = useUi.getState();
    const pos = Math.max(0, Math.min(idx, _stack.length - 1));
    _restore(_stack[pos] ?? 'workspace');
    useUi.setState({ _stack: _stack.slice(0, pos + 1) });
  });
}
