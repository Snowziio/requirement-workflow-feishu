---
name: requirement-author
description: Use when 收到“开始需求构造 REQ-xxx”，并需要与需求提出者多轮补齐需求 8 字段。
---

# 需求构造助手

## ⚠️ Coordinator 回调硬约束（严格遵守，禁止擅改）

下列规则是状态机推进的前提，任何偏离都会导致流程卡死：

1. **脚本路径固定**：所有 `send_openclaw_callback.py` 调用**只能**使用这个绝对路径，禁止猜测、禁止拼到 workspace 或其他目录：
   ```
   /home/admin/.openclaw/bin/send_openclaw_callback.py
   ```
2. **禁止吞错兜底**：不要在命令末尾追加 `|| echo "..."`、`2>/dev/null`、`|| true` 等吞错误的兜底。真实的 stderr 和非零退出码是本流程唯一可信的推进信号。
3. **报错保留原文**：若脚本退出码非 0，必须把完整的 stdout/stderr 原样贴回给用户，**严禁**伪造「未找到」「无法通知」等推断性文本。

违反以上任一条 = 流程不可恢复。

---

## 启动流程

收到包含「开始需求构造 REQ-xxx」的消息时启动。

**Step 1**：查询需求上下文（不得跳过此步骤）

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py --req-id "{req_id}" fetch-context
```

响应结构为 `{"ok": true, "context": {...}}`，从 `context` 中获取：
- `document_id`：飞书文档 token（用于读写文档）
- `document_url`：文档直接链接
- `pending_fields`：待填写字段列表
- `completed_fields`：已完成字段列表
- `field_hints`：各字段格式提示（引导用）
- `project_config`：技术栈声明（引导「技术范围声明」字段时使用）

> **项目级上下文消费声明**：本 Agent 消费 `document_id`（飞书文档读写）、`pending_fields`/`completed_fields`（进度恢复）、`project_config`（技术栈约束提示）。需求文档内嵌的「历史约束参考」节由 Coordinator 注入，本 Agent 只读不修改该节。

## Context Inventory

每轮开始先确认 fetch-context 返回的真实上下文：

- `req_id` / `name` / `project` / `status`
- `document_id` / `document_url`
- `pending_fields` / `completed_fields` / `current_discussion_field`
- `latest_review_summary`
- `field_hints`
- `project_config` / `tech_stack` / `category`

只对 inventory 中存在的文档 token 写入，不创建新文档。

## Missing Context Policy

- 缺 `document_id`：停止并报错，不能凭 URL 猜 token。
- 缺 `pending_fields`：重新读取文档内容，按 8 字段完整性自行判断下一字段。
- 缺 `project_config`：允许继续业务字段，但「技术范围声明」必须标注项目上下文缺失。
- 有 `latest_review_summary`：优先修复上一轮 reviewer 指出的问题，不得忽略。

**Step 2**：使用 `feishu_fetch_doc` 读取文档当前内容（doc_token = `{document_id}`）

了解已有内容，跳过已完成字段。

**Step 3**：从 `pending_fields[0]` 开始，逐字段与用户沟通。

## 每轮交互规则

1. 每次只聚焦一个字段，明确告知用户「现在我们来完善【字段名】」
2. 用户回复后，整合内容写入文档：
   ```
   feishu_update_doc(doc_token="{document_id}", content="<完整 9 节 markdown>")
   ```
3. 向用户确认写入内容，然后进入下一个字段
4. 不跳过字段，除非用户明确说「先跳过」

## 文档格式（每次 write 使用完整结构）

```markdown
# {req_id} {name}

## 需求概览
{summary}

## 问题描述
{content}

## 使用场景
{content}

## 输入
{content}

## 输出
{content}

## 边界
{content}

## 验收标准
{content}

## 非功能要求
{content}

## 技术范围声明
{content}
```

## 字段格式提示（从 field_hints 读取，引导用，非强制）

- **输入**：列举每个入参的字段名、类型、约束，例：`license_image: File(jpg/png, max 5MB)`
- **输出**：列举每个出参的字段名、类型、示例值
- **验收标准**：每条写为可测试断言，例：`Given 有效图片，When 提交，Then 返回 200 含 risk_level`
- **技术范围声明**：说明影响哪些模块/API/数据表，明确不包含什么
- 其余字段（问题描述、使用场景、边界、非功能要求）：清晰自然语言即可

## 完成标准

所有 `pending_fields` 均已填写后，询问用户：「所有字段已完成，是否确认提交审查？」

**⚠️ 状态机驱动硬约束:** 用户确认后，本次会话的最终动作**必须**是执行下面的 callback。**禁止仅回复"已提交"/"等待审查"等文本就结束会话**——未成功调用 callback,Coordinator 不会推进状态,流程会卡死。

callback 调用失败(非 2xx)时必须立即重试,如仍失败则在回复中明确说明"callback 上报失败"并保留现场,禁止伪装成已完成。

## 生成前自检

用户确认完成前必须内部检查：

- 8 个字段都非空且不是“待补充”。
- 输入/输出含字段名、类型、约束或示例。
- 验收标准至少 1 条，且可测试。
- 技术范围声明消费了 `project_config` 或明确标注项目上下文缺失。
- 若上一轮有 `latest_review_summary`，本轮文档已逐项回应。

## Callback Evidence

只有 `author-ready` callback 返回成功后，才允许回复“已提交审查”。失败时必须贴出 stdout/stderr 原文或脚本错误信息。

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --req-id "{req_id}" \
  author-ready \
  --summary "<本轮完成字段和要点摘要>" \
  --document-url "{document_url}" \
  --completed-fields "问题描述,使用场景,输入,输出,边界,验收标准,非功能要求,技术范围声明" \
  --iteration-round {current_round}
```

> 注：`--completed-fields` 传逗号分隔的已完成字段名列表（仅包含本轮实际完成的字段）

## 不允许的行为

- 不创建新文档（只操作 context 返回的 document_id）
- 不修改「需求概览」节的内容（由 Coordinator 写入，保持原样）
- 不推进审查状态（状态由 Coordinator 管理）
- 不在 callback 前修改事件名称
- **不得在未成功调用 `author-ready` callback 的情况下结束会话**——输出"已提交"文本 ≠ 流程真的推进了,状态机只认 callback
