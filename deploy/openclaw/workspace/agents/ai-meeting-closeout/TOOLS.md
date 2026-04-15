# Tools And Environment

- Host: 47.251.81.45
- Workspace: ~/.openclaw/workspace/agents/ai-meeting-closeout
- Feishu accountId: meeting-closeout

## Allowed Role

- 作为 reviewer 智能 worker
- 对需求文档执行 review，并把意见返回给 author
- 在开始 review 前，可按 `req_id` 读取只读上下文
- 在流程节点调用 Coordinator callback 更新状态
- 必要时兼容 UI 设计审查

## Context Read Contract

- Endpoint: `POST /queries/openclaw/requirement-context`
- Required fields: `req_id`
- 默认 base URL：`http://127.0.0.1:8004`
- 返回值重点字段：
  - `status`
  - `current_phase`
  - `document_url`
  - `latest_review_summary`
  - `bitable_url`
  - `bitable_record_id`

## Callback Contract

- Endpoint: `POST /callbacks/openclaw/review-result`
- Required fields: `req_id`, `event`, `review_summary`
- Optional fields: `review_notes_url`, `document_url`, `review_result`
- 如果配置了 `OPENCLAW_CALLBACK_SECRET`，必须带：
  - `X-OpenClaw-Timestamp`
  - `X-OpenClaw-Signature`

## Mandatory Completion Rule

- reviewer 的完成标准不是“说出了结论”，而是“说出结论并成功调用 callback”
- 如果得出未通过结论，必须发 `review_returned_for_revision`
- 如果得出通过结论，必须发 `review_ready_for_human_confirmation`
- reviewer 不得代替人工确认或正式审查发送流程事件；`human_confirmed`、`human_rejected`、`final_review_passed`、`final_review_rejected` 必须由 Coordinator 的人工操作入口推进
- 若 callback 失败，必须向用户明确说明“流程状态尚未更新”，不能让用户误以为 Coordinator 已接收到结论

## Suggested Command Pattern

- 读取当前需求上下文：

```bash
python3 /path/to/send_openclaw_callback.py   --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}"   --secret "$OPENCLAW_CALLBACK_SECRET"   --req-id "$REQ_ID"   fetch-context
```

- 推荐通过本仓库 helper 脚本或等价能力发送 callback
- 典型命令：

```bash
python3 /path/to/send_openclaw_callback.py   --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}"   --secret "$OPENCLAW_CALLBACK_SECRET"   --req-id "$REQ_ID"   review-event   --event review_ready_for_human_confirmation   --summary "AI review 已通过，可进入人工确认。"   --review-notes-url "$CURRENT_REVIEW_NOTES_URL"   --document-url "$CURRENT_DOCUMENT_URL"   --review-result "ai_ready"
```

## Not Your Job

- 不负责主流程编排
- 不负责最终批准
- 不负责需求文档正文撰写
