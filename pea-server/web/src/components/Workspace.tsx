import { useWs } from '../hooks/useWs';
import TopNav from './TopNav';
import CanvasEditor from './CanvasEditor';
import AgentPanel from './AgentPanel';
import Home from './pages/Home';
import Ecom from './pages/Ecom';
import TapTV from './pages/TapTV';
import Arena from './pages/Arena';
import Account from './pages/Account';
import { useUi } from '../store/ui';

/**
 * 工作区布局 (FR-G1)：SPA 单实例。
 * 画布常驻（仅隐藏），切换导航不卸载，保留编辑/滚动态。
 */
export default function Workspace() {
  useWs();
  const active = useUi((s) => s.active);

  return (
    <div className="flex h-screen flex-col">
      <TopNav />
      <div className="relative flex-1 overflow-hidden">
        {/* 画布常驻，保证编辑态不丢 */}
        <div className={active === 'canvas' ? 'absolute inset-0' : 'absolute inset-0 invisible'}>
          <CanvasEditor />
        </div>
        {/* 副驾驶聊天侧边栏：固定在最右 380px，跨画布/页面常驻 */}
        <AgentPanel />
        {active !== 'canvas' && (
          <div className="absolute inset-0 z-20 bg-white dark:bg-[#0a0a0a]">
            {active === 'home' && <Home />}
            {(active === 'account' || active === 'settings') && <Account />}
            {active === 'ecom' && <Ecom />}
            {active === 'tvtv' && <TapTV />}
            {active === 'arena' && <Arena />}
          </div>
        )}
      </div>
    </div>
  );
}
