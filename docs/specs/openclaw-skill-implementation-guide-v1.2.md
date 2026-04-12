# OpenClaw Skill 实现指引 v1.2

## 1. 目标

本文档定义 OpenClaw `author agent` / `review agent` 在当前架构边界下的最小实现方式。

目标不是让 skill 重新承担流程编排，而是让 skill 在正确时机向 Coordinator Service 发出**流程事件**。

## 2. 总体原则

- `author agent` 负责私聊需求构造与需求文档正文撰写
- `review agent` 负责 review 循环与审查意见输出
- `Coordinator Service` 只消费流程事件，更新 Bitable、状态机和工作流
- skill 不上传字段级 `updates`
- skill 不要求 Coordinator 编译或改写需求文档正文

## 3. 推荐实现方式

推荐直接复用仓库脚本：

- [send_openclaw_callback.py](../../scripts/send_openclaw_callback.py)
- [run_openclaw_smoke.py](../../scripts/run_openclaw_smoke.py)

这样 OpenClaw skill 不需要自己实现：

- HMAC 签名拼装
- author / reviewer endpoint 区分
- review 事件枚举合法性检查
- `req_id` 上下文查询

默认情况下，如果不显式传 `--base-url`，helper 会按以下顺序选择：

- `$COORDINATOR_BASE_URL`
- 本机 Coordinator 服务地址

在真实联调前，也可以先用 smoke 脚本串一次最小闭环：

```bash
python3 ./scripts/run_openclaw_smoke.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "$REQ_ID" \
  --document-url "$CURRENT_DOCUMENT_URL" \
  --review-event review_ready_for_human_confirmation
```

## 4. skill 运行前置配置

skill 或 agent 运行环境至少需要：

- `COORDINATOR_BASE_URL`
- `OPENCLAW_CALLBACK_SECRET`
- `REQ_ID`

如需补充展示信息，可额外提供：

- `CURRENT_DOCUMENT_URL`
- `CURRENT_DOCUMENT_VERSION`
- `CURRENT_REVIEW_NOTES_URL`

## 4.1 进入任务前先拉上下文

author / reviewer 在开始处理具体需求前，推荐先按 `req_id` 拉一次只读上下文：

```bash
python3 /path/to/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "$REQ_ID" \
  fetch-context
```

重点读取：

- `status`
- `current_phase`
- `document_url`
- `latest_review_summary`
- `bitable_url`
- `bitable_record_id`

如果返回结果中 `document_url` 非空：

- 必须在该文档上继续撰写/审查
- 不允许重新创建第二份需求文档

## 5. Author Skill 触发规则

author 只在以下条件满足时发送 callback：

- 当前需求文档已经完成一轮有效收敛
- 当前内容足以进入 AI review
- author 不再需要继续私聊追问

author 不应在以下场景发送 callback：

- 只是补充一小段零散内容
- 问题仍明显不清晰
- reviewer 尚未返回到 author 的修改意见已处理完成前

author 还必须遵守：

- 如果 context 返回了 `document_url`，就在该文档继续撰写
- 只有当 `document_url` 为空时，才允许新建文档并在 callback 时回写新的 `document_url`

### 5.1 建议命令模板

```bash
python3 /path/to/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "$REQ_ID" \
  author-ready \
  --summary "需求文档已完成当前轮撰写，可进入 AI review。" \
  --document-url "$CURRENT_DOCUMENT_URL" \
  --document-version "${CURRENT_DOCUMENT_VERSION:-}" \
  --iteration-round "${ITERATION_ROUND:-1}"
```

### 5.2 Author Skill 伪代码

```python
if document_is_ready_for_ai_review():
    run_callback(
        mode="author-ready",
        req_id=req_id,
        summary="需求文档已完成当前轮撰写，可进入 AI review。",
        document_url=document_url,
        document_version=document_version,
        iteration_round=iteration_round,
    )
```

## 6. Reviewer Skill 触发规则

reviewer 只在流程节点发送 callback，不在普通 review 对话中的每条建议后都发。

强制规则：

- reviewer 的完成标准不是“输出了结论”，而是“输出了结论并成功调用了对应 callback”
- 如果 reviewer 已向用户给出正式结论，但没有 callback 到 Coordinator，这次 review 视为未完成
- callback 失败时，reviewer 必须明确告知“流程状态尚未更新”，不能让用户误以为已进入下一阶段

### 6.1 退回修改

适用条件：

- reviewer 已得出“当前文档仍需修改”的结论
- reviewer 已把修改意见交回 author
- 一旦给出这种正式结论，就必须立即发送 `review_returned_for_revision`

```bash
python3 /path/to/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "$REQ_ID" \
  review-event \
  --event review_returned_for_revision \
  --summary "AI review 未通过，已将修改意见返回 author。" \
  --review-notes-url "$CURRENT_REVIEW_NOTES_URL" \
  --document-url "$CURRENT_DOCUMENT_URL" \
  --review-result "needs_revision"
```

### 6.2 进入人工确认

适用条件：

- AI review 已通过
- reviewer 判断当前文档已可进入人工确认
- 一旦给出这种正式结论，就必须立即发送 `review_ready_for_human_confirmation`

```bash
python3 /path/to/send_openclaw_callback.py \
  --base-url "$COORDINATOR_BASE_URL" \
  --secret "$OPENCLAW_CALLBACK_SECRET" \
  --req-id "$REQ_ID" \
  review-event \
  --event review_ready_for_human_confirmation \
  --summary "AI review 已通过，可进入人工确认。" \
  --review-notes-url "$CURRENT_REVIEW_NOTES_URL" \
  --document-url "$CURRENT_DOCUMENT_URL" \
  --review-result "ai_ready"
```

### 6.3 Reviewer Skill 伪代码

```python
if review_requires_revision():
    notify_coordinator(
        event="review_returned_for_revision",
        review_summary="AI review 未通过，已将修改意见返回 author。",
    )
elif review_is_ai_ready():
    notify_coordinator(
        event="review_ready_for_human_confirmation",
        review_summary="AI review 已通过，可进入人工确认。",
    )
```

## 6.4 Reviewer 开始前的上下文确认

reviewer 在开始审查前，至少应确认：

- `status == AI_REVIEWING`
- `document_url` 非空
- `latest_review_summary` 与当前轮目标不冲突

如果状态不匹配，不应直接推进 callback。
如果 callback 未成功，不应把“已退回/已通过”的结论表达成已完成流转。

## 7. 失败处理

- `400`
  - skill payload 有问题，优先检查 event 和字段名
- `401`
  - secret、时间戳或签名不一致
- `404`
  - `REQ_ID` 不存在，通常是环境或需求号错误
- `500`
  - Coordinator 内部异常，建议记录原始响应并暂停自动重试

推荐策略：

- `400/401/404` 不自动无限重试
- `500` 可有限次重试
- 所有失败都要在 skill 日志中记录 `req_id`、event、response body
- 如果 callback 没成功，必须明确告诉用户：`Coordinator 尚未收到 review 结论，流程状态未更新`

## 8. 最小上线清单

- author 能发 `author_ready_for_ai_review`
- reviewer 能发 `review_returned_for_revision`
- reviewer 能发 `review_ready_for_human_confirmation`
- skill 环境已配置 `COORDINATOR_BASE_URL` 与 `OPENCLAW_CALLBACK_SECRET`
- 已做一轮真实 smoke test

只要以上 5 项完成，主流程就具备真实联调基础。
