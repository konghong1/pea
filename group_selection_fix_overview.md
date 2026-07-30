# 画布多选/打组问题修复总览

## 修复内容

| # | 问题 | 状态 | 关键改动 |
|---|---|---|---|
| 1 | 框选多个节点后，选区遮挡下方节点内容 | 已修复 | `pea-server/web/src/styles/index.css`：`.react-flow__selection` 背景改为半透明 `rgba(31,162,220,0.06)`，`pointer-events: none`，并加 `!important` 覆盖 ReactFlow 运行时默认样式。 |
| 2 | 顶部多选工具栏显示“打包”，且点击选区外部选择框不消失 | 已修复 | `MultiSelectToolbar.tsx` 文案改为“打组”；`CanvasEditor.tsx` 已绑定 `onPaneClick={() => clearSelection()}`，点击画布空白处清空选择。 |
| 3 | 点击打组后报错 `Parent node group_xxx not found`，节点不可用 | 已修复 | `store/canvas.ts` 的 `groupNodes`：先创建 group 节点并置于 nodes 数组最前；子节点设置 `parentNode`、`extent: 'parent'`，并把坐标转为相对 group 原点的相对坐标；随后清空多选。 |

## 验证结果

- `tsc --noEmit` 通过。
- 新增 `verify/verify_group_fix.py` 跑真浏览器验证：
  - 两节点多选后点击空白处 → `selectedIds` 清空。
  - 调用 `groupNodes(['n1','n2'])` → 返回 gid，无 pageerror，无 console 报错。
  - DOM 中 ReactFlow 正确渲染 group + 两个子节点（`.pea-group-node` 存在）。
  - 打组后 `selectedIds=[]`，多选工具条消失。

截图：`verify/shots/grpf_*_20260730133954.png`

## 注意

验证过程中发现两个测试环境/脚本坑点，已记录在工作区 memory 与脚本注释中：
1. Playwright 向 `localStorage.setItem` 写入对象时必须 `JSON.stringify`，否则会被 toString 成 `"[object Object]"`，导致 `auth.ts:7` 解析崩溃、白屏。
2. 本地 dev 的 BFF 经 vite proxy 到 `:4000`，直接访问 `:4100` 注册的用户在 app 中会被 api 拦截器以 401 清 token 跳登录。验证脚本改为走 BASE 代理，并用 `page.route` mock 后端 API，避免后端状态干扰画布 UI 验证。
