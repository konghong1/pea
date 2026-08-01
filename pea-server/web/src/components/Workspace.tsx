import { useEffect, useRef } from 'react';
import { useWs } from '../hooks/useWs';
import { useAuth } from '../store/auth';
import TopNav from './TopNav';
import CanvasEditor from './CanvasEditor';
import AgentPanel from './AgentPanel';
import ProjectList from './ProjectList';
import Home from './pages/Home';
import Ecom from './pages/Ecom';
import TapTV from './pages/TapTV';
import Arena from './pages/Arena';
import Account from './pages/Account';
import Plans from './pages/Plans';
import Admin from './pages/Admin';
import { useUi } from '../store/ui';

/**
 * 工作区布局 (FR-G1)：SPA 单实例。
 *
 * 视图模型（2026-07-24 重构）：
 *   - `home`        → 首页占位（暂时留空，等待规划）
 *   - `workspace`   → 项目列表（ProjectList）；点击或新建项目后跳画布
 *   - `canvas`      → 画布编辑器（隐藏 TopNav，画布自带头部）
 *   - 其他 (account/settings/ecom/tvtv/arena) → 各自面板
 *
 * 画布模式下隐藏顶部 TopNav — 画布自带头部（标题 + 下拉 + 操作），避免双层导航。
 */
export default function Workspace() {
  useWs();
  const active = useUi((s) => s.active);
  const { refreshMe, refreshToken } = useAuth();

  // 静默续期（必须在常驻的 Workspace 里，而非 TopNav）：
  // TopNav 在画布模式下不挂载，若续期放那，画布里登录态会过期被踢。
  // 这里启动即续期 + 每 30 分钟保活，覆盖所有页面（含画布）。
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    refreshMe().then((ok) => { if (ok) refreshToken(); });
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      if (useAuth.getState().token) refreshToken();
    }, 30 * 60 * 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [refreshMe, refreshToken]);

  // 余额最终保底轮询：WS 事件（快路径）+ 生成/退款时的 syncBalance（慢路径）之外的第三道保险。
  // 仅在页面可见时发起，后台标签页不空跑；2 分钟一次对服务端几乎无压力，
  // 但能彻底消除「余额永远停在旧值，非得手动点一下」的体验问题。
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState !== 'visible') return;
      if (!useAuth.getState().token) return;
      void useAuth.getState().refreshBalance();
    };
    const id = setInterval(tick, 2 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const inCanvas = active === 'canvas';

  return (
    <div className="flex h-screen flex-col">
      {!inCanvas && <TopNav />}
      {/* overflow-visible：画布节点（尤其靠近底部/边缘的）必须完整可见，
          不能被此容器裁切（否则连线时目标节点"只露出一点"甚至看不到）。
          页面面板本身是 absolute inset-0 精确贴合，不会因此溢出。 */}
      <div className="relative flex-1 overflow-visible">
        {/* 画布：仅在 canvas 模式挂载（点击项目 / 新建项目后跳转） */}
        {inCanvas && (
          <div className="absolute inset-0">
            <CanvasEditor />
          </div>
        )}
        {/* 副驾驶聊天侧边栏：固定在最右 380px，跨画布/页面常驻 */}
        <AgentPanel />
        {!inCanvas && (
          <div className="absolute inset-0 z-20 bg-white dark:bg-[#0a0a0a]">
            {active === 'home' && <Home />}
            {active === 'workspace' && <ProjectList />}
            {(active === 'account' || active === 'settings') && <Account />}
            {active === 'ecom' && <Ecom />}
            {active === 'tvtv' && <TapTV />}
            {active === 'arena' && <Arena />}
            {active === 'plans' && <Plans />}
            {active === 'admin' && <Admin />}
          </div>
        )}
      </div>
    </div>
  );
}