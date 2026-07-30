import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useUi } from '../store/ui';
import { useCanvas } from '../store/canvas';

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * 画布级错误边界（防御性兜底）。
 *
 * 任何画布子组件渲染期抛错（如节点组件崩溃、状态不一致）都会被捕获，
 * 显示可恢复的兜底界面，而不是让整页 React 树卸载成「白屏」（需求3：
 * 避免一键操作直接白屏、刷新也回不去初始状态）。
 *
 * 兜底提供两个出口：
 *  - 「刷新页面」：重新加载（适用于偶发错误 / 需重新拉取最新画布）。
 *  - 「返回工作空间」：清空本地选中态并切回工作空间，避开崩溃画布。
 */
export default class CanvasErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 仅记录，不向上抛出，避免冒泡成整页崩溃。
    console.error('[CanvasErrorBoundary] caught render error:', error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleBackToWorkspace = () => {
    try {
      // 清空本地选中态，避免崩溃态被再次渲染
      useCanvas.getState().clearSelection();
    } catch {
      /* ignore */
    }
    useUi.getState().setActive('workspace');
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <div className="pea-canvas-error-boundary">
          <div className="pea-eb-card">
            <div className="pea-eb-icon" aria-hidden>⚠️</div>
            <div className="pea-eb-title">画布出现了一点问题</div>
            <div className="pea-eb-desc">
              渲染过程中发生异常，已为你拦截白屏。你可以刷新重试，或返回工作空间重新打开项目。
            </div>
            <pre className="pea-eb-detail">{String(this.state.error?.message || this.state.error).slice(0, 240)}</pre>
            <div className="pea-eb-actions">
              <button type="button" className="pea-eb-btn primary" onClick={this.handleReload}>
                刷新页面
              </button>
              <button type="button" className="pea-eb-btn" onClick={this.handleBackToWorkspace}>
                返回工作空间
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
