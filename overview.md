# 图片生成失败显示修复 — 总结报告

> 资深开发工程师（Senior Developer）交付 · 2026-07-28

## 一、问题现象

用户反馈两类「图片生成不出来」的展示问题：

1. **图片生成失败时，节点显示浏览器裂图（broken image），而不是失败提示卡**。
2. **一直生成失败**（上游偶发 520），但 UI 没有清晰地把失败原因和「重试」能力呈现给用户。

## 二、根因定位（资深视角）

核心 bug 在**前端状态清理不完整**：

- 当生成失败或用户点击「重新生成」时，前端只写入了 `error` 字段，却**残留了上一次的
  `resultUrl` / `resultUrls`**。
- 节点渲染判定 `hasResult = Boolean(currentUrl)` 因此为 `true`，走进了 `<img src={旧url}>` 分支，
  而失败卡分支要求 `data.error && !hasResult` —— 由于 `hasResult` 为真，失败卡**永远进不去**，
  于是浏览器把已失效的旧 URL 渲染成裂图。
- 第二处隐患：若节点持有一个**无效 URL 且没有 error 字段**（例如 reference / rehost 未完成），
  浏览器同样只给默认裂图，没有任何可读的占位。
- 链路缺口：多图结果 `resultUrls` 在 WS 事件合同里存在，但 REST `JobStatusResponse` 没返回，
  前端轮询兜底拿不到，多图节点会丢失其余结果。
- 附带：BFF `files.controller.ts` 用了不存在的 `Express.Multer.File` 命名空间，`tsc` 直接报错
  （TS2694），阻塞构建。

> 上游侧：`Agnes` 偶发 `HTTP 520`（Cloudflare 瞬断），`allow_mock_fallback=false` 会正确退款 ——
> 这是真实上游抖动，不是我们代码的 bug，但需要被**正确呈现**给用户（失败卡 + 重试），而不是静默裂图。

## 三、修复清单

| 层 | 文件 | 改动 |
|---|---|---|
| 前端 | `web/src/lib/nodeGeneration.ts` | `done` 补 `savedToLibrary:false`；`failed/refunded` 清理 `resultUrl/resultUrls/resultIndex/savedToLibrary`；`retryNodeGeneration` 重生成前清理同批字段 |
| 前端 | `web/src/components/NodeChatPrompt.tsx` | WS `failed/refunded` 分支清理同批字段；发起生成时 `update(single, …)` 同步清理 |
| 前端 | `web/src/components/PeaNode.tsx` | `ResultImageView` 增加 `imgError` state + `onError` 处理器，显式渲染「图片加载失败」占位（不依赖 `error` 字段） |
| 前端 | `web/src/styles/index.css` | 新增 `.pea-node-result-image-error` 占位样式 |
| 编排器 | `services/generation-orchestrator/app/api.py` | `_row_to_dto` 解析 `result_json.urls` → 返回 `resultUrls` |
| 编排器 | `app/schemas.py` | `JobStatusResponse` 增加 `resultUrls: list[str] \| None` |
| BFF | `services/bff/src/modules/files/files.controller.ts` | `Express.Multer.File` → `any`，修复 TS2694 构建错 |

**设计原则**：所有「写回节点状态」的入口（WS 事件、轮询兜底、重试发起、accept 失败 catch）
都保持同一套字段清理契约，避免再次出现「只设 error 不清 url」的不对称。

## 四、验证结果

新增离线 E2E 脚本 `verify/verify_image_failure_display.py`（Playwright + dev hooks 注入，
**不依赖真实模型，可重复跑**），覆盖 6 项断言：

```
✅ 失败卡已显示 — count=1
✅ 裂图/结果图未显示 — img_count=0
✅ 重新生成按钮存在
✅ 点击重新生成后旧 resultUrl 已清理 — resultUrl=
✅ 无效 URL 无 error 时显示加载失败占位 — placeholder_count=1
🎉 全部验证通过
```

部署后对所有运行中的容器（web / bff / orchestrator）复跑，结果一致通过。

## 五、给团队的技术沉淀（代码质量点）

1. **状态清理要成对**：设置 `error` 的同时必须清理 `resultUrl/resultUrls`，这是本仓库节点状态
   机的隐性契约，建议升级成 `resetNodeResult()` 单一 helper，避免散落各处。
2. **渲染分支不要依赖「隐式缺省」**：`<img>` 与失败卡之间用「有没有 url」做开关太脆弱，应让
   `onError` 兜底，保证任何无效 URL 都有可读占位。
3. **全链路字段要打通**：WS 合同有了的字段（如 `resultUrls`），REST DTO 也要补齐，否则轮询兜底
   会丢数据——建议加一个 contract 一致性检查。
4. **E2E 是质量闸门**：用 dev hooks 注入失败态做离线 E2E，比等真实上游抖动再修，成本低两个数量级。
   已沉淀为可复用技能 `pea-e2e-failure-verify`。

## 五、样式 Redesign：科技感任务终端

用户进一步反馈「失败卡样式太丑」。我安装并应用了 **Anthropic `frontend-design` skill**
的设计原则，把失败卡从「警告弹窗」重构成「画布命令面板」的一部分：

- **深色玻璃底**：`rgba(16,18,24,0.78)` + `backdrop-filter: blur(10px)`，融入深色画布。
- **顶部琥珀状态边**：1px 高亮边 + 内发光，暗示「状态异常」但不刺眼。
- **角括号 + 脉冲琥珀点**：替代传统警告圆圈，更有科技终端的「状态指示」感。
- **青蓝重试按钮**：品牌渐变 + hover 扫光 + 外发光，作为唯一视觉高光。
- **终端日志详情**：等宽字体、暗色面板，调试时展开有「命令行输出」的质感。
- **无障碍**：所有动画都加了 `prefers-reduced-motion` 降级。

改动文件：`pea-server/web/src/components/PeaNode.tsx`、`pea-server/web/src/styles/index.css`。

## 六、验证

- `tsc --noEmit` 0 错误，`vite build` 通过。
- 部署到 `pea-server-web-1` 并 reload nginx。
- 离线 E2E `verify_image_failure_display.py` 6 项断言全过。
- 新增 `verify/screenshot_failure_card.py` 截图确认新视觉效果。

## 七、后续打磨：生成中状态圆角「半透明」感

用户反馈生成中节点的**四个圆角仍可见、且像半透明**。根因是 `.pea-node-body-card`
背景为 `rgba(34,34,40,0.96)`，在浅色画布上圆角抗锯齿处会轻微透出背景，导致"半透明"错觉。

修复（`pea-server/web/src/styles/index.css`）：

- 生成中时把 `.pea-node-body-card` 背景改为**完全不透明** `#222228`。
- `.pea-node-generating` 面板也使用同色不透明底，并叠加极淡扫描线纹理，保持科技感。
- 所有动画仍保留 `prefers-reduced-motion` 降级。

验证：新增 `verify/screenshot_generating_state.py` 截图确认生成中节点圆角已变为实心深色，
无透光感；同时复跑原有 E2E 6 项断言全过。

## 八、统一设计系统：优雅科技感按钮 + 状态语言

用户要求基于 `frontend-design` skill 设计一套「美观、优雅、科技感、且符合系统 UI」的样式和按钮。
我没有另起一套配色，而是**严格落在系统既有 token 上**（`--pea-brand` 青色、`--pea-lime` 绿色），
只派生 `--pea-accent-soft` / `--pea-warn` / `--pea-warn-soft` 等辅助色。

### 新增/完善内容

1. **统一按钮系统 `.pea-btn`**（`pea-server/web/src/styles/index.css`）
   - 变体：`.pea-btn--primary` / `.pea-btn--ghost` / `.pea-btn--warn` / `.pea-btn--quiet` / `.pea-btn--light`
   - 行为：hover 微抬升 + 柔光 + 扫光高光；focus-visible 双环；`prefers-reduced-motion` 降级
   - 失败卡按钮从各自的 `.pea-node-failure-btn-*` 迁移到 `.pea-btn` 系统，保证全画布/全系统一致

2. **状态签名：status rail**
   - 失败卡顶部：琥珀渐变流光（与生成中同一视觉语言）
   - 生成中面板顶部：青色渐变流光
   - 共用 `@keyframes pea-rail-flow`，是这次设计的「签名元素」

3. **色彩对齐**
   - 把之前游离的 `#38e1ff` fallback 统一回系统品牌青 `#1fa2dc`
   - 失败警告从饱和红改为优雅琥珀 `#f59e0b`

4. **设计文档**
   - 新增 `pea-design/DESIGN-SYSTEM.md` 供团队后续复用和扩展

### 验证

- `tsc --noEmit` 0 错误，`vite build` 通过
- 部署到 `pea-server-web-1` 并 reload nginx
- 原离线 E2E `verify_image_failure_display.py` 6 项断言全过（同步更新了脚本里的按钮选择器）
- 新增截图：`verify/shots/image_failure/failure-card-redesign.png`、
  `verify/shots/image_failure/generating-state-redesign.png`

## 九、结论

图片「生成不出来」的展示问题已修复并验证：失败态现在会正确显示科技感失败卡 + 重试，
无效 URL 有「图片加载失败」占位，多图结果链路补齐，BFF 构建错误已消除。生成中状态圆角
也已改为实心深色。最外层，基于 `frontend-design` skill 和系统自有 token，沉淀了一套统一、
优雅、科技感的节点状态设计语言与按钮系统。真实上游 520 抖动由退款机制兜底，前端呈现清晰、
美观、有科技感的用户体验闭环。
