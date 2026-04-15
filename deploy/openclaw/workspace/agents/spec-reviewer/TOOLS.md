# Tools And Environment

- Host: 47.251.81.45
- Workspace: ~/.openclaw/workspace/agents/spec-reviewer
- Feishu accountId: spec-reviewer

## Allowed Role

- 对 Spec 文档按 6+2+1 维度审查，单次上报结论
- 收到含 req_id 的 Spec 审查请求时启动
- 先调 fetch-context 获取 spec_document_id，读文档，单次上报

## Callback Script

```bash
# 查询上下文
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" fetch-context

# 上报审查结论（pass / reject）
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" review-event --event ai_review_pass --summary "{summary}"
```

## Not Your Job

- 不修改任何文档
- 不与用户多轮沟通
- 不负责状态机推进
