# pea Creative OS — 资深开发二轮:前端一致性与验证闭环

> 评审人: Senior Developer (高级开发工程师) · 日期: 2026-07-23
> 范围: 前端设计一致性 (对齐 `pea-canvas-v12.html`) + 交互 bug 修复 + 验证闭环
> 基线: 首轮 `REVIEW-senior-dev-2026-07-23.md` (后端钱路/状态机/越权/CI) 已修; 本轮聚焦前端 + 真机 E2E
> 结论: **前端与原型达成高一致 (样式 + 交互); Delete 快捷键 bug 修; 验证发现并修复一个生产级注册 500 回归; Playwright 真机 E2E 全绿 (0 console error)**

---

## 一、前端设计令牌对齐 pea-canvas-v12.html

原型设计令牌 (从 `pea-canvas-v12.html` `:root` 抽取) 与原前端实现存在系统性偏差, 本轮全部对齐。

| 令牌 | 原型 (pea-canvas-v12) | 原前端 (修正前) | 修正后 |
|---|---|---|---|
| 主色 (accent) | `#1fa2dc` (青蓝) | `#6C5CE7` (紫) | **`#1fa2dc`** |
| 深色底色 | `#0a0a0a` (--bg-deep) | 组件散落 `#1c1c24`/`#0a0a0a` | **统一 `--pea-bg-deep` CSS 变量** |
| 次强调 (AI) | `#8b5cf6` (紫) | `#00CEC9` (青) | **`#8b5cf6`** |
| 第三色 | `#34d399` (青柠) | 无 | **`#34d399`** |
| Logo 渐变 | `linear-gradient(135deg,#7c5cfc,#1fa2dc,#34d399)` | `from-pea-brand to-pea-accent` (2 段) | **`from-pea-purple via-pea-brand to-pea-lime`** |
| 字体 | system + PingFang SC + Noto Sans CJK SC | Inter / system-ui | **同上 + CSS 变量** |
| 顶栏 | 52px 毛玻璃 `backdrop-filter:saturate(180%) blur(12px)` | 52px 毛玻璃 ✓ | 统一用 `--pea-*` 变量驱动 |

### 修改的令牌源 (单一事实源)
- `web/tailwind.config.js` → `pea.brand/pea.purple/pea.lime/pea.accent` + 字体栈
- `web/src/styles/index.css` → `:root` / `.dark` CSS 变量 (`--pea-bg-deep` 等) + body 背景; 替换所有硬编码 `#6c5ce7`/`#00cec9`/`rgba(108,92,231,*)`
- `web/src/App.tsx` → antd `ConfigProvider.token`: `colorPrimary:'#1fa2dc'`、`colorInfo`、`borderRadius:10`、字体
- `web/src/components/PeaNode.tsx` → 节点类型色 (generate→`#1fa2dc`、prompt→`#8b5cf6`、text→`#34d399`)
- `web/src/components/TopNav.tsx` → Logo 三色渐变 + 导航项对齐原型顺序
- 6 个页面 (`Account/Arena/Home/Settings/TapTV/Login`) 的硬编码十六进制全部替换
- `NotificationCenter.tsx` / `Toast.tsx` info 色 → `#1fa2dc`

> 资深开发把关: 引入 CSS 变量 (`--pea-*`) 作为暗/亮主题单一源, Tailwind 调色板与 antd token 同时绑定; 后续改色只动 `index.css` 的 `:root`/`.dark` 两块, 组件无需动。

---

## 二、Delete 快捷键 bug 修复 (Playwright 真机抓出)

### 现象
`verify_e5.py` 输出:
```
[check] Delete shortcut: 2 -> 2 (expect -1)   ← 失败
```

### 根因
`web/src/components/CanvasEditor.tsx` 快捷键 handler 顺序错误:
```ts
if (editing) return;                        // ← 提前 return
if (e.key === 'Delete' || 'Backspace' && sel) removeNode(sel);
```
点击生成节点 → 中心是内联 `<textarea>` (用于写 prompt) → 获焦 → `editing===true` → handler 在 Delete 检查**之前**就 return → 节点永远删不掉。
context menu 的"删除"绕过了此路径 (直接调 `removeNode`), 所以那条路通; 键盘路被吞。

### 修复
```ts
if (e.key === 'Delete' && sel) { e.preventDefault(); removeNode(sel); return; }
if (editing) return;                         // ← 移到 Delete 之后
if (e.key === 'Backspace' && sel) { removeNode(sel); return; }
```
- **Delete** 键: 删除选中节点, 即便焦点在内联输入框 (画布标准交互)
- **Backspace** 键: 仅在非编辑态删除节点; 编辑态走原生文本编辑 (不破坏 prompt 输入)
- 验证: `Delete shortcut: 2 -> 1 (expect -1)` ✅ 通过

> 资深开发把关: 画布类工具的 Delete/Backspace 语义必须**显式分流**——Delete = 删对象, Backspace = 删字符; ReactFlow 自带 `deleteKeyCode` 也只对 Delete 起效, 不要混用。

---

## 三、生产级回归: `POST /auth/register` 返回 500 (本轮发现并修复)

### 现象
真机验证 `verify_e7.py` 注册步骤超时 (`.react-flow` 20s 不出现); `curl POST /auth/register` 返回 `{"code":500,"message":"internal error"}`。

### 根因
首轮资深开发评审修复"注册不写赠金流水"时, 在 `auth.service.ts` register 事务内新增:
```sql
INSERT INTO ledger_entries (..., type='grant', ...)
```
但 `mysql_data` Docker 卷是**持久化**的 (本次环境已运行 16h), 启动时的 `initdb.d/01-schema.sql` 仅对**新卷**生效。该卷的 `ledger_entries.type` 枚举仍为:
```
enum('preauth','confirm','refund')   ← 缺 'grant'
```
所以 grant 行 INSERT 报 Data truncation → register 500。**首轮 REVIEW §八 明确写了"需手动 ALTER", 但无人执行**。本轮真机验证把它挖了出来。

### 修复 (不可逆 DDL, 已执行)
```sql
ALTER TABLE ledger_entries
  MODIFY COLUMN type ENUM('grant','preauth','confirm','refund') NOT NULL;
```
register 重测: `{"user":{...},"token":"eyJ..."}` ✅

### 团队规范 (新增)
1. **DDL 变更 PR 必须在描述里写"是否需对已存在数据卷执行迁移 SQL"**; 若需, 合并人必须在合并后立即执行并在 PR 评论贴结果。
2. **`.github/workflows/ci.yml` 启动 job 加入迁移门**: 启动容器后跑一次 `assert-migrated.sh` (校验关键枚举/列), 失败阻断部署。→ 下期 T-OBS-04 落实。
3. **真机 E2E 是这类回归的终极防线**——单元测试覆盖不到"服务起来 + 注册跑通"这条端到端链路; 任何 DDL/状态机/钱路变更都必须跑一遍 `verify_e*.py`。

---

## 四、验证脚本与新导航对齐

原 E7/E8 脚本硬编码了"旧顶栏"的导航项 (`设置`/`账户` 直接在顶栏), 本轮顶栏已对齐原型 (主页/工作空间/电商套图/TapTV/竞技场; 设置/账户在头像菜单)。同步修正:

| 脚本 | 修正 |
|---|---|
| `verify_e7.py` | 注册用**时间戳邮箱** (`e7_{ts}@pea.ai`), 避免与持久化 DB 中 `verify@pea.ai` 冲突 |
| `verify_e8.py` | BFF 端口 `4000`→**`4100`** (宿主映射); 设置/账户改经 `.pea-user-trigger` → "AI Provider 设置"/"账户中心" |

---

## 五、验证结果 (Playwright 真机, 0 console error)

| 套件 | 覆盖 | 结果 |
|---|---|---|
| **E5** (画布 M1) | 添加节点、Agent 副驾驶、侧边面板、**Delete 快捷键**(原 bug→✅)、深色主题 | **6/6 check, 0 console error** |
| **E7** (全局系统 G) | 注册+登录、5 项导航、SPA 画布常驻、通知、分享 Toast、用户菜单、深色 | **13/13 PASS, 0 console error** |
| **E8** (主页/账户/Provider) | 主页"最近项目"、Provider 开关/默认/持久化、账户中心 | **全 PASS, 0 console error** |
| **E9** (社区 TapTV) | feed/发布/详情/点赞/收藏/评论/Arena Non-Goal | **9/9 PASS, 0 console error** |

构建: `npm run build` (tsc -b + vite build) **EXIT 0**, 3242 modules, 11.5s。

---

## 六、给团队 (把关要点补充)

1. **设计令牌 = CSS 变量 + Tailwind + antd token 三方绑定**: 改色只动 `:root`/`.dark` 两块, 组件 `text-pea-brand`/`bg-pea-brand`/antd `colorPrimary` 自动跟随。
2. **Delete vs Backspace 必须分流**: 画布类工具不要让"对象删除"和"字符删除"共用同一条判断。
3. **真机 E2E 是 DDL/状态机的最终防线**: CI 跑 `verify_e*.py` (T-OBS-04), 任何钱路/DDL 变更必须 0 console error 才允许合并。
4. **导航/路由改动要同步验证脚本**: 改 UI 时, grep 一下 `verify_*.py` 里有没有写死选择器, 一起改。
5. **Docker 持久卷的 DDL 不会自动迁移**: 任何 `ALTER`/新枚举必须在 PR 描述写明并执行。

---

## 七、交付物清单 (本轮)

- **设计**: `tailwind.config.js` / `styles/index.css` (token) / `App.tsx` (antd)
- **交互**: `CanvasEditor.tsx` (Delete fix) / `TopNav.tsx` (nav + 标题 lastSaved) / `canvas.ts` store (lastSavedAt)
- **视觉**: `PeaNode.tsx` / `NotificationCenter.tsx` / `Toast.tsx` / 6 个 page
- **验证**: `verify/verify_e7.py` (时间戳邮箱) / `verify/verify_e8.py` (用户菜单 + 4100)
- **数据**: mysql `ALTER TABLE ledger_entries MODIFY COLUMN type ENUM(...,'grant',...)` (已执行)
- **治理**: `TASK-BREAKDOWN-pea.md` §3 矩阵更新 (E5/E7/E8/E9 关键任务翻 `已验证/可全量`) + 二轮评审 note
