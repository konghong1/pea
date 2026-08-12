import { useEffect, useState } from 'react';
import { estimateCost, listAvailableModels } from '../api/catalog';
import type { AvailableModel } from '../api/catalog';
import { useCanvas } from '../store/canvas';
import { toast } from '../store/toast';

export interface AngleCubeParams {
  rotation: number;
  tilt: number;
  zoom: number;
  wideAngle: boolean;
  modelId: string;
}

interface Props {
  nodeId: string;
  url: string;
  onClose: () => void;
  onConfirm: (params: AngleCubeParams) => void;
}

/**
 * 角度魔方面板 — 内嵌模式（渲染到节点编辑锚点内，替代 NodeChatPrompt 输入框）。
 *
 * 关键行为：
 * - 渲染到 .pea-node-editor-anchor 内，与节点选中态绑定；
 * - 面板「是否展示」取决于节点是否被选中：节点取消选中时编辑框收起（不展示），
 *   但 cubeOpenNodeId 状态保留，再次选中同一节点仍恢复角度魔方面板；
 * - 只有点击右上角 × 按钮才真正关闭（清空 cubeOpenNodeId），关闭后再次选中节点回退为提示词框；
 * - 不响应点击外部 / Escape 关闭，避免误关。
 */
export default function AngleCubeOverlay({ nodeId, url, onClose, onConfirm }: Props) {
  const node = useCanvas((s) => s.nodes.find((n) => n.id === nodeId));
  const metaModelId = (node?.data.meta?.modelId as string) || '';

  const [rotation, setRotation] = useState(-30);
  const [tilt, setTilt] = useState(23);
  const [zoom, setZoom] = useState(0);
  const [wideAngle, setWideAngle] = useState(false);

  const [model, setModel] = useState<AvailableModel | null>(null);
  const [est, setEst] = useState<{ cost: number; allowed: boolean; minPlanLevel: number } | null>(null);
  const [loading, setLoading] = useState(false);

  // 加载可用模型 + 估算消耗
  useEffect(() => {
    let cancelled = false;
    listAvailableModels('image')
      .then((list) => {
        if (cancelled) return;
        const pick =
          list.find((m) => m.id === metaModelId) ||
          list.find((m) => m.isDefault) ||
          list[0] ||
          null;
        setModel(pick);
        if (pick) {
          estimateCost(pick.id, { n: 1 })
            .then((r) => {
              if (cancelled) setEst({ cost: r.cost, allowed: r.allowed, minPlanLevel: r.minPlanLevel });
            })
            .catch(() => {
              if (cancelled) setEst(null);
            });
        }
      })
      .catch(() => {
        if (cancelled) setModel(null);
      });
    return () => {
      cancelled = true;
    };
  }, [metaModelId]);

  const reset = () => {
    setRotation(-30);
    setTilt(23);
    setZoom(0);
    setWideAngle(false);
  };

  const canSend = Boolean(model && est?.allowed);

  const handleSend = () => {
    if (!model || !est?.allowed) return;
    setLoading(true);
    onConfirm({ rotation, tilt, zoom, wideAngle, modelId: model.id });
  };

  if (typeof document === 'undefined') return null;

  return (
    <div
      className="pea-angle-cube-panel"
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      onWheel={(e) => e.stopPropagation()}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
    >
      <div className="pea-angle-cube-header">
        <span className="pea-angle-cube-title">拖拽方块调整角度</span>
        <button
          type="button"
          className="pea-angle-cube-close"
          onClick={onClose}
          aria-label="关闭"
          title="关闭"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M18 6L6 18" />
            <path d="M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="pea-angle-cube-body">
        <div className="pea-angle-cube-preview">
          <div
            className="pea-angle-cube-preview-stage"
            style={{ perspective: '800px' }}
          >
            {(() => {
              /* 等比缩放基础尺寸（不用 CSS scale，避免 translateZ 被同比例放大导致透视变形）
               * 紧凑面板：预览框 160px，左下角留 28px 图标区；
               *   zoom=0  → 小立方体，约 46px（占 160px 框的 ~29%）
               *   zoom=10 → 大立方体，正方面 70px × 1.37 ≈ 96px 投影（占框 ~60%，不会碰到左下角重置按钮）
               * 立方体固定旋转态(rotation=-30/tilt=23)，旋转后投影≈正方面的1.37倍 */
              const baseSize = 46;
              const maxSize = 70;
              const cubeSize = Math.round(baseSize + (maxSize - baseSize) * (zoom / 10));
              const halfZ = Math.round(cubeSize / 2);
              return (
              <div
                className="pea-angle-cube-preview-cube"
                style={{
                  transform: `rotateX(${tilt}deg) rotateY(${-rotation}deg)`,
                  '--cube-size': `${cubeSize}px`,
                  '--cube-half-z': `${halfZ}px`,
                } as React.CSSProperties}
              >
              {/* 正面 — 贴图 */}
              <div className="pea-cube-face pea-cube-front">
                <img src={url} alt="角度预览" draggable={false} />
              </div>
              {/* 背面 */}
              <div className="pea-cube-face pea-cube-back" />
              {/* 右侧 */}
              <div className="pea-cube-face pea-cube-right" />
              {/* 左侧 */}
              <div className="pea-cube-face pea-cube-left" />
              {/* 顶面 */}
              <div className="pea-cube-face pea-cube-top" />
              {/* 底面 */}
              <div className="pea-cube-face pea-cube-bottom" />
            </div>
              );
            })()}
          </div>

          {/* 重置按钮：仅图标，悬浮在预览区左下角，避免与最大立方体重叠 */}
          <button
            type="button"
            className="pea-angle-cube-reset-icon"
            onClick={reset}
            title="重置角度"
            aria-label="重置角度"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
          </button>
        </div>

        <div className="pea-angle-cube-controls">
          <SliderRow
            label="旋转"
            value={rotation}
            min={-90}
            max={90}
            step={1}
            suffix="°"
            onChange={setRotation}
          />
          <SliderRow
            label="倾斜"
            value={tilt}
            min={-45}
            max={45}
            step={1}
            suffix="°"
            onChange={setTilt}
          />
          <SliderRow
            label="缩放"
            value={zoom}
            min={0}
            max={10}
            step={1}
            suffix=""
            onChange={setZoom}
          />
          <div className="pea-angle-cube-row">
            <span className="pea-angle-cube-label">广角镜头</span>
            <span />
            <button
              type="button"
              role="switch"
              aria-checked={wideAngle}
              className={`pea-angle-cube-toggle ${wideAngle ? 'on' : ''}`}
              onClick={() => setWideAngle((v) => !v)}
            >
              <span className="pea-angle-cube-toggle-knob" />
            </button>
          </div>

          {/* 发送胶囊：齿轮 + 短横线 + 灰色圆形箭头按钮（与截图一致），放在参数区底部 */}
          <div className="pea-angle-cube-send-row">
            <div className="pea-angle-cube-send-pill">
              <span
                className="pea-angle-cube-cost"
                title={est ? `预计消耗 ${Math.round(est.cost)} Tapies` : '当前模型不可用'}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                <span className="pea-angle-cube-cost-sep" aria-hidden>—</span>
              </span>
              <button
                type="button"
                className="pea-angle-cube-send"
                onClick={handleSend}
                disabled={!canSend || loading}
                aria-label="发送生成"
                title={est?.allowed ? '发送生成' : '当前模型不可用'}
              >
                {loading ? (
                  <span className="pea-angle-cube-send-spinner" />
                ) : (
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M12 19V5" />
                    <path d="M5 12l7-7 7 7" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix: string;
  onChange: (v: number) => void;
}) {
  const fmt = `${value > 0 && suffix ? '+' : ''}${value}${suffix}`;
  // 当前值在 range 中的位置百分比（0~100）
  const progress = ((value - min) / (max - min)) * 100;
  // 填充逻辑：
  //   - 对称范围（含负值，如旋转 -45~+45）：以中心(50%)为原点双向填充
  //   - 非负范围（如缩放 0~10）：标准左到右填充
  const isSymmetric = min < 0 && max > 0;
  const fromPct = isSymmetric ? (value >= 0 ? 50 : progress) : 0;
  const toPct = isSymmetric ? (value >= 0 ? progress : 50) : progress;
  return (
    <div className="pea-angle-cube-row">
      <span className="pea-angle-cube-label">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="pea-angle-cube-slider"
        style={{ '--from': `${fromPct}%`, '--to': `${toPct}%` } as React.CSSProperties}
        onPointerDown={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      />
      <span className="pea-angle-cube-value">{fmt}</span>
    </div>
  );
}
