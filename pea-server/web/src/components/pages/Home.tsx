import { useUi } from '../../store/ui';

/**
 * 首页 (FR-pending) — 暂时留空，等待后续规划。
 *
 * 当前导航模型 (2026-07-24 起)：
 *   - `home`     → 进入本占位页（暂未开发内容）
 *   - `workspace` → 进入项目列表（ProjectList），点击/新建项目后跳转画布
 *   - `canvas`   → 进入画布编辑器
 *
 * 一旦后续有规划，按钮/快捷入口/欢迎语在此添加。
 */
export default function Home() {
  const setActive = useUi((s) => s.setActive);

  return (
    <div className="pea-page">
      <div className="projects-page">
        <div className="projects-subnav">
          <div className="projects-tabs" role="tablist">
            <button className="projects-tab active" aria-selected="true">
              主页
            </button>
          </div>
          <div className="projects-toolbar">
            <button
              className="projects-new-btn"
              onClick={() => setActive('workspace')}
              aria-label="进入工作空间"
            >
              前往工作空间
            </button>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            color: 'var(--pea-text-muted)',
            textAlign: 'center',
            gap: 12,
          }}
        >
          <div style={{ fontSize: 56, opacity: 0.35 }} aria-hidden>
            🌱
          </div>
          <div style={{ fontSize: 16, color: 'var(--pea-text-primary)', fontWeight: 600 }}>
            主页规划中
          </div>
          <div style={{ fontSize: 13 }}>
            内容暂未上线。你可以先到「工作空间」开始创作。
          </div>
        </div>
      </div>
    </div>
  );
}