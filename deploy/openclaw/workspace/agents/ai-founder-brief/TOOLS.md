# Tools And Environment

- Host: 47.251.81.45
- Workspace: ~/.openclaw/workspace/agents/ai-founder-brief
- Feishu accountId: founder-brief

## Allowed Role

- 作为 author 私聊入口与智能 worker
- 与需求提出者私聊并持续维护需求文档
- 在继续推进需求前，可按 `req_id` 读取只读上下文
- 在文档达到 AI review 门槛后调用 Coordinator callback

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

## Document Reuse Rule

- 如果 context 返回了 `document_url`，必须在这份文档上继续撰写
- 不允许为了继续需求构造而再次新建第二份需求文档
- 只有在 `document_url` 为空时，才允许创建新文档

## Callback Contract

- Endpoint: `POST /callbacks/openclaw/author-turn`
- Event: `author_ready_for_ai_review`
- Required fields: `req_id`, `event`, `summary`
- Optional fields: `document_url`, `document_version`, `iteration_round`
- 如果配置了 `OPENCLAW_CALLBACK_SECRET`，必须带：
  - `X-OpenClaw-Timestamp`
  - `X-OpenClaw-Signature`

## Suggested Command Pattern

- 读取当前需求上下文：

```bash
python3 /path/to/send_openclaw_callback.py   --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}"   --secret "$OPENCLAW_CALLBACK_SECRET"   --req-id "$REQ_ID"   fetch-context
```

- 推荐通过本仓库 helper 脚本或等价能力发送 callback
- 典型命令：

```bash
python3 /path/to/send_openclaw_callback.py   --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}"   --secret "$OPENCLAW_CALLBACK_SECRET"   --req-id "$REQ_ID"   author-ready   --summary "需求文档已完成当前轮撰写，可进入 AI review。"   --document-url "$CURRENT_DOCUMENT_URL"   --document-version "${CURRENT_DOCUMENT_VERSION:-}"   --iteration-round "${ITERATION_ROUND:-1}"
```

## Not Your Job

- 不负责状态机
- 不负责 Bitable 主写入
- 不负责工作流卡点推进
- 不负责最终流转
