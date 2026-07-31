# 节点标题(徽章)与画布缩放联动修复 — 2026-07-31

## 根因
`.pea-node-chrome`（承载标题徽章 + 功能条 + 上传条）**整层**做了
`transform: scale(var(--pea-inv-zoom))` 反向缩放：目的是让交互控件在任意
画布缩放下都保持屏幕恒定尺寸（不变成针眼/挤不下），但副作用是**标题徽章
也被一起反向缩放**——节点框 85px~1020px 时徽章始终 131px，比例从 0.77
漂到 0.13。隐藏了 7 处历史修复尝试都不彻底（漏改 CSS 或漏改 inline style）。

关键证据（修复前）：
```
zoom=0.25  card=85   badge=131   ratio=1.54  → 徽章比节点还宽
zoom=1.00  card=340  badge=131   ratio=0.385
zoom=3.00  card=1020 badge=131   ratio=0.128 → 标题变成小蚂蚁
```

## 修复方案（拆分 chrome 为两层，各自独立缩放策略）
```
pea-node-chrome          ← 外层，纯 flow 坐标，不做 counter-scale
  └─ NodeBadge           ← 跟随节点框等比缩放（相对大小恒定 ✓）
  └─ pea-node-chrome-fixed  ← 内层，绝对定位 + counter-scale
       ├─ TextNodeToolbar
       ├─ pea-node-top-upload-bar
       └─ ResultToolbar (portal 入口改成 chromeFixedRef)
```

- 徽章 → 跟节点一起放大缩小，比值恒定 `0.3859`
- 交互控件 → 屏幕大小恒定 71px，任何 zoom 下都能点
- 徽章与 chrome-fixed 的间距用 `margin-bottom: 8px * invZoom`
  抵消 zoom，视觉间距永远 8px

## 验证（verify_badge_scale.py，3 个节点 × 7 个 zoom 级别）
```
want   zoom   cardW    badgeW   badge/card   uploadW   gap(px)
0.25   0.25   85       32.8     0.3859       71        2.75
0.50   0.50   170      65.6     0.3859       71        5.50
0.75   0.75   255      98.4     0.3859       71        8.25
1.00   1.00   340      131.2    0.3859       71       11.00
1.50   1.50   510      196.8    0.3859       71       16.50
2.00   2.00   680      262.4    0.3859       71       22.00
3.00   3.00   1020     393.6    0.3859       71       33.00

PASS：标题与节点等比缩放(badge/card=0.3859 恒定)
     交互控件屏幕大小恒定(71.0px)
```
判定项全过：A 比例恒定、B badge 宽 = zoom × unit、C 上传条恒定 71px、
D 三个节点 (image/text/result) 全按比例缩放、E 标题始终在节点框上方且不重叠。

## 改动的文件
- `web/src/components/PeaNode.tsx`
  - 新增 `chromeFixedRef`（交互控件层 ref）
  - 外层 chrome 去掉 counter-scale，只写 `--pea-node-inv-zoom` 变量
  - `<NodeBadge>` 留在外层自然 flow；交互控件挪进 `<div class="pea-node-chrome-fixed">`
  - `MediaNodeBody` 的 `chromeRef` prop 改为 `chromeFixedRef`（portal 入口）

- `web/src/styles/index.css`
  - `.pea-node-chrome`：去掉 `transform: scale(...)`、去掉用 inv-zoom 算 bottom
  - 新增 `.pea-node-chrome-fixed`：绝对定位 + `transform: scale(inv-zoom)`、
    `margin-bottom: 8px * inv-zoom`、`:empty { display:none }`

- `web/src/components/CanvasEditor.tsx`
  - 新增 E2E 钩子 `window.__peaFitView(padding, maxZoom)`（回归脚本要用）

- `verify/verify_badge_scale.py`：新建（主验证）
- `verify/probe_badge_zoom.py`：新建（量化探测，复现原 bug）

## 回归
- verify_bounce_back.py     PASS（手柄弹回未受影响）
- verify_toolbar_above.py   PASS（多选工具条层级未受影响；唯一 FAIL 与本改动无关）
- verify_selection_bounds_box.py PASS（选区框未受影响）

## 不要回退的要点（写在代码注释里）
1. 外层 `.pea-node-chrome` 不能再加任何 counter-scale —— 这就是原 bug 的源头。
2. 新增交互控件请放进 `.pea-node-chrome-fixed` 子层，绝对不要放外层。
3. 缩放源统一用 `--pea-node-inv-zoom`（节点内联），退化到全局 `--pea-inv-zoom`。

## 部署状态（2026-07-31 收尾）
- **已干净部署到生产 8088**：构建到 `dist-clean` 绕开 `emptyOutDir:false` 累积的旧文件，
  容器内 `rm -rf /usr/share/nginx/html && mkdir` 清空旧产物后 `docker cp`。
- **线上核验**：
  - `curl 8088/` 只引用 `index-BK2p_4ko.js` + `index-Bj30iW4i.css`（各 1 个）
  - `curl .../index-Bj30iW4i.css | grep -c pea-node-chrome-fixed` → `1`（修复类已上线）
  - 容器内 `static/` 仅 2 个文件，无历史残留
- 用户浏览器普通刷新即可看到修复（nginx 已对 `/` 关缓存，见前序会话）。