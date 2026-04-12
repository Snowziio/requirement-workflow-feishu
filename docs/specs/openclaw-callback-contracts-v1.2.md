# OpenClaw Callback 契约 v1.2

## 1. 目标

本文档定义 OpenClaw `author agent` / `review agent` 向 `Coordinator Service` 上报流程事件时的固定 callback 契约。

核心边界：

- `author agent` 负责需求文档的交互式撰写与修改
- `review agent` 负责 review 过程与审查意见生成
- `Coordinator Service` 不参与需求文档撰写
- `Coordinator Service` 只负责更新 Bitable、状态机、工作流与通知
- 对 `review agent` 来说，正式结论必须与 callback 绑定；只输出自然语言结论而不上报事件，视为流程未完成

因此 callback 是**事件上报**，不是**文档内容上报**。

## 2. 回调入口

- `POST /callbacks/openclaw/author-turn`
- `POST /callbacks/openclaw/review-result`

返回：

- `200`：成功接收并推进流程
- `400`：请求体不合法
- `401`：签名或时间戳校验失败
- `404`：`req_id` 不存在
- `500`：服务内部错误

## 3. 签名规范

当配置了 `OPENCLAW_CALLBACK_SECRET` 时，两个 callback 都必须携带：

- `X-OpenClaw-Timestamp`
- `X-OpenClaw-Signature`

签名算法：

```text
signature = hex(hmac_sha256(secret, timestamp + "." + raw_body))
```

要求：

- `timestamp` 使用 Unix 秒级时间戳
- 默认允许时间窗为 300 秒，可通过 `OPENCLAW_CALLBACK_TTL_SECONDS` 调整
- `raw_body` 必须使用原始请求字节串参与签名

## 4. Author Callback

### 4.1 用途

`author agent` 在与需求提出者完成一轮或多轮需求撰写后，通知 Coordinator：

- 当前需求文档已经达到可进入 AI review 的门槛
- Coordinator 应把状态推进到 `AI_REVIEW`

### 4.2 请求体

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "author_submit",
  "summary": "需求文档已完成当前轮撰写，可进入 AI review。",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "document_version": "v3",
  "iteration_round": 3
}
```

### 4.3 字段约束

- `req_id`
  - 必填，字符串
- `event`
  - 必填
  - 当前仅支持：`author_submit`
- `summary`
  - 必填
  - 用于写入 Bitable 的最近状态说明
- `document_url`
  - 可选
  - 由 author agent 持有并回传，Coordinator 只记录引用
- `document_version`
  - 可选
  - 用于外部审计或后续联调，不参与当前状态机判断
- `iteration_round`
  - 可选
  - 若提供，Coordinator 仅作为流程观测值记录

### 4.4 成功响应

```json
{
  "ok": true,
  "req_id": "REQ-HARNESS-001",
  "status": "AI_REVIEW",
  "current_phase": "AI Review",
  "current_round": 3,
  "current_owner": "reviewer",
  "latest_review_summary": "需求文档已完成当前轮撰写，可进入 AI review。"
}
```

## 5. Review Callback

### 5.1 用途

`review agent` 在完成阶段性 review 后，通知 Coordinator 当前流程应该如何流转。

注意：

- review 意见应先回到 `author agent`
- 由 `author agent` 驱动文档修改
- Coordinator 只消费 review 结论对应的流程事件

### 5.2 支持事件

- `ai_review_reject`
  - AI review 未通过，退回 `DRAFTING`
- `ai_review_pass`
  - AI review 已通过，进入 `HUMAN_CONFIRM`

注意：

- reviewer callback 只覆盖 AI review 阶段
- 人工确认与正式审查必须由 Coordinator 的人工操作入口推进
- reviewer 不得代替人工确认或正式审查发起状态迁移

### 5.3 请求体

```json
{
  "req_id": "REQ-HARNESS-001",
  "event": "ai_review_reject",
  "review_summary": "AI review 认为验收标准仍不可验证，需要继续修改需求文档。",
  "review_notes_url": "https://example.com/review/REQ-HARNESS-001",
  "document_url": "https://example.com/doc/REQ-HARNESS-001",
  "review_result": "needs_revision"
}
```

### 5.4 字段约束

- `req_id`
  - 必填，字符串
- `event`
  - 必填，必须属于支持事件集合
- `review_summary`
  - 必填
  - 用于 Bitable、卡片、状态观测
- `review_notes_url`
  - 可选
  - 指向 review agent 维护的审查意见页面
- `document_url`
  - 可选
  - 指向 author agent 当前维护的需求文档
- `review_result`
  - 可选
  - 供外部系统使用，Coordinator 当前仅做透传记录准备

### 5.5 成功响应

```json
{
  "ok": true,
  "req_id": "REQ-HARNESS-001",
  "status": "DRAFTING",
  "current_phase": "需求构造",
  "ai_ready": false,
  "latest_review_summary": "AI review 认为验收标准仍不可验证，需要继续修改需求文档。",
  "current_owner": "author"
}
```

## 6. 推荐协作时序

```text
创建群创建需求
-> Coordinator 创建 REQ 与 Bitable 记录
-> 用户私聊 author agent
-> author agent 完成需求文档撰写
-> author callback: author_submit
-> Coordinator 状态 -> AI_REVIEW
-> 用户与 review agent 进行 review 沟通
-> review agent 给出审查意见并回传给 author agent
-> author agent 修改需求文档
-> review callback: ai_review_reject / ai_review_pass
-> 人工确认：由 Coordinator 指令入口推进
-> 正式审查：由 Coordinator 指令入口推进
-> Coordinator 只负责状态流转与工作流通知
```

## 7. 边界说明

- Coordinator 不接收字段级 `updates`
- Coordinator 不改写需求文档正文
- Coordinator 不编译需求文档内容
- author / reviewer 不直接推进 Bitable 状态机
- 需求文档是真正由 agent 驱动的自然语言工作产物
