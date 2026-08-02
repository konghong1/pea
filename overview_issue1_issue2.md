# 两个问题修复总览（资深开发工程师）

## Issue 1 — 所有媒体节点上传后隐藏左侧输入连接点

**需求**：像图片节点一样，用户自己上传（非 AI 生成）的 image / video / audio 节点，左侧 target 连接点不展示。

**根因**：原逻辑只有图片节点用 `isUserUploadedImage` 控制左侧 Handle 显隐，video/audio 未覆盖。

**修复**（`PeaNode.tsx`）：
- 主组件顶部新增 `isUserUploadedMedia`：（image/video/audio）且 有 `fileKey/url` 且 无 `resultUrl` —— 与 AI 生成结果区分。
- 左侧 Handle 渲染条件由 `{!isUserUploadedImage && (` 改为 `{!isUserUploadedMedia && (`。
- 修正了一处回归：变量改名后必须同步引用点，否则运行期 `ReferenceError`。

**验证**：静态核对 + 与 `NodeBadge` 内同名变量（独立作用域）语义一致，无冲突。

---

## Issue 2 — 生成过程中提示词丢失（重大，已严格排查）

**排查结论（代码审查，后端未运行）**：前端**不存在**任何显式清空 `data.prompt` 的代码路径：
- `applyJobResult` / `reconcileGeneratingNodes` / `pollNodeJobResult` 均为 merge（`{...n.data, ...patch}`），不会清 prompt。
- `saveCanvasNow` 持久化保留完整 `data`（`cleanGraph` 不剥 prompt）；无 server→client 回写覆盖。
- 编辑框 `didInitRef` 守卫：生成期间不会因 `resolvedThumbs`/`initialHtml` 变化被重填。
- 既有 `saveCanvasNow()` 即时落盘已修复"刷新/切走丢 prompt"（见 `NodeChatPrompt.tsx:1320` 注释）。

**最可能的真实成因（感知丢失）**：生成态下节点切到 `pea-node-generating` 覆盖层，**完全不显示提示词**；若用户点击画布取消选中，唯一可见的编辑框卸载 → 看起来"提示词没了"。

**修复**（4 处）：
1. `PeaNode.tsx` 两处生成覆盖层（media / generic）内新增 `.pea-node-gen-prompt` 回显 `data.prompt` —— 生成期间提示词始终可见。
2. `index.css` 新增 `.pea-node-gen-prompt` 样式（浅色多行截断）。
3. `canvas.ts` `applyJobResult` 新增防御：`patch.prompt` 为 `undefined/null` 时 `delete`，杜绝后端回写清空提示词。
4. `NodeChatPrompt.tsx` 节点切换恢复逻辑兜底：本地草稿/editorText 均空但 `data.prompt` 存在且无上游时，回退 `data.prompt`（无上游避免二次拼接重复）。

**验证脚本**：`verify/verify_prompt_not_lost.py`（Playwright，目标 `localhost:8088`）断言：
- 生成态下提示词持续可见（轮询 6×5s）；
- 取消选中再重新选中，编辑框恢复原提示词。
> 需 `docker compose` 起后端后由用户运行；沙箱无 Docker，本次未实跑。

---

## 改动文件清单
| 文件 | 改动 |
|------|------|
| `pea-server/web/src/components/PeaNode.tsx` | `isUserUploadedMedia` 泛化 + 左侧 Handle 引用 + 生成覆盖层回显提示词 |
| `pea-server/web/src/styles/index.css` | `.pea-node-gen-prompt` 样式 |
| `pea-server/web/src/store/canvas.ts` | `applyJobResult` 防御性保留 `prompt` |
| `pea-server/web/src/components/NodeChatPrompt.tsx` | 节点恢复兜底回退 `data.prompt` |
| `verify/verify_prompt_not_lost.py` | 新增复现/验证脚本 |

## 说明
- 沙箱无 Docker，后端未运行，前端改动未经实跑，仅做静态审查与类型/逻辑核对。
- 建议起后端后用 `verify/verify_prompt_not_lost.py` 复测确认。
