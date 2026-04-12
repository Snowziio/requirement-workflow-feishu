# OpenClaw Requirement Context Query 契约 v1.2

## 1. 目标

本文档定义 OpenClaw `author agent` / `review agent` 如何按 `req_id` 从 `Coordinator Service` 拉取只读需求上下文。

这个接口的目的不是让 agent 改写 Bitable，而是让 agent 在推进具体需求时拿到当前真相源状态。

## 2. 边界

- `Coordinator Service` 仍然是状态机与 Bitable 的真相源
- `author` / `reviewer` 可以读取上下文，但不能把自己当成流程真相源
- 读取接口只返回只读上下文，不提供写能力
- Bitable 字段名以 [bitable-agent-readable-fields-v1.2.md](bitable-agent-readable-fields-v1.2.md) 和仓库根目录的 `bitable_schema_v12.json` 为准

## 3. Endpoint

- `POST /queries/openclaw/requirement-context`
- `COORDINATOR_BASE_URL` 应指向当前 Coordinator Service 实例

## 4. 鉴权

当配置了 `OPENCLAW_CALLBACK_SECRET` 时，请求必须携带：

- `X-OpenClaw-Timestamp`
- `X-OpenClaw-Signature`

签名规则与 callback 完全一致：

- `signature = hex(hmac_sha256(secret, timestamp + "." + raw_body))`

## 5. 请求体

```json
{
  "req_id": "REQ-HARNESS-001"
}
```

## 6. 成功响应示例

```json
{
  "ok": true,
  "context": {
    "req_id": "REQ-HARNESS-001",
    "name": "需求构造与评审闭环",
    "project": "HARNESS",
    "summary": "验证 agent 私聊构造、review 循环与状态流转。",
    "status": "AI_REVIEWING",
    "current_phase": "AI Review",
    "current_owner": "reviewer",
    "current_role_label": "需求审查Agent",
    "current_round": 3,
    "current_discussion_field": "验收标准",
    "completed_fields": ["问题描述", "使用场景"],
    "pending_fields": ["输入", "输出", "边界", "验收标准", "非功能要求"],
    "ai_ready": false,
    "human_confirmed": false,
    "latest_review_summary": "当前已进入 AI review。",
    "latest_question": "需求已提交 AI review，请由 review agent 与需求提出者完成审查。",
    "document_url": "https://example.com/doc/REQ-HARNESS-001",
    "bitable_record_id": "recxxxx",
    "bitable_url": "https://example.com/base/apptoken?table=tblxxxx",
    "project_group_id": "oc_xxx",
    "review_history": [],
    "human_review_history": [],
    "discussion_history": [],
    "latest_writeback_at": "2026-04-11T10:00:00+00:00",
    "updated_at": "2026-04-11T10:00:00+00:00"
  }
}
```

## 7. 推荐使用方式

- author 在接手需求或准备继续修改前，先按 `req_id` 拉一次上下文
- reviewer 在开始审查前，先拉一次上下文确认当前状态确实处于 `AI_REVIEWING`
- 不要把本地 session 里的记忆当真相源，优先以这里返回的 `status/current_phase/document_url/latest_review_summary` 为准
- 如果返回 `document_url` 非空，author 必须复用该文档，不得另起一份新文档
