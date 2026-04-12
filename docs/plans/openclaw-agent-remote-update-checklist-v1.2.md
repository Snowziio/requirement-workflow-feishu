# OpenClaw 线上 Agent 改造清单 v1.2

## 1. 目标

将线上 `author agent` / `review agent` 的行为约束更新为事件驱动模型：

- `author` 负责需求文档正文撰写
- `review` 负责 review 循环与审查结论
- `Coordinator Service` 只负责 Bitable、状态机、工作流卡点与通知

## 2. 需要修改的远端对象

- `~/.openclaw/workspace/agents/ai-founder-brief/IDENTITY.md`
- `~/.openclaw/workspace/agents/ai-founder-brief/AGENTS.md`
- `~/.openclaw/workspace/agents/ai-founder-brief/TOOLS.md`
- `~/.openclaw/workspace/agents/ai-meeting-closeout/IDENTITY.md`
- `~/.openclaw/workspace/agents/ai-meeting-closeout/AGENTS.md`
- `~/.openclaw/workspace/agents/ai-meeting-closeout/TOOLS.md`

## 3. Author Agent 新约束

- 负责私聊需求构造与需求文档正文维护
- 不再向 Coordinator 提交字段级 `updates`
- 仅在文档达到阶段门槛时，调用 callback：
  - `POST /callbacks/openclaw/author-turn`
  - `event=author_ready_for_ai_review`

## 4. Review Agent 新约束

- 负责 review 循环，不直接修改需求文档正文
- review 意见返回给 author，驱动文档继续修改
- 仅在流程节点调用 callback：
  - `review_returned_for_revision`
  - `review_ready_for_human_confirmation`
  - `human_confirmed`
  - `human_rejected`
  - `final_review_passed`
  - `final_review_rejected`

## 5. Callback 安全要求

- 若启用 `OPENCLAW_CALLBACK_SECRET`
- 所有 callback 必须带：
  - `X-OpenClaw-Timestamp`
  - `X-OpenClaw-Signature`
- 签名算法：
  - `hex(hmac_sha256(secret, timestamp + "." + raw_body))`

## 6. 落地顺序

1. 更新远端 agent 文档约束
2. 重载或重启对应 agent 会话
3. 配置 callback secret
4. 做 author -> AI review 联调
5. 做 review -> revision / human confirm 联调
6. 做 final review pass / reject 联调
