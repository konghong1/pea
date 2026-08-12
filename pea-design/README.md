# pea 设计基准 · 使用说明

> 本目录是 **pea 前端 UI 的单一事实来源（设计方向）**。
> 三份规范定义「长什么样」，代码（`pea-server/web/src/styles/index.css` + `Workspace.tsx` / `CanvasEditor.tsx`）定义「怎么落地」。
> 任何 UI 改动前先读对应表面的规范，照它的色板 / 字重 / 圆角 / 阴影写，不要自创配色。

---

## 1. 总览

pea 的界面按**使用场景**切成三个「表面（surface）」，每个表面直接对应 awesome-design-md 仓库里的一份设计规范：

| 表面 token | 规范文件 | 美学来源 | 承载区域 |
|---|---|---|---|
| `cinematic` | `runwayml/DESIGN.md` | Runway · 电影感暗色 | 创作端画布（节点流、生成工具条、画布浮层） |
| `precision` | `vercel/DESIGN.md` | Vercel · 单色精准 | 后台 / 管理 / 普通页面（Admin、Plans、Account、TopNav、Workspace 非画布区） |
| `figma` | `figma/DESIGN.md` | Figma · 明亮创作 | 创作端画布的**亮色分支**（用户在画布 header 一键切换） |

一句话原则：
- **后台用 `precision`（Vercel）**
- **创作端用 `cinematic`（Runway）或 `figma`（Figma）二选一**，由画布 header 菜单切换，刷新后原样恢复

---

## 2. 三个表面分别用在哪、怎么落地

### 2.1 cinematic（runwayml）— 创作端 · 暗

- **用在哪**：`CanvasEditor` 节点画布，以及画布内所有 `createPortal` 浮层（多选工具条、节点提示框、搜索弹层、角度魔方面板等）。
- **表面开关**：`Workspace.tsx` 进入画布时
  - `document.body.dataset.surface = "cinematic"`
  - `documentElement` 加 `.dark` 类
  - 离开画布时清除，并据全局 `useTheme` 恢复 `precision` 主题（避免污染后台浮层）。
- **令牌作用域**：`src/styles/index.css` 的 `[data-surface="cinematic"]`。
- **Antd 主题**：`CanvasEditor.tsx` 内嵌 `ConfigProvider` 用 `theme.darkAlgorithm`，`colorPrimary`/`colorInfo` 取 `#f5f5f5`，字体走 Inter 栈。
- **设计规范视觉要点**：纯黑 `#000` 画布、暗节点卡 `#1a1a1a` + `1px #27272a` 发丝边、**零阴影**、cool-slate 连线流光、Inter 单字族、纯黑药丸 CTA。

### 2.2 precision（vercel）— 后台 · 单色精准

- **用在哪**：所有后台 / 管理 / 普通页面，以及不在画布里的 Workspace 区域。这是**默认表面**。
- **表面开关**：无需 `data-surface`。令牌写在 `:root`（亮）与 `.dark`（暗）；明暗由 `store/theme.ts` 通过 `documentElement` 的 `.light` / `.dark` 类控制。
- **Antd 主题**：全局 `ConfigProvider`（在 `App.tsx`）：`colorPrimary: #171717`、`borderRadius: 6`、字体 Geist。
- **设计规范视觉要点**：白 / `#fafafa` 底、墨 `#171717`、发丝线、`6px` 圆角、堆叠微影（soft layered shadows）、Geist 紧字距。

### 2.3 figma（figma）— 创作端 · 亮

- **用在哪**：与 `cinematic` **同一个画布容器**，只是用户把创作主题切到 Figma 时的亮色形态。
- **表面开关**：`Workspace.tsx` 进入画布时
  - `document.body.dataset.surface = "figma"`
  - `documentElement` 加 `.light` 类
- **令牌作用域**：`src/styles/index.css` 的 `[data-surface="figma"]`。
- **Antd 主题**：`CanvasEditor.tsx` 内嵌 `ConfigProvider` 用 `theme.defaultAlgorithm`，`colorPrimary`/`colorInfo` 取 `#000000`，字体走 Inter 栈。
- **设计规范视觉要点**：纯白 `#fff` 画布、白节点卡 + `#e6e6e6` hairline + `0 8px 28px` 软影、`24px` 大圆角、黑墨主操作、Inter 字体、深墨连线。

---

## 3. 全局约定（三表面共用，改 UI 必须守）

1. **只走令牌，禁止硬编码 hex**
   所有颜色用 `--pea-*` CSS 变量（`--pea-bg-deep` / `--pea-bg-surface` / `--pea-border` / `--pea-text-primary` / `--pea-brand` / `--pea-purple` / `--pea-lime` / `--pea-warn` …）。三份规范的「落到 pea 令牌」段就是映射表；新增颜色先加令牌，不要散落写死。

2. **字体两族**
   - 后台 `precision` = **Geist** 主导（Vercel 精准工程感）。
   - 创作端 `cinematic` + `figma` = **Inter** 主导（Runway `abcNormal`、Figma `figmaSans` 为商用私有字体，按规范以 Inter 作开源替身）。
   - 全项目不混第三种字族（代码 / 技术标签用 Geist Mono / JetBrains Mono 除外）。字体在 `index.html` 一次预连接加载。

3. **唯一语义彩色 = AI 紫 `#8b5cf6`**
   表示「生成中 / AI 活动」，跨三表面统一。失败 = 琥珀 `#f5a623`，成功 = 青柠 `#34d399`，主操作 = 纯黑 / 纯白。不要再引入品牌青。

4. **切表面机制**
   - 创作端：`useCreatorDesign()`（`'runway' | 'figma'`）→ 映射到 surface `cinematic` / `figma`。
   - 后台：`useTheme()`（`'light' | 'dark'`）→ 控制 `precision` 明暗。
   - 任何 `createPortal` 到 `body` 的画布浮层会自动继承 `body[data-surface]` + `.light/.dark` 类，无需单独处理。

---

## 4. 给开发 / 代理的速查

- **改任意 UI 前**：先读对应表面的规范（画布 → `runwayml` 或 `figma`；后台 → `vercel`），照它的色板 / 字重 / 圆角 / 阴影写。
- **加新组件**：默认复用 `--pea-*` 令牌 + 既有类（`.pea-btn--primary`、`.pea-node-body-card` 等），不要新建一套配色。
- **新增表面 / 主题**：在 `src/styles/index.css` 加新的 `[data-surface="xxx"]` 作用域 + 节点令牌；在 `store/creatorDesign.ts` 或 `store/theme.ts` 接通切换；在 `Workspace.tsx` 做 `body[data-surface]` + `.light/.dark` 传播。
- **这三份是方向基准**：实现细节（令牌具体值、surface 传播逻辑）以 `src/styles/index.css` + `Workspace.tsx` / `CanvasEditor.tsx` 的当前代码为准，规范文档定方向、代码定落点。

---

## 5. 文件清单

```
pea-design/
├── README.md            ← 本文件（使用说明索引）
├── runwayml/DESIGN.md   ← cinematic 表面规范（创作端·暗）
├── vercel/DESIGN.md     ← precision 表面规范（后台·单色）
└── figma/DESIGN.md      ← figma 表面规范（创作端·亮）
```

---

_UI Designer · 设计基准说明 · 2026-08-12_
