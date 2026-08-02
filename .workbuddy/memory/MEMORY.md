# pea Creative OS — 长期记忆

## 设计改进记录 (2026-08-02)

### 节点生成按钮重新设计（第三版：科技感粒子翻动）
- **问题**:旧版图标丑陋/简单,与"生成"语义不相关;数字中间有"T"多余
- **方案**:一体化 `.pe-launcher` → 消耗区仅留数字(微光) + 触发区「生成核心」(中心火花+4轨道粒子翻动)
- **设计亮点**:
  - 中心 4 角星火花核心 (象征"创造/生成")
  - 4 颗粒子沿轨道旋转+自身缩放翻动 (错峰动画)
  - hover 加速粒子流动 (orbit 3.2s→1.6s)
  - 火花脉冲呼吸 (scale 1→1.18)
  - 去掉 T 标签和菱形消耗图标
- **技术栈**:纯 CSS keyframes (pe-spark-pulse / pe-orbit / pe-flip) + SVG
- **验证**:Playwright 截图+DOM 探针全部通过 (verify/shot_launcher_v3.png)
- **状态**:已部署到 `NodeChatPrompt.tsx` + `index.css`

## 设计一致性约定
- **库默认样式覆盖**：使用 ReactFlow/Antd 等库时，必须显式覆盖其默认节点/组件样式（如 `.react-flow__node-group` 的直角边框），否则会出现库样式与自定义样式叠加的“两个框”问题。
- **圆角对齐**：嵌套容器/卡片的圆角必须成体系；若需层级差，应大于 4px，避免 1-2px 的似是而非。
- **颜色指示器**：小尺寸色块优先使用“颜色环（ring）”而非实心圆点；半透明背景色用于指示器时，应提升 alpha 以保证可见。
- **透明态不覆盖 CSS**：组件在“透明/未设置”状态下不要写死内联 `background: transparent`，应让 CSS 默认样式生效，避免用户感知不到容器边界。
- **主题兜底**：除 `.light`/`.dark` 类外，关键视觉元素（如 group 边框）应补充 `prefers-color-scheme` 媒体查询兜底，防止主题类未初始化时样式与 body 背景 mismatch。

## 通用约定
- 设计文档 → `pea-design/`
- 代码改动 → `pea-server/web/`
- 验证截图 → `verify/`
- 工作日志 → `pea-server/.workbuddy/memory/YYYY-MM-DD.md`
