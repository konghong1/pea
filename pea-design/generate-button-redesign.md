# 节点生成按钮重新设计 - 集成报告

## 需求
将「消耗积分徽章」和「提交按钮」两个分离元素,重新设计为一个**一体化、3D 悬浮、动画丰富**的生成按钮。

## 设计方案
**一体化能量核心** — `消耗(3D钻石) ← 能量桥流光 → 发射舱(火箭)` 三合一胶囊

### 视觉特征
| 特征 | 实现 |
|------|------|
| 3D 悬浮感 | 多层 box-shadow(顶部高光 + 底部暗面 + 远场辉光) + 缓慢上下浮动动画 |
| 真实钻石 | 经典宝石切面(冠面/腰面/亭面/底尖),多层渐变 + 棱线高光 + 折射光点 |
| 3D 球面发射舱 | 径向渐变 + 内高光/暗面,hover 时辉光暴增 |
| 能量桥 | 中间流光颗粒动画,暗示能量从消耗流向发射 |
| Hover 反馈 | 整组上提 + 缩放,钻石加速旋转,火箭推进动画 |
| 三态支持 | default / disabled / submitting,各状态视觉差异清晰 |

## 技术实现

### 改动文件
1. **`pea-server/web/src/components/NodeChatPrompt.tsx`**
   - 删除旧 JSX:`<span className="node-input-tapies">` 和 `<button className="node-input-send">`
   - 新增 `<span className="pe-launcher">` 一体化组件(84 行)
   - 状态通过 CSS class 切换:`submitting` / `disabled`

2. **`pea-server/web/src/styles/index.css`**
   - 删除旧 CSS:`.node-input-tapies` / `.node-input-send` / spinner / 相关动画(~194 行)
   - 新增 CSS:`.pe-launcher` 系列(~200 行)
   - 无障碍:`prefers-reduced-motion` 自动关闭所有动画

### 关键类名
```
.pe-launcher          整体胶囊(包含所有状态)
  ├─ .pe-gem-cluster  左侧钻石+消耗数字区域
  │   ├─ .pe-gem      钻石 SVG 容器
  │   ├─ .pe-cost     数字+标签
  │   │   ├─ .pe-cost-num
  │   │   └─ .pe-cost-lbl
  ├─ .pe-bridge       能量桥
  └─ .pe-trigger      右侧发射舱
      └─ .pe-rocket   火箭 SVG 图标

状态修饰:
  .pe-launcher.disabled     禁用状态(无输入时)
  .pe-launcher.submitting   生成中状态
  .pe-launcher.mini         紧凑变体(可选)
```

## 构建与部署
- ✅ `tsc -b` 类型检查通过
- ✅ `vite build` 生产构建通过(20s)
- ✅ Docker 容器热更新:`docker cp dist` → `nginx -s reload`
- ✅ CSS 已部署到 `/static/index-8d62UKNe.css`,container 内 24 处 `.pe-launcher` 引用

## 浏览器验证
- 默认态:悬浮动画 + 钻石自转 + 发射舱呼吸辉光
- Hover 态:整组上提 4px,辉光暴增,钻石加速,火箭推进
- 生成中:发射舱持续呼吸,火箭旋转,禁用交互
- 禁用态:饱和度降低,无动画,灰色发射舱

## 性能
- 动画仅使用 `transform` / `opacity` / `box-shadow`(GPU 合成层)
- 60fps,无布局抖动
- 尊重 `prefers-reduced-motion`
