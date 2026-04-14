# Spec 阶段 Coordinator 扩展 — 设计文档

**日期**：2026-04-14  
**状态**：待实现  
**关联子项目**：Sub-project A

---

## 目标

在需求工作流 APPROVED 之后，新增 Spec 阶段（SPEC_DRAFTING → SPEC_LOCKED），由 Spec Agent 撰写技术规格文档，Spec Reviewer 自动审查，审查通过后发卡点1a 通知卡。全流程无需人工干预即可完成。

---

## 架构概述

```
APPROVED
  │
  │ Coordinator 发飞书消息给 Spec Agent
  ▼
SPEC_DRAFTING  ◄──── Spec Agent spec_submit + Reviewer reject
  │
  │ Reviewer ai_review_pass
  ▼
SPEC_LOCKED  ──► 发卡点1a 通知卡到项目群
```

- Coordinator 是中枢，不写文档内容，只管状态转换和消息路由
- Spec Agent 主动调 spec_start callback 正式开始，调 spec_submit 提交
- Coordinator 在 spec_submit 后自动发消息给 Spec Reviewer Agent（Option 2：Feishu IM 触发）
- Reviewer 复用现有 review-result 端点，Coordinator 按 status 区分处理分支

---

## 项目级上下文契约

> 遵循 [context-chain-principle.md](../../context/infra/context-chain-principle.md) 规定的五问格式。

### 消费（来自需求层）

| 上下文产物 | 来源 | 读取机制 |
|-----------|------|---------|
| requirement_document_url | Coordinator state（APPROVED 时已存） | spec_start 响应中直接返回 |
| 需求文档 8 字段 | 飞书需求文档 | Spec Agent 调 feishu_fetch_doc |
| latest_review_summary | Coordinator state | fetch-context 接口 |
| ARCHITECTURE.yaml | GitHub 仓库 | Spec Agent 通过 GitHub API 读取 |
| tech_stack（技术栈） | Coordinator state（project_config） | spec_start 响应或 fetch-context 返回 |

### 产出（传递给下层）

| 上下文产物 | 内容 | 存储位置 | 更新策略 |
|-----------|------|---------|---------|
| Spec 文档（9节） | 技术规格，含架构设计节与上下文消费声明 | 飞书文档（spec_document_id） | 逐节覆盖写，SPEC_LOCKED 后不可修改 |
| spec_document_url | Spec 飞书文档 URL | Coordinator state | spec_start 后写入 |
| spec_review_summary | 最近一次 Spec 审查结论 | Coordinator state | 每次审查完成后更新 |

### 终止

| 上下文产物 | 终止原因 |
|-----------|---------|
| discussion_history（需求讨论记录） | 需求层内部记录，Spec 层不需要 |
| human_confirm_notes | 已吸收进需求文档，无需再传递 |

### 防漂移验证

| Review 维度 | 验证内容 | 类型 |
|------------|---------|------|
| 需求字段全覆盖 | Spec 9节与需求文档 8 字段一一对应 | 阻断 |
| 上下文消费声明完整性 | 架构设计节中「项目级上下文消费声明」子节非空 | 阻断 |

---

## Section 1：状态机 & 数据模型

### 新增 WorkflowStatus

```python
SPEC_DRAFTING = "SPEC_DRAFTING"
SPEC_LOCKED   = "SPEC_LOCKED"
```

### 状态转换规则

| 当前状态 | 事件 | 下一状态 |
|---------|------|---------|
| APPROVED | Coordinator 自动通知 Spec Agent（无 callback） | — |
| APPROVED | Spec Agent 调 spec_start | SPEC_DRAFTING |
| SPEC_DRAFTING | Spec Agent 调 spec_submit | SPEC_DRAFTING（等待 Review） |
| SPEC_DRAFTING | Reviewer ai_review_pass | SPEC_LOCKED |
| SPEC_DRAFTING | Reviewer ai_review_reject | SPEC_DRAFTING（Coordinator 通知 Spec Agent 修改） |

### Requirement 新增字段

```python
spec_document_id: str = ""      # 飞书 Spec 文档 token
spec_document_url: str = ""     # 飞书 Spec 文档 URL
spec_review_summary: str = ""   # 最近一次 Spec Review 结论
```

---

## Section 2：Callback 协议

### 新端点：POST /callbacks/openclaw/spec-turn

#### event: spec_start

**请求**：
```json
{
  "req_id": "REQ-xxx",
  "event": "spec_start",
  "summary": "开始撰写 Spec"
}
```

**Coordinator 行为**：
1. 校验 requirement.status == APPROVED
2. 调 gateway.create_spec_document(req) → 拿到 spec_document_id / spec_document_url
3. 更新 requirement：status → SPEC_DRAFTING，写入 spec_document_id / spec_document_url
4. 更新 Bitable 记录

**返回**：
```json
{
  "ok": true,
  "spec_document_id": "...",
  "spec_document_url": "...",
  "requirement_document_url": "...",
  "req_id": "REQ-xxx",
  "status": "SPEC_DRAFTING"
}
```

#### event: spec_submit

**请求**：
```json
{
  "req_id": "REQ-xxx",
  "event": "spec_submit",
  "summary": "Spec 初稿完成，8节均已填写",
  "spec_document_url": "https://..."
}
```

**Coordinator 行为**：
1. 校验 requirement.status == SPEC_DRAFTING
2. 更新 spec_review_summary = summary（暂存）
3. 发飞书消息给 Spec Reviewer Agent：`gateway.send_text(settings.spec_reviewer_feishu_id, _build_spec_review_handoff(req))`
4. 更新 Bitable

**返回**：
```json
{ "ok": true, "message": "已通知 Spec Reviewer 开始审查" }
```

### 复用端点：POST /callbacks/openclaw/review-result

Reviewer 使用完全相同的 event 名（`ai_review_pass` / `ai_review_reject`）。Coordinator 在 `submit_review_event_payload` 里按 status 分支处理：

```python
if requirement.status == WorkflowStatus.SPEC_DRAFTING:
    if event == "ai_review_pass":
        requirement.status = WorkflowStatus.SPEC_LOCKED
        # 发卡点1a通知卡到项目群
    else:  # ai_review_reject
        requirement.spec_review_summary = payload.review_summary
        # 发消息给 Spec Agent：请根据以下意见修改
elif requirement.status == WorkflowStatus.AI_REVIEW:
    # 原有需求 review 分支，不变
```

### Context Query 扩展

`/queries/openclaw/requirement-context` 返回新增字段：

```json
{
  "spec_document_id": "...",
  "spec_document_url": "...",
  "spec_review_summary": "..."
}
```

---

## Section 3：Spec 文档模板 & Agent SKILL

### Spec 文档固定模板（9节）

```markdown
# {req_id} {name} — 技术规格

## 背景与目标
（对应需求：问题描述 + 使用场景）

## API 入参定义
（对应需求：输入）
| 字段名 | 类型 | 约束 | 说明 |

## API 出参定义
（对应需求：输出）
| 字段名 | 类型 | 示例值 | 说明 |

## 异常处理与边界条件
（对应需求：边界）

## 测试策略
（对应需求：验收标准）
每条 AC → 对应测试用例（Given/When/Then）

## 性能与可用性指标
（对应需求：非功能要求，必须含量化数值）

## 实现范围
（对应需求：技术范围声明）
影响模块/API/数据表；明确 in/out of scope

## 架构设计

### 顶层架构背景

（说明本需求在整体系统架构中的位置。参考 ARCHITECTURE.yaml，描述：
- 涉及哪些已有服务/模块
- 本次变更在架构上属于新增、扩展还是改造
- 与相邻系统的交互边界）

### 项目级上下文消费声明

（列出本 Spec 明确消费了哪些项目级上下文，确保下游层可追溯。）

| 上下文产物 | 版本/来源 | 影响本 Spec 的哪些判断 |
|-----------|---------|----------------------|
| ARCHITECTURE.yaml | {commit_sha 或 日期} | 架构接合点选择、复用模块确认 |
| ACM 注册表（历史约束） | {snapshot 日期} | 兼容性分析，是否与已有 AC 冲突 |
| 设计系统快照 | {snapshot 日期，仅 needs_ui=true} | UI 组件选择、交互规范对齐 |

### 关键架构决策

（记录本次实现中的关键技术判断，说明"为什么这样做"。每条决策至少包含：
- **决策**：选了什么方案
- **依据**：为何选这个（来自上层约束、性能要求、历史约束等）
- **影响**：对 ARCHITECTURE.yaml 的变更，或对未来需求的约束）

示例：
- **决策**：将 X 逻辑放入现有 Y 服务，而非新建服务
  **依据**：ARCHITECTURE.yaml 中 Y 服务已有 Z 能力，拆新服务会增加跨服务调用
  **影响**：Y 服务 ARCHITECTURE.yaml 新增接口 /api/v1/... 需在实现后更新

### 存储与数据流设计

（描述数据的流向和存储：
- 输入从哪里来（API 参数 / 消息队列 / 定时任务）
- 处理在哪个层发生（Service / Repository / Gateway）
- 写入哪些存储（数据表 / 缓存 / 外部 API）
- 输出如何返回（同步响应 / 异步通知 / Webhook））

## 数据模型
新增或变更的表结构 / 数据模型定义
```

### Spec Reviewer 6+2+1 审查维度

**阻断维度（任一不通过则 reject）**

1. **需求字段全覆盖**：9节均非空，且能与需求文档各字段对应
2. **API 具体性**：入参/出参有字段名+类型，无「返回成功」等模糊描述
3. **测试用例与 AC 对齐**：每条需求验收标准有对应测试用例
4. **实现范围无歧义**：明确哪些模块改/不改，无「可能涉及」类表述
5. **数据模型存在性**：涉及存储变更的需求必须有表/模型定义
6. **内部一致性**：API 入参与测试用例中使用的字段名一致，无矛盾
7. **上下文消费声明完整性**：架构设计节中「项目级上下文消费声明」子节非空，至少列出 ARCHITECTURE.yaml 消费记录

**警告维度（不通过记入 weak_fields，仍可 pass）**

7. **性能指标量化**：非功能要求有具体数字（P99 < Xs / QPS > N / 可用性 99.x%）
8. **风险点识别**：至少一个技术风险 + 应对策略

### docs/agents/spec-author/SKILL.md 要点

- 启动触发词：「开始 Spec 撰写 REQ-xxx」
- Step 1：调 spec_start callback，从返回值拿 spec_document_id 和需求文档 URL（不得跳过）
- Step 2：feishu_fetch_doc 读需求文档，提取 8 个字段内容；同时读取 fetch-context 返回的 `architecture_yaml_url`（ARCHITECTURE.yaml 链接）供架构设计节使用
- Step 3：逐节填写 Spec（每节完成后 feishu_update_doc 写入完整文档）；**架构设计节必须包含「项目级上下文消费声明」子节，填写已读取的 ARCHITECTURE.yaml 版本和 ACM 快照信息**
- Step 4：9节均完成后调 spec_submit callback
- 约束：不修改需求文档；不跳过任何节；「数据模型」节无数据库变更时填「无」；「项目级上下文消费声明」不得为空

### docs/agents/spec-reviewer/SKILL.md 要点

- 启动触发词：「开始 Spec 审查 REQ-xxx」
- Step 1：fetch-context 拿 spec_document_id + requirement_document_url（不得跳过）
- Step 2：feishu_fetch_doc 读 Spec 文档 + 需求文档
- Step 3：按 6+2+1 维度逐一检查（第7条：「项目级上下文消费声明」子节非空 → 阻断）
- Step 4：单次上报，不与用户多轮沟通
- 约束：不修改文档；event 只能是 ai_review_pass 或 ai_review_reject

---

## Section 4：卡点1a 通知卡 & 配置

### 卡点1a 卡片（SPEC_LOCKED 时发到项目群）

```
┌──────────────────────────────────────────────┐
│ 🟢  REQ-xxx Spec 已锁定                       │
├──────────────────────────────────────────────┤
│ 需求名称    {name}                            │
│ Spec 结论   {spec_review_summary}            │
├──────────────────────────────────────────────┤
│ [查看需求文档]  [查看 Spec 文档]               │
└──────────────────────────────────────────────┘
```

- 通知性卡片，无需人工点击放行
- 两个跳转按钮：需求文档 URL + Spec 文档 URL

### 新增 Settings 字段

```python
openclaw_spec_agent_name: str = "Spec 撰写助手"
spec_agent_feishu_id: str = ""       # Spec Agent 飞书 open_id，发消息触发用
spec_reviewer_feishu_id: str = ""    # Spec Reviewer 飞书 open_id，spec_submit 后触发用
```

### staging.yml 新增 env

```yaml
OPENCLAW_SPEC_AGENT_NAME=${{ secrets.OPENCLAW_SPEC_AGENT_NAME || 'Spec 撰写助手' }}
SPEC_AGENT_FEISHU_ID=${{ secrets.SPEC_AGENT_FEISHU_ID }}
SPEC_REVIEWER_FEISHU_ID=${{ secrets.SPEC_REVIEWER_FEISHU_ID }}
```

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `models.py` | 修改 | 新增 SPEC_DRAFTING / SPEC_LOCKED；Requirement 新增 3 字段 |
| `state_machine.py` | 修改 | 新增 Spec 阶段相关 Event 和转换规则 |
| `coordinator_service.py` | 修改 | 新增 submit_spec_event_payload；submit_review_event_payload 加 Spec 分支 |
| `service_app.py` | 修改 | 新增 /callbacks/openclaw/spec-turn 端点；APPROVED 通知加发 Spec Agent 消息；卡点1a 卡片；_build_spec_review_handoff |
| `feishu_gateway.py` | 修改 | 新增 create_spec_document |
| `store.py` | 修改 | 新增 3 个 spec 字段的 load/save |
| `config.py` | 修改 | 新增 3 个 settings 字段 |
| `.github/workflows/staging.yml` | 修改 | 新增 3 个 env 变量 |
| `docs/agents/spec-author/SKILL.md` | 新建 | Spec Agent 启动流程和约束 |
| `docs/agents/spec-reviewer/SKILL.md` | 新建 | Spec Reviewer 6+2 维度和约束 |
| `tests/test_spec_stage.py` | 新建 | Spec 阶段状态机和 callback 测试 |
