# ADR-004: 图像生成读取超时与重试语义修正（消除延迟翻倍）

## Status
Accepted

## Context
ADR-003 让节点图片/视频调用真实 Agnes 模型并可靠显示（事件 + 轮询双通道）。用户实测反馈「现在能出图了，还是很慢」。
排查编排器日志，发现铁证：

```
[agnes] attempt 1 network error ReadTimeout (read timeout=110), retry in 4s
[worker] route() for job ee009ec3 ... took 214.65s (provider=Agnes AI)
```

即**一次图片生成花了 214 秒（3.5 分钟）**，且在此前触发了 `ReadTimeout (read timeout=110)`。

根因有三层：
1. `agnes_provider._generate_image` 的**读取超时硬编码 110s**，但 Agnes 高峰期本身就要 100–170s 才返回（代码注释 `agnes_provider.py` 已自述）。慢但有效的响应在 110s 被当作超时掐断 → 从头重试 → 延迟≈翻倍（实测 214s）。
2. 配置里另有 `PEA_PROVIDER_IMAGE_TIMEOUT_S=300`（worker 硬超时 330s 也据此推算），但 image 路径**从未使用**，这个 300s 预算被白白浪费。
3. `_post_with_retry` 把 `requests.Timeout` 也列入重试条件：读取超时即重试，等于「已等待的 110s 作废，再等一遍」。

> 注：模型本身有物理下限。真实 Agnes flash 典型 18–77s，峰值 ~170s，这是调用真实模型 unavoidable 的成本，无法靠架构压到 1–3s。本 ADR 解决的是「可避免的超时→重试翻倍」这部分。

## Decision
1. image 读取超时从硬编码 `110` 改为 `settings.provider_image_timeout_s`（=300，覆盖 Agnes 峰值延迟）。worker 硬超时 330s 仍作为最终兜底，300s 单次尝试留有 30s 余量。
2. 重试仅保留**瞬时可重试错误**：HTTP 429/500/502/503 与 `ConnectionError`。**移除对 `requests.Timeout` 的重试**——读取超时意味着提供商在预算内一字未回（真挂死/半开连接），重试只会浪费已等待的时间。Agnes 峰值延迟表现为「带 503 的响应」（5xx），仍在 300s 内被正常接收并触发重试，语义不变。

## Consequences
- 易（延迟）：消除「超时→重试」带来的延迟翻倍。慢生成在单次尝试内完成，不再被 110s 误杀后重跑；典型耗时回归模型固有区间（Agnes flash 18–77s，峰值 ~170s）。极端 >300s 的挂死会干净失败并退款，而非翻倍后还失败。
- 易（韧性）：真实瞬时 503/连接错误仍被重试保护。
- 代价：单次真挂死最多等 300s 才失败（此前 110s 即重试却往往同样失败）；但 300s < worker 硬超时 330s，整体可控。
- 风险（吞吐）：worker 为单线程顺序消费（`run_once` 内 `for` 循环串行；`count=2` 仅单次多取 2 条，不并行）。单张图不受影响；若并发多张，会排队串行。如需并发，应提升 worker 并发（多 consumer / 多进程），属独立扩展项，不在本 ADR 范围。

## 验证
- `verify/timing_probe_real_image.py`：直接打 BFF 测真实出图端到端耗时，打印状态机跳变与总耗时；对照整改前 `route() took 214.65s`。
- 整改后实测（见 verify/timing_probe.log）：单次 route() 在模型固有区间内完成，无 `ReadTimeout ... retry` 日志。

---

## 追加决策（2026-07-26）：默认模型与默认分辨率

### Context（续）
用户追问：「我直接调 `apihub.agnes-ai.com/v1` 基本秒回，为啥你们系统很慢？」
为排除「我们 pipeline 慢」的猜测，做了一组**同源对照实测**（同一台机器出口，同一把 key）：

| 调用 | 模型 | 尺寸 | 实测耗时 | 说明 |
|---|---|---|---|---|
| 我们系统默认 | `agnes-image-2.0-flash` | **2048×2048** | 94.9s（BFF 端到端）/ 79s（直连模型） | 默认分辨率 2K |
| 直连同模型 | `agnes-image-2.0-flash` | 2048×2048 | 79s | 与系统差 ~16s = 队列+派发+回填，可忽略 |
| 直连更快模型 | `agnes-image-2.1-flash` | 1024×1024 | <48s | 模型快一档 |
| **网络基线** | — | — | **1.7s RTT** | egress 不是瓶颈 |

结论：
1. **我们的 pipeline 只加 ~2s 开销**（队列→worker→模型→回调→WS→节点），不是慢的原因。
2. **网络到 Agnes 仅 1.7s RTT**，也不是瓶颈。
3. 慢的 100% 是**模型调用本身**：`agnes-image-2.0-flash` @ 2048² 固有 79s+；图像扩散从本机出口根本做不到「秒回」。
4. 用户感知的「秒回」几乎必然来自**不同的调用**：要么用了更小的尺寸（512/1024²），要么用了更快的模型（2.1-flash），要么调的是**文本/对话端点 `/v1/chat/completions`**（首 token 秒回，与图像扩散不可比）。

### Decision
将节点图片生成的默认值向「快」倾斜（质量换速度，用户可手动调回）：
1. **默认分辨率 2K → 1K**（`NodeChatPrompt.tsx` `useState('2k')` → `useState('1k')`，即 2048²→1024²）。计算量大幅下降，画质对绝大多数场景仍够用；需要高清可在 UI 切回 2K/3K。
2. **默认图像模型 `agnes-image-2.0-flash` → `agnes-image-2.1-flash`**（`ai_models.is_default` 翻转）。实测 2.1-flash 同尺寸明显更快。
3. 维持 ADR-004 的超时/重试修正（不引入翻倍延迟）。

### Consequences
- 易（速度）：默认出图从 ~95s 降到预期 30–50s 区间（1K + 2.1-flash 组合）。
- 代价（质量）：默认图分辨率减半、模型迭代一档；画质敏感场景由用户主动选 2K + 2.0-flash。
- 不变：真实图像扩散的**物理下限仍在数十秒**，架构无法压到「秒回」；若用户坚持秒级，唯一出路是 Agnes 侧提供 turbo/极小模型，或接受其「秒回」实为文本端点。
- 可回退：上述两项均为配置/默认值，改回 `2k` + 2.0-flash 即可恢复高画质默认。
