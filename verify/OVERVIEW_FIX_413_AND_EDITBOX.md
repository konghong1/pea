# 修复验证报告：413 上传限制 + AI 图编辑框弹不出

> 验证日期：2026-07-27 · 运行环境：Docker `localhost:8088`（生产构建）
> 验证方式：真机 Playwright E2E（Node），确定性、可复现，非口头声称。

## 一、问题 1 — 上传/替换触发 `413 Request Entity Too Large`

**现象**：已登录用户，`POST http://localhost:8088/files/upload` 返回 `413 Request Entity Too Large`。

**根因**：web 容器 nginx 缺 `client_max_body_size`，默认仅 `1m`，大文件在 nginx 层被拒。与 BFF 侧 multer 的 `100MB` 上限不一致。

**修复**（`pea-server/infra/docker/nginx.conf`，server 块）：
```nginx
client_max_body_size 100m;   # 与 BFF multer fileSize 上限对齐
```
> ⚠️ nginx 配置由 web Dockerfile 在构建时 COPY 成 `default.conf`，**必须 `docker compose up -d --build web` 重建镜像**才生效。已 `docker exec` 确认运行容器内 `default.conf` 第 9 行含该指令。

## 二、问题 2 — 图片节点 AI 生成后点击编辑框不弹出

**推翻的误判**：最初怀疑是图片 `onClick` 吞掉点击导致选不中 —— 真机证伪（旧容器中部节点 `selectedId=nGen, hasInputBar=true`，既能选中也有栏）。

**真正根因**（`web/src/components/NodeChatPrompt.tsx`）：`compute()` 永远把输入栏钉在节点正下方（`top = r.bottom + 16`）。节点落在画布下半区时 `top + BAR_H > 视口高(900)`，输入栏被推出视口外（旧容器实测 `box.top = 913 > 900`），体感"弹不出"。

**修复**：加翻转逻辑 —— 若下方放不下则翻到节点**上方**；仍超界则贴顶（`top = 16`），保证栏始终在视口内可见。

## 三、确定性验证证据（同一脚本，修复前后各跑一遍）

脚本：`verify/verify_fix_413_and_editbox.cjs`（Node Playwright，跑 8088，需 `localStorage.__peaDevHooks='1'`）

### 修复前（旧容器，已抓铁证）
| 测试 | 结果 | 关键证据 |
|---|---|---|
| TEST A 上传 6MB | FAIL | `/files/upload` 响应 `[[413,...]]`，fileKey=null |
| TEST B[nLow] 点生成图 | FAIL | 输入栏 `box.top = 913`（屏外 > 900） |

### 修复后（新容器，重建镜像后）
| 测试 | 结果 | 关键证据 |
|---|---|---|
| TEST A 上传 6MB | PASS | `/files/upload` 响应 `[[201,...]]`，fileKey=`u:149/uploads/...` |
| TEST B[nLow] 点生成图 | PASS | `box.top=457, bottom=617`（视口内） |
| TEST B[nHigh] 点生成图 | PASS | `box.top=613`（视口内） |

**RESULT: ALL PASS** —— 0 console error / 0 pageerror。

> 说明：初版脚本用 `s === 200` 判成功，但 BFF 成功上传返回 **201 Created**，导致修复后误报 FAIL。已改为 `s >= 200 && s < 300`（仅改验证脚本，未动实现，符合协作红线）。

## 四、任何人可复现的命令
```bash
cd /d/workspace/pea/verify
NODE_PATH='C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules' \
  /c/Users/admin/.workbuddy/binaries/node/versions/22.22.2/node.exe \
  verify_fix_413_and_editbox.cjs
```

## 五、为什么之前"每次验证不一致"
1. nginx 改动**必须重建 web 镜像**才生效，旧 8088 容器仍跑旧配置 → 显示 413。
2. 测试断言阈值写错（期望 200，实际 201）→ 误报 FAIL。
3. 现已用同一脚本在修复前后各跑一遍，输出**真实 HTTP 状态码**与**真实 DOM 矩形坐标**，结论可复现、不依赖口头声称。
