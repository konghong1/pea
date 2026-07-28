import { CSSProperties } from 'react';

/**
 * 科技感加载动画 - 中心圆环 + 发光核心
 *
 * 设计原则：节点外壳(.pea-node.is-generating)负责"HUD 框"(四角色 + 纵向扫描 + 底部光带)，
 * 让用户感觉整个动画"在节点框内"流动；本组件只负责中心圆环 + 文字 label。
 *
 * 跟随主题色 currentColor 自动适配深/浅主题；带 prefers-reduced-motion 降级。
 */
export default function TechLoader({
  size = 56,
  label,
  className,
  style,
}: {
  size?: number;
  label?: string;
  className?: string;
  style?: CSSProperties;
}) {
  const stroke = 2;
  const rOuter = (size - stroke) / 2 - 2;
  const rMid = rOuter - 6;
  const rInner = rMid - 6;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * rOuter;

  return (
    <div
      className={`tech-loader${className ? ` ${className}` : ''}`}
      style={{ width: size, ...style }}
      role="status"
      aria-live="polite"
    >
      <svg
        className="tech-loader__svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden
      >
        <defs>
          <radialGradient id="tech-loader-core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="1" />
            <stop offset="70%" stopColor="currentColor" stopOpacity="0.35" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle
          className="tech-loader__ring tech-loader__ring--outer"
          cx={cx}
          cy={cy}
          r={rOuter}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference * 0.18} ${circumference * 0.12}`}
          opacity={0.55}
        />

        <circle
          className="tech-loader__ring tech-loader__ring--mid"
          cx={cx}
          cy={cy}
          r={rMid}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference * 0.1} ${circumference * 0.16}`}
          opacity={0.7}
        />

        <circle
          className="tech-loader__ring tech-loader__ring--arc"
          cx={cx}
          cy={cy}
          r={rInner}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke + 0.5}
          strokeLinecap="round"
          strokeDasharray={`${circumference * 0.28} ${circumference}`}
        />

        <circle
          className="tech-loader__core"
          cx={cx}
          cy={cy}
          r={rInner * 0.42}
          fill="url(#tech-loader-core)"
        />
      </svg>

      {label && <span className="tech-loader__label">{label}</span>}
    </div>
  );
}
