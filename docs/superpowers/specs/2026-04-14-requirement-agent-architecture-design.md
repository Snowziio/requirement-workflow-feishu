# 需求构造 Agent 架构优化设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化需求构造阶段的 Agent 架构——明确 Coordinator 边界（只做状态转移和 hook 触发）、将文档内容写入权归还 Author Agent、定义显式的 Agent 协议契约和审查维度，同时为未来迁移到 Claude Code Agent 预留接口定义。

**Architecture:** Coordinator 作为纯规则驱动的状态机，不持有文档内容；Author Agent 通过 `feishu_doc` skill 直接读写飞书文档；Review Agent 按 8 项显式维度审查；Agent 与 Coordinator 通过稳定的 HTTP callback + context query 协议对接。

**Tech Stack:** Python 3.11（Coordinator）、OpenClaw（Agent 运行时）、飞书 Docx API（via feishu-doc skill）、HTTP JSON callbacks

---

## 核心设计原则

### Coordinator 职责边界

**只做，且仅做：**
- 状态机（CREATED → DRAFTING → AI_REVIEW → HUMAN_CONFIRM → FINAL_REVIEW → APPROVED）
- 飞书通知（状态卡片、卡点卡片）——通知**人**，不触达 Agent
- Bitable 同步（结构化状态字段）
- 需求文档 shell 创建（生成 doc_id，之后不碰内容）

**不做：**
- 写入需求文档内容
- 触发 Agent（Agent 由用户通过飞书直接触达）
- 调用 AI

### Agent 触发机制

需求构造阶段所有 Agent 触发由**用户通过飞书主动触达 OpenClaw Agent** 完成。  
Coordinator 发给用户的飞书通知是「告知人」（下一步该做什么），不是「触达 Agent」。

### 未来迁移预留

Agent 协议（callback + context query HTTP 接口）是唯一的对接边界。  
未来迁移到 Claude Code Agent，只需新 Agent 实现同样的 callback 协议，Coordinator 零改动。  
不提前实现 AgentDispatcher 等抽象类——接口定义即契约。

---

## §1 Agent 协议定义

三个接口作为任何 Agent 运行时的对接契约。

### 1a. Context Query

```
GET /queries/openclaw/requirement-context
Body: { "req_id": "REQ-PROJ-001" }

Response 200:
{
  "req_id": "REQ-PROJ-001",
  "name": "登录功能",
  "project": "PROJ",
  "summary": "用户可以用邮箱登录",
  "status": "DRAFTING",
  "current_discussion_field": "输入",
  "completed_fields": ["问题描述", "使用场景"],
  "pending_fields": ["输入", "输出", "边界", "验收标准", "非功能要求", "技术范围声明"],
  "document_id": "docx_abc123",
  "document_url": "https://xxx.feishu.cn/docx/abc123",
  "field_hints": {
    "输入":       "列举每个入参的字段名、类型、约束，例：license_image: File(jpg/png, max 5MB)",
    "输出":       "列举每个出参的字段名、类型、示例值",
    "验收标准":   "每条写为可测试断言：Given [前置条件], When [动作], Then [期望结果]",
    "技术范围声明": "说明影响哪些模块/API/数据表，以及明确不包含什么"
  },
  "latest_review_summary": "...",
  "bitable_record_id": "rec_xyz"
}
```

**变更说明：** 新增 `field_hints`（提示性，不强制校验）。不返回字段实际内容——飞书文档是内容权威，Agent 直接读文档。

### 1b. Author Callback

```
POST /callbacks/openclaw/author-turn
Body:
{
  "req_id": "REQ-PROJ-001",
  "event": "author_submit",
  "summary": "本轮补全了输入输出和边界，验收标准待下轮",
  "completed_fields": ["问题描述", "使用场景", "输入", "输出"],
  "iteration_round": 2
}

Response 200:
{
  "ok": true,
  "req_id": "REQ-PROJ-001",
  "status": "DRAFTING",
  "current_discussion_field": "边界",
  "pending_fields": ["边界", "验收标准", "非功能要求", "技术范围声明"]
}
```

**变更说明：** 移除 `normalized_updates`（字段值）。Coordinator 只接收「哪些字段完成了」，内容已由 Author Agent 直写飞书文档。

### 1c. Review Callback

```
POST /callbacks/openclaw/review-result
Body:
{
  "req_id": "REQ-PROJ-001",
  "event": "ai_review_pass" | "ai_review_reject",
  "review_summary": "验收标准格式合规，技术范围声明清晰",
  "weak_fields": ["非功能要求"],
  "document_url": "https://xxx.feishu.cn/docx/abc123"
}
```

**不变**，现有结构已正确。

---

## §2 Coordinator 瘦身

### 移除

| 组件 | 原因 |
|---|---|
| `FeishuGateway.sync_requirement_document()` | 内容写入职责归 Author Agent |
| `RequirementDocumentCompiler.rewrite_sections()` | 同上 |
| `RequirementDocumentCompiler.refresh_derived_sections()` | 同上 |
| `Requirement.document: RequirementDocument` | Coordinator 不再维护内容副本 |
| `handle_author_turn` 中 `normalized_updates` 处理逻辑 | callback 不再传字段值 |

### 保留

| 组件 | 原因 |
|---|---|
| `FeishuGateway.create_requirement_document()` | Coordinator 负责创建文档 shell |
| `Requirement.document_id / document_url` | 状态元数据，传给 Agent 用 |
| `Requirement.completed_fields / pending_fields` | 状态元数据，从 callback 更新 |
| `RequirementDocumentCompiler`（仅保留 `render_markdown` 用于初始化） | 创建文档 shell 时生成初始结构 |

### 文档结构调整

需求文档只包含内容节（9 节），由 Author Agent 全权管理：

```markdown
# REQ-PROJ-001 登录功能

## 需求概览
## 问题描述
## 使用场景
## 输入
## 输出
## 边界
## 验收标准
## 非功能要求
## 技术范围声明
```

**移出文档**：「多轮讨论纪要」「AI Review结论」「人工Review结论」不再写入飞书文档。  
它们是工作流元数据，保留在 Coordinator 内部状态和 Bitable 字段中。

### `handle_author_turn` 简化后

```python
def handle_author_turn(self, requirement: Requirement, callback: AuthorCallbackPayload) -> Requirement:
    requirement.current_round += 1
    requirement.completed_fields = callback.completed_fields
    requirement.pending_fields = [
        f for f in DISCUSSION_FIELDS
        if f not in requirement.completed_fields
    ]
    requirement.current_discussion_field = (
        requirement.pending_fields[0]
        if requirement.pending_fields
        else DISCUSSION_FIELDS[-1]
    )
    requirement.latest_review_summary = callback.summary
    requirement.touch()
    return requirement
```

---

## §3 Author Agent 设计

**运行时**：OpenClaw（飞书 channel）  
**Skills**：`feishu-doc`（read/write）、HTTP fetch（context query + callback）

### 工具链

| 动作 | 工具 | 时机 |
|---|---|---|
| 拉取 REQ 上下文 | `web_fetch` GET `/queries/openclaw/requirement-context` | 会话开始，获取 field_hints / pending_fields / document_id |
| 读取当前文档 | `feishu_doc { action: "read" }` | 会话开始，了解已有内容 |
| 写入文档 | `feishu_doc { action: "write" }` | 每轮讨论后，整体替换文档内容 |
| 上报完成 | `web_fetch` POST `/callbacks/openclaw/author-turn` | 所有必填字段完成后 |

**选用 `write`（整文替换）而非 `update_block`**：Agent 控制完整文档结构，不依赖 block_id 持久性，避免块顺序错乱。

### Skill 定义（SKILL.md）

```markdown
---
name: requirement-author
description: 需求构造助手，协助需求提出者逐字段完善需求文档，完成后上报 Coordinator。
---

## 启动流程

收到「开始需求构造 REQ-PROJ-001」消息后（消息中含 context_query_url、callback_url）：

1. GET {context_query_url}
   → 获取 document_id、document_url、field_hints、pending_fields、completed_fields

2. feishu_doc { action: "read", doc_token: {document_id} }
   → 了解当前已有内容，跳过已完成字段

3. 从 pending_fields[0] 开始，逐字段与用户沟通

## 每轮交互规则

- 每次只聚焦一个字段
- 用户回复后：整合内容 → 写入文档 → 向用户确认 → 进入下一字段
- 写入：feishu_doc { action: "write", doc_token: ..., content: <完整 9 节 markdown> }
- 不跳过字段，除非用户明确说「先跳过」

## 字段格式提示（引导用，非强制）

**输入**：列举每个入参的字段名、类型、约束
  示例：`license_image: File(jpg/png, max 5MB)`

**输出**：列举每个出参的字段名、类型、示例值

**验收标准**：每条写为可测试断言
  示例：`Given 有效图片，When 提交，Then 返回 200 含 risk_level`

**技术范围声明**：说明影响哪些模块/API/数据表，明确不包含什么

其余字段（问题描述、使用场景、边界、非功能要求）：清晰自然语言即可

## 完成标准

所有 pending_fields 均已填写后，询问用户确认，然后：

POST {callback_url}/callbacks/openclaw/author-turn
{
  "req_id": "REQ-PROJ-001",
  "event": "author_submit",
  "summary": "<本轮完成的字段和要点摘要>",
  "completed_fields": ["问题描述", "使用场景", ...全部已完成字段],
  "iteration_round": <轮次>
}

## 不允许的行为

- 不创建新的需求文档（只在 document_id 对应的文档上操作）
- 不修改「需求概览」节（由 Coordinator 在创建时写入）
- 不推进状态（状态由 Coordinator 管理）
```

### 启动消息格式

Coordinator 在需求创建后发给用户的通知，用户将此消息转发给 Author Agent：

```
开始需求构造 REQ-PROJ-001
需求名称：登录功能
需求简述：用户可以用邮箱登录
context_query_url: https://<coordinator-host>/queries/openclaw/requirement-context?req_id=REQ-PROJ-001
callback_url: https://<coordinator-host>
文档直接链接：https://xxx.feishu.cn/docx/abc123
```

---

## §4 Review Agent 设计

**运行时**：OpenClaw（飞书 channel）  
**Skills**：`feishu-doc`（read）、HTTP fetch（context query + callback）

### 工具链

| 动作 | 工具 | 时机 |
|---|---|---|
| 读取需求文档 | `feishu_doc { action: "read" }` | 审查开始 |
| 拉取 REQ 上下文 | `web_fetch` GET `/queries/openclaw/requirement-context` | 获取 completed_fields、历史 review_summary |
| 上报审查结论 | `web_fetch` POST `/callbacks/openclaw/review-result` | 审查完成后 |

### 8 项审查维度

| 维度 | 检查内容 | 不通过结果 |
|---|---|---|
| 1. 字段完整性 | 所有 8 个 DISCUSSION_FIELDS 均非「待补充」 | **reject** |
| 2. 输入结构化 | 「输入」包含具体参数名+类型，非纯自然语言 | **reject** |
| 3. 输出结构化 | 「输出」包含返回字段名+类型 | **reject** |
| 4. 验收标准可测试 | 每条 AC 为条件-动作-期望结构，非模糊目标 | **reject** |
| 5. 边界覆盖 | 包含至少一个异常/错误场景 | **warn**（记入 summary） |
| 6. 非功能量化 | 若有性能声明，包含可量化指标（P99/百分比） | **warn** |
| 7. 技术范围声明 | 「技术范围声明」非空，含模块/API/数据表信息 | **reject** |
| 8. 内部一致性 | AC 中使用的字段与「输入」定义一致，无矛盾 | **reject** |

**阻断（→ reject）**：维度 1/2/3/4/7/8 任一不通过  
**警告（→ pass with note）**：维度 5/6

### Skill 定义（SKILL.md）

```markdown
---
name: requirement-reviewer
description: 需求审查助手，按 8 项维度审查需求文档质量，单次上报 pass/reject 结论，不与用户多轮沟通。
---

## 启动流程

收到审查任务（含 req_id 和 document_url）后：

1. feishu_doc { action: "read", doc_token: {document_id} }
2. GET {context_query_url}?req_id={req_id}
3. 按 8 项维度逐一检查（见下方定义）

## 8 项审查维度

维度 1：字段完整性 → 不通过：reject，指出空缺字段
维度 2：输入结构化 → 不通过：reject，说明需参数化
维度 3：输出结构化 → 不通过：reject，同上
维度 4：验收标准可测试 → 不通过：reject，标出不可测条目
维度 5：边界覆盖 → 不通过：记入 weak_fields，仍可 pass
维度 6：非功能量化 → 不通过：记入 weak_fields，仍可 pass
维度 7：技术范围声明 → 不通过：reject（Spec 生成必要输入）
维度 8：内部一致性 → 不通过：reject，指出冲突点

## 输出

POST {callback_url}/callbacks/openclaw/review-result
{
  "req_id": "REQ-PROJ-001",
  "event": "ai_review_pass" | "ai_review_reject",
  "review_summary": "<整体结论一句话，含具体问题或通过原因>",
  "weak_fields": ["非功能要求"],
  "document_url": "{document_url}"
}

## 不允许的行为

- 不修改需求文档
- 不与用户多轮沟通（单次审查，直接上报）
- 不推进人工确认或正式审查
```

---

## §5 需求文档模板定稿

### 设计原则

需求文档是**人读的**，不是机器消费的格式。最小格式约束，自然语言友好。  
结构化约束在 Spec 转化阶段（卡点1a 人工+AI 多轮沟通）处理，不在文档构造阶段强制。

### 9 节固定结构

```markdown
# {req_id} {name}

## 需求概览
{summary}（由 Coordinator 创建时写入，Author Agent 不修改）

## 问题描述
（自然语言，描述待解决的问题）

## 使用场景
（自然语言，描述用户角色和典型操作路径）

## 输入
（引导格式：字段名: 类型(约束)，每行一个参数）

## 输出
（引导格式：字段名: 类型，示例值）

## 边界
（包含什么，不包含什么，异常情况处理）

## 验收标准
（引导格式：Given [前置条件], When [动作], Then [期望结果]，每条一行）

## 非功能要求
（响应时间/可用性/并发/数据安全等，有指标写指标）

## 技术范围声明
（影响哪些模块/API/数据表；明确不包含什么）
```

### 初始化写入（Coordinator 一次性操作）

需求创建时，Coordinator 调用 `create_requirement_document()` 生成 doc_id 后，**一次性写入 9 节初始 shell**（需求概览填入 summary，其余节写「待补充」）。此后 Coordinator 不再碰文档内容，由 Author Agent 接管。

此次写入通过 `FeishuGateway.write_document_initial_shell(doc_id, requirement)` 实现，是文档 shell 创建的组成部分，不属于「内容管理」。

### 移出文档的内容

| 原字段 | 新位置 |
|---|---|
| 多轮讨论纪要 | Coordinator 内部状态（`discussion_history`） |
| AI Review结论 | Coordinator 内部状态（`review_history`）+ Bitable |
| 人工Review结论 | Coordinator 内部状态（`human_review_history`）+ Bitable |

---

## §6 实施顺序

1. **Coordinator 协议层**：更新 context query response（加 `field_hints`）、更新 author callback handler（移除 `normalized_updates`）
2. **Coordinator 瘦身**：移除 `sync_requirement_document` 调用链，简化 `handle_author_turn`，移除 `Requirement.document` 维护逻辑
3. **Author Agent Skill**：按 §3 定义写 SKILL.md，在 OpenClaw 部署
4. **Review Agent Skill**：按 §4 定义写 SKILL.md，在 OpenClaw 部署
5. **回归验证**：走完一个完整需求创建→构造→审查→通过流程

---

## 附：未来迁移 Claude Code Agent 时需要做的事

- 新 Agent 实现 §1 定义的 callback + context query 协议
- Coordinator 零改动
- 启动消息格式（§3 中的文本块）可以直接作为 Agent 的初始 prompt
