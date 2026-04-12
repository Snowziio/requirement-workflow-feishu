# OpenClaw Callback 请求模板 v1.2

## 1. 目标

本文档给 `author agent` / `review agent` 的 skill 提供可直接实现的 callback 请求模板。

适用场景：

- `author` 完成需求文档撰写后，通知 Coordinator 进入 AI review
- `reviewer` 完成阶段审查后，通知 Coordinator 更新流程状态

相关正式契约见：

- [openclaw-callback-contracts-v1.2.md](openclaw-callback-contracts-v1.2.md)
- [openclaw-context-query-contract-v1.2.md](openclaw-context-query-contract-v1.2.md)

## 2. 公共配置

OpenClaw skill 侧至少需要以下配置：

- `COORDINATOR_BASE_URL`
  - 例如 `https://coordinator.example.com`
  - 若与 Coordinator Service 同机部署，可使用本机服务地址
- `OPENCLAW_CALLBACK_SECRET`
  - 若 Coordinator 启用了 callback 签名校验，则这里必须保持一致

仓库内也提供了一个可直接复用的 helper 脚本：

- [send_openclaw_callback.py](../../scripts/send_openclaw_callback.py)
  - 适合先做本地联调、网关 smoke test，或直接被 OpenClaw skill 包装调用

## 3. 签名生成

### 3.1 规则

- `timestamp = 当前 Unix 秒级时间戳`
- `raw_body = JSON 原始字节串`
- `signature = hex(hmac_sha256(secret, timestamp + "." + raw_body))`

### 3.2 Python 示例

```python
import hashlib
import hmac
import json
import time


def build_signed_request(payload: dict, secret: str) -> tuple[bytes, dict[str, str]]:
    raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-OpenClaw-Timestamp": timestamp,
        "X-OpenClaw-Signature": signature,
    }
    return raw_body, headers
```

### 3.3 curl 示例思路

如果 skill 侧只能发 shell 命令，建议先由脚本生成：

- `raw_body`
- `timestamp`
- `signature`

再调用：

```bash
curl -X POST "$COORDINATOR_BASE_URL/callbacks/openclaw/author-turn" \
  -H "Content-Type: application/json" \
  -H "X-OpenClaw-Timestamp: $TIMESTAMP" \
  -H "X-OpenClaw-Signature: $SIGNATURE" \
  --data-binary "$RAW_BODY"
```

## 4. 开始前先拉上下文

在 author / reviewer 开始推进某个 `req_id` 前，建议先拉一次当前只读上下文：

```bash
python3 ./scripts/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "REQ-HARNESS-001" \
  fetch-context
```

这一步主要用于确认：

- 当前状态是不是你预期的阶段
- 当前需求文档链接是不是最新的
- 最近 review 结论和待处理焦点是什么
- 如果 `document_url` 已存在，后续必须复用这份文档
## 5. Author Callback 示例

### 5.1 触发时机

只有在以下条件满足时才调用：

- author 已与需求提出者完成当前轮或当前阶段文档撰写
- 当前文档达到可进入 AI review 的门槛
- 当前需求确实需要进入 review，而不是继续在 author 私聊里追问

### 5.2 请求体

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "author_ready_for_ai_review",
  "summary": "需求文档已完成当前轮撰写，可进入 AI review。",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "document_version": "v3",
  "iteration_round": 3
}
```

### 5.3 Python 请求示例

```python
import requests


payload = {
    "req_id": "REQ-HARNESS-001",
    "event": "author_ready_for_ai_review",
    "summary": "需求文档已完成当前轮撰写，可进入 AI review。",
    "document_url": "https://example.com/doc/REQ-HARNESS-001",
    "document_version": "v3",
    "iteration_round": 3,
}

raw_body, headers = build_signed_request(payload, secret=OPENCLAW_CALLBACK_SECRET)
response = requests.post(
    f"{COORDINATOR_BASE_URL}/callbacks/openclaw/author-turn",
    data=raw_body,
    headers=headers,
    timeout=20,
)
response.raise_for_status()
print(response.json())
```

### 5.4 Helper 脚本示例

```bash
python3 ./scripts/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "REQ-HARNESS-001" \
  author-ready \
  --summary "需求文档已完成当前轮撰写，可进入 AI review。" \
  --document-url "https://example.com/doc/REQ-HARNESS-001" \
  --document-version "v3" \
  --iteration-round 3
```

### 5.5 成功响应示例

```json
{
  "ok": true,
  "req_id": "REQ-HARNESS-001",
  "status": "AI_REVIEWING",
  "current_phase": "AI Review",
  "current_round": 3,
  "current_owner": "reviewer",
  "latest_review_summary": "需求文档已完成当前轮撰写，可进入 AI review。"
}
```

## 6. Reviewer Callback 示例

### 6.1 `review_returned_for_revision`

适用场景：

- AI review 未通过
- reviewer 已把意见返回给 author
- 流程应回到 `DISCUSSING`

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "review_returned_for_revision",
  "review_summary": "AI review 认为验收标准仍不可验证，需要继续修改需求文档。",
  "review_notes_url": "https://example.com/review/REQ-HARNESS-001",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "needs_revision"
}
```

### 6.2 `review_ready_for_human_confirmation`

适用场景：

- AI review 已通过
- 流程应进入人工确认

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "review_ready_for_human_confirmation",
  "review_summary": "AI review 已通过，当前需求文档可进入人工确认。",
  "review_notes_url": "https://example.com/review/REQ-HARNESS-001",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "ai_ready"
}
```

### 6.3 `human_confirmed`

适用场景：

- 需求提出者已完成人工确认
- 流程应进入正式审查

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "human_confirmed",
  "review_summary": "人工确认通过，需求表达与预期一致。",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "human_confirmed"
}
```

### 6.4 `human_rejected`

适用场景：

- 需求提出者人工确认不通过
- 流程应退回 `DISCUSSING`

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "human_rejected",
  "review_summary": "人工确认未通过，需要继续修改需求文档。",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "human_rejected"
}
```

### 6.5 `final_review_passed`

适用场景：

- 正式审查通过
- 流程应进入 `REQ_APPROVED`

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "final_review_passed",
  "review_summary": "正式审查通过，可进入下一层流程。",
  "review_notes_url": "https://example.com/review/final/REQ-HARNESS-001",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "approved"
}
```

### 6.6 `final_review_rejected`

适用场景：

- 正式审查退回
- 流程应回到 `DISCUSSING`

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "final_review_rejected",
  "review_summary": "正式审查未通过，需要继续补充文档后再次发起审查。",
  "review_notes_url": "https://example.com/review/final/REQ-HARNESS-001",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "rejected"
}
```

## 7. Reviewer 通用请求模板

```python
import requests


payload = {
    "req_id": "REQ-HARNESS-001",
    "event": "review_returned_for_revision",
    "review_summary": "AI review 认为验收标准仍不可验证，需要继续修改需求文档。",
    "review_notes_url": "https://example.com/review/REQ-HARNESS-001",
    "document_url": "https://example.com/doc/REQ-HARNESS-001",
    "review_result": "needs_revision",
}

raw_body, headers = build_signed_request(payload, secret=OPENCLAW_CALLBACK_SECRET)
response = requests.post(
    f"{COORDINATOR_BASE_URL}/callbacks/openclaw/review-result",
    data=raw_body,
    headers=headers,
    timeout=20,
)
response.raise_for_status()
print(response.json())
```

## 8. Reviewer Helper 脚本示例

### 8.1 退回修改

```bash
python3 ./scripts/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "REQ-HARNESS-001" \
  review-event \
  --event review_returned_for_revision \
  --summary "AI review 认为验收标准仍不可验证，需要继续修改需求文档。" \
  --review-notes-url "https://example.com/review/REQ-HARNESS-001" \
  --document-url "https://example.com/doc/REQ-HARNESS-001" \
  --review-result "needs_revision"
```

### 8.2 进入人工确认

```bash
python3 ./scripts/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "REQ-HARNESS-001" \
  review-event \
  --event review_ready_for_human_confirmation \
  --summary "AI review 已通过，当前需求文档可进入人工确认。" \
  --review-notes-url "https://example.com/review/REQ-HARNESS-001" \
  --document-url "https://example.com/doc/REQ-HARNESS-001" \
  --review-result "ai_ready"
```

## 9. 失败处理建议

- `400`
  - skill 请求体有误
  - 优先检查 `event`、必填字段名、JSON 结构
- `401`
  - 签名错误或时间戳过期
  - 优先检查 secret、一致的 `raw_body`、本机时间
- `404`
  - `req_id` 不存在或已失效
  - 优先检查是否使用了正确环境和正确需求号
- `500`
  - Coordinator 内部异常
  - 建议记录完整响应并重试前人工确认

## 10. 最小联调顺序

1. author 发送 `author_ready_for_ai_review`
2. reviewer 发送 `review_returned_for_revision`
3. reviewer 发送 `review_ready_for_human_confirmation`
4. 人工确认后发送 `human_confirmed`
5. 正式审查发送 `final_review_passed`

只要这 5 步走通，主流程就能完整闭环。
