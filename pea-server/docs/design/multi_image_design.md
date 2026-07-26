# 出图数量功能完整方案

## 问题分析

### 当前状态
1. **前端传参 ✅**：`n` 参数已正确传递
2. **编排器 adapter ✅**：`AgnesImageAdapter` 已构建包含 `n` 的 payload
3. **Agnes API 返回多图 ✅**：响应 `data[]` 数组包含所有生成的图片

### 问题链路
1. **编排器丢弃多图**：`agnes_provider.py:159` 只取 `items[0]`，忽略其他
2. **worker 只传单 URL**：`job_updated` 事件只有 `result_url`，没有 `result_urls`
3. **前端从未收到多图**：`resultUrls` 数组已定义，但从未被填充

## 设计方案

### 1. 编排器修改 (generation-orchestrator)

#### 1.1 `llm_router.py` - GenerationResult 支持 urls 数组
```python
class GenerationResult:
    def __init__(self, url: str, provider: str, urls: list[str] | None = None, ...):
        self.url = url           # 主图（兼容旧客户端）
        self.urls = urls or []   # 所有图片 URL
        self.provider = provider
        ...
```

#### 1.2 `agnes_provider.py` - 返回所有图片
```python
def _generate_image(self, req: dict) -> GenerationResult:
    ...
    items = data.get("data") or []
    if not items:
        raise RuntimeError(...)
    
    # 收集所有图片 URL
    urls = []
    for item in items:
        if item.get("url"):
            urls.append(item["url"])
        elif item.get("b64_json"):
            urls.append(f"data:image/png;base64,{item['b64_json']}")
    
    if not urls:
        raise RuntimeError(...)
    
    return GenerationResult(
        url=urls[0],        # 主图（兼容）
        urls=urls,          # 所有图片
        provider=self.provider_name,
        raw={"count": len(urls)},
        usage=data.get("usage") or {}
    )
```

#### 1.3 `worker.py` - 发布多图事件
```python
result_obj: dict = {
    "url": result.url,
    "urls": result.urls,  # 新增
    "provider": result.provider,
    "usage": usage_dict
}
...
publish_event(job_updated(
    job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
    status="done",
    result_url=result.url,
    result_urls=result.urls,  # 新增
    cost=...,
))
```

#### 1.4 `services/shared/events/__init__.py` - 事件结构扩展
```python
def job_updated(*, result_urls: list[str] | None = None, **kwargs):
    event = {...}
    if result_urls:
        event["result_urls"] = result_urls
    return event
```

### 2. BFF 修改

#### 2.1 SSE 推送多图
```typescript
// BFF 收到 job_updated 事件后转发给前端
event: job_updated
data: {"jobId":"xxx","status":"done","resultUrl":"url1","resultUrls":["url1","url2","url3"],...}
```

### 3. 前端修改

#### 3.1 `NodeChatPrompt.tsx` - 处理多图结果
```typescript
// SSE 收到 job_updated 时
if (ev.result_urls && ev.result_urls.length > 0) {
  useCanvas.getState().applyJobResult(ev.jobId, {
    generating: false,
    resultUrl: ev.result_urls[0],
    resultUrls: ev.result_urls,
    resultIndex: 0,
  });
}
```

### 4. Mock Provider 支持

#### 4.1 生成多张占位图
```python
def generate(self, req: dict) -> GenerationResult:
    n = req.get("params", {}).get("n", 1)
    urls = [self._placeholder_image(f"{job_id}_{i}", prompt) for i in range(n)]
    return GenerationResult(url=urls[0], urls=urls, ...)
```

## 实施步骤

1. **Phase 1 - 编排器**：修改 `GenerationResult`、`agnes_provider`、`worker`
2. **Phase 2 - 事件**：扩展 `job_updated` 事件结构
3. **Phase 3 - 前端**：修改 SSE 处理逻辑
4. **Phase 4 - 测试**：E2E 验证多图生成

## 兼容性

- **向后兼容**：`result_url` 保留，旧客户端继续工作
- **新客户端**：读取 `result_urls` 支持多图
- **Mock 模式**：无 API 密钥时也能测试多图
