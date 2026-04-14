# 需求层实现规格

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §4.1 需求层的实现细节文档。
> 描述具体的状态机转移表、双闸门约束、Hook 契约、需求文档格式、Bitable 字段、UI 两阶段实现等。
>
> **参考实现**：`Snowziio/requirement-workflow-feishu`（以参考实现为最终权威，本文与参考实现冲突时以参考实现为准）

---

## 项目级上下文契约

> 遵循 [infra/context-chain-principle.md](../infra/context-chain-principle.md) 规定的五问格式。

### 消费（来自上层 / 基础设施）

| 上下文产物 | 来源 | 读取机制 |
|-----------|------|---------|
| project_config（技术栈声明） | Coordinator state | fetch-context 接口 |
| ARCHITECTURE.yaml（现有模块列表） | GitHub 仓库 | GitHub API（技术范围声明节填写参考） |
| ACM 注册表（历史验收约束） | GitHub 仓库 | Coordinator 在创建文档时自动注入「历史约束参考」节 |

### 产出（传递给下层）

| 上下文产物 | 内容 | 存储位置 | 更新策略 |
|-----------|------|---------|---------|
| 需求文档 8 字段 | 问题描述/使用场景/输入/输出/边界/验收标准/非功能要求/技术范围声明 | 飞书文档（document_id） | 每轮 onExit(DRAFTING) section-rewrite |
| req_id | 需求唯一编号 REQ-{PROJECT}-{NNN} | Coordinator state + Bitable | 创建时写入，不可变 |
| needs_ui | 是否涉及 UI | Coordinator state + Bitable | 创建时写入，APPROVED 前可修改 |
| latest_review_summary | 最近一次 AI 审查结论 | Coordinator state + Bitable | 每次审查完成后更新 |

### 终止（不向下传递）

| 上下文产物 | 终止原因 |
|-----------|---------|
| discussion_history（逐轮讨论记录） | 需求层内部记录，Spec 层只需要最终的 8 字段，不需要讨论过程 |
| human_confirm_notes（人工确认意见） | 最终产物已经过 review，意见已被吸收进需求文档 |

### 防漂移验证

| Review 维度 | 验证内容 | 类型 |
|------------|---------|------|
| 字段完整性 | 8 个字段均非「待补充」且有实质内容 | 阻断 |
| 输入结构化 | 输入包含字段名 + 类型，非纯自然语言 | 阻断 |
| 输出结构化 | 输出包含字段名 + 类型，非「返回成功」等模糊描述 | 阻断 |
| 验收标准可测试 | 每条 AC 为 Given/When/Then 格式，无模糊目标 | 阻断 |
| 技术范围声明存在性 | 技术范围声明节非空，含具体模块/API/数据表信息 | 阻断 |
| 内部一致性 | 输入字段与验收标准使用的字段名自洽，无矛盾 | 阻断 |

---

## 一、状态机完整转移表

### 状态转移表（6 态）

| 当前状态 | 事件 | 目标状态 | 触发条件 |
|---|---|---|---|
| CREATED | create_requirement | DRAFTING | 无条件 |
| DRAFTING | author_submit | AI_REVIEW | 无条件（由 Author Agent 判断是否提交） |
| AI_REVIEW | ai_review_reject | DRAFTING | ai_ready = false |
| AI_REVIEW | ai_review_pass | HUMAN_CONFIRM | ai_ready = true |
| HUMAN_CONFIRM | human_confirm_no | DRAFTING | 无条件 |
| HUMAN_CONFIRM | human_confirm_yes | FINAL_REVIEW | human_confirmed = true |
| FINAL_REVIEW | final_review_pass | APPROVED | 无条件 |
| FINAL_REVIEW | final_review_reject | DRAFTING | 无条件 |

> 注：DISCUSSION_ROUTING 状态在参考实现中已合并进创建流程（Coordinator 创建需求后直接私信 author，author 在私聊发送启动指令后即进入 DRAFTING），不单独成状态。

### 状态 canonical 名与含义

**需求层主状态（6 态，本文及所有 docs/context/** 文档统一使用这组名称；代码中历史遗留的 `DISCUSSING` / `AI_REVIEWING` / `HUMAN_CONFIRMING` / `REVIEWING` 为别名，字符串值已对齐 canonical）**：

| 状态 | 含义 |
|---|---|
| CREATED | 需求刚建出，尚未开始讨论 |
| DRAFTING | Author 与 Author Agent 讨论、持续撰写 |
| AI_REVIEW | Reviewer Agent 审查中 |
| HUMAN_CONFIRM | 提出人确认 AI 审查结论 + 可选 UI 设计一阶段 |
| FINAL_REVIEW | 正式审查（人工卡点） |
| APPROVED | 需求定稿，规格层可启动 |

事件名以参考实现 `Event` 枚举为准：`author_submit`、`ai_review_reject`、`ai_review_pass`、`human_confirm_yes`、`human_confirm_no`、`final_review_pass`、`final_review_reject`。

> 代码兼容性注意：`src/requirement_workflow_v12/models.py` 的 `WorkflowStatus` 枚举同时保留 `DISCUSSING` / `AI_REVIEWING` / `HUMAN_CONFIRMING` / `REVIEWING` / `REQ_APPROVED` / `DISCUSSION_ROUTING` 作为历史别名（枚举成员字符串值与 canonical 一致），用于向后兼容旧调用点；新代码与文档一律使用 canonical 名。

---

## 二、双闸门约束（状态机层硬编码）

双闸门约束属于 Workflow Service 层的职责，必须在状态机中硬编码，不能下沉到 Hook 层。

```
约束 1（AI Ready 前置）：
  if event == human_confirm_yes and ai_ready == false:
    → 拒绝转移，保持 HUMAN_CONFIRM
    → 原因：「AI Ready 未满足，需先通过 AI 审查」

约束 2（Human Confirmed 前置）：
  if event == final_review_pass and human_confirmed == false:
    → 拒绝转移，保持 FINAL_REVIEW
    → 原因：「Human Confirmed 未满足，不能批准需求」
```

| 闸门 | 判定者 | 存储字段 | 满足条件 |
|---|---|---|---|
| AI Ready | Reviewer Agent | Bitable `AI Ready` (bool) | 8 字段全部有实质内容 + 完整性/一致性/可测试性/技术范围非空 全部通过 |
| Human Confirmed | Author（需求发起人） | Bitable `Human Confirmed` (bool) | 私聊中主动确认（human_confirm_yes 事件） |

---

## 三、Hook 实现层 ↔ 能力层契约

每个 Hook 的输入/输出契约如下。Workflow Service 不感知 Hook 内部实现，Hook 不感知状态机实现。

### onEnter(DRAFTING)

**触发时机**：每次进入 DRAFTING 状态，以及每条 author 私聊消息到达时

| | 内容 |
|---|---|
| **输入** | 当前需求快照（所有已填字段）+ 当前讨论进度（已完成字段 / 待补字段 / 当前轮次）+ 本轮 author 发言 |
| **输出** | 下一个要问的字段 / 下一句引导语 / 是否等待用户（bool） |
| **能力层** | OpenClaw Author Agent（requirement-writer Skill） |
| **失败处理** | Hook 层重试最多 2 次，超限记录到 Bitable 追溯字段，推送错误提示给 author |

### onEnter(AI_REVIEW)

**触发时机**：author_submit 事件触发状态迁移到 AI_REVIEW 时

| | 内容 |
|---|---|
| **输入** | 完整需求快照（所有讨论字段 + 最近一轮变更 diff）+ 历史约束参考（从 ACM 注册表拉取） |
| **输出** | `ai_ready: bool` + 结论摘要 + 维度打分（完整性 / 一致性 / 可测试性 / 技术范围 / 历史冲突） |
| **能力层** | OpenClaw Reviewer Agent（requirement-reviewer Skill） |
| **失败处理** | 重试 2 次，超限则 ai_ready = false，触发 ai_review_reject，原因「Reviewer Agent 调用失败，请人工介入」 |

### onEnter(HUMAN_CONFIRM)

**触发时机**：ai_review_pass 事件触发状态迁移到 HUMAN_CONFIRM 时

执行顺序：
1. 组装 AI 审查结论（结构化文字）
2. 若 `needs_ui = true`，调 UI 设计 Agent 生成低保真线框图，写入飞书文档
3. 把「审查结论 + 线框图链接（如有）」推送到 author 私聊
4. 等待 author 响应（human_confirm_yes / human_confirm_no）

| | 内容 |
|---|---|
| **输入（UI 设计部分）** | 完整需求快照（8 字段） |
| **输出（UI 设计部分）** | 低保真线框图（组件树 + 主要交互逻辑说明），写入飞书文档 |
| **能力层** | OpenClaw UI 设计 Agent（ui-design-bridge Skill） |

### onExit(DRAFTING)

**触发时机**：author_submit 事件（DRAFTING → AI_REVIEW 转移时）

1. 将所有讨论字段同步写入 Bitable 进度字段
2. 调用飞书 Docx API，按 section 幂等重写需求文档

### onEnter(FINAL_REVIEW)

**触发时机**：human_confirm_yes 事件（HUMAN_CONFIRM → FINAL_REVIEW 转移时）

向项目群发送正式审查卡片，包含：需求文档链接 + 审查结论摘要 + UI 设计稿链接（如有）+ [通过] [打回] 按钮。

---

## 四、需求文档格式规范

### 模板结构

```markdown
# REQ-{ID} {需求名称}
> 创建人: {人员} | 创建时间: {日期} | 状态: {状态}

## 历史约束参考（只读，系统注入）
[由 Coordinator 从 ACM 注册表自动拉取，列出可能受影响的历史验收标准。作者不得手动编辑本节。]

## 问题描述
这个功能解决什么业务问题？（自然语言描述）

## 使用场景
用户在什么情况下触发，期望得到什么结果？

## 输入
每条输入包含：字段名 + 类型 + 主要约束。
示例：
  - license_image: 图片文件，支持 jpg/png，最大 5MB
  - credit_report: JSON 对象，包含 applicant_id（string）和 credit_score（number，0-850）

## 输出
每条输出包含：字段名 + 类型 + 可能值。
示例：
  - risk_level: enum（low / medium / high）
  - score: integer（0-100）
  - report_id: string（UUID 格式）

## 边界（不包含什么）
明确排除的功能范围。

## 验收标准
每条格式：给定[前提条件]，当[触发动作]，系统应[可观测结果]。
示例：
- 给定有效营业执照图片（jpg，< 5MB）和完整征信数据，提交风控请求，响应 risk_level 字段存在且值为 low / medium / high 之一
- 给定缺失 credit_score 的征信数据，提交风控请求，返回 HTTP 422，body.error_code = MISSING_CREDIT_SCORE

## 非功能要求
性能（含数值）、安全、合规等约束。示例：P99 响应时间 < 3s；数据不出境。

## 技术范围声明
  - 涉及现有模块：[从 ARCHITECTURE.yaml 模块列表选取，或填"无"]
  - 操作类型：新增接口 / 修改现有接口 / 纯数据处理（必填）
  - 数据持久化：是 / 否（是否需要新增或修改数据表）
  - 对外依赖：[调用哪些第三方服务，无则填"无"]
```

### Section-rewrite 规则

需求文档在每轮 `onExit(DRAFTING)` 时同步。**必须遵守以下规则，不可例外**：

1. 每个 section 有稳定的 H2 标题锚点（`## 问题描述`、`## 使用场景`等）
2. 每次写回只替换该 section 的内容，不追加、不全删重建
3. section 不存在时新建在固定位置；存在时原地覆盖
4. 写回操作幂等：同一内容写多次结果一致

**违反后果**：全删重建会抹掉人工在文档里添加的注解，破坏信任。这条规则没有例外情况。

### Reviewer Agent 退回条件（Reviewer 必须退回，不能放行）

- 输入/输出仍为纯自然语言描述（无字段名）
- 验收标准无法被理解为"给定输入 → 期望输出"格式
- 技术范围声明为空（涉及现有模块 / 操作类型 / 数据持久化三项任意为空）
- 验收标准中有含糊词（"系统应合理处理"、"系统应及时响应"，无具体数值或可观测结果）

---

## 五、Bitable 需求追踪表字段

### 生命周期字段

| 字段 | 类型 | 说明 |
|---|---|---|
| req_id | 文本（主键） | `REQ-{PROJECT}-{NNN}` |
| 名称 | 文本 | 需求名称 |
| 项目 | 单选 | 项目代号 |
| 状态 | 单选 | **需求层主状态（6 态）**：CREATED / DRAFTING / AI_REVIEW / HUMAN_CONFIRM / FINAL_REVIEW / APPROVED。规格层 Spec 子状态（SPEC_DRAFTING / SPEC_LOCKED）在 APPROVED 后由 Spec 子状态机承接，不占用本字段。Harness / Impl / CI / 部署层进度由 checkpoint-handler 与 GitHub PR 状态承接，不进入本字段。 |
| 创建人 | 人员 | |
| 创建时间 | 日期 | |
| 需求文档 | 链接 | 飞书文档 URL |
| 审查报告 | 链接 | 飞书文档 URL |
| Spec 版本 | 数字 | 1, 2, ... |
| Spec PR | 链接 | GitHub PR URL |
| Harness PR | 链接 | GitHub PR URL |
| Impl PR | 链接 | GitHub PR URL |
| 当前卡点 | 单选 | 无 / 1a / 1b / 2 / 3 |
| 卡点1a 时间 | 日期 | |
| 卡点1b 时间 | 日期 | |
| 卡点2 时间 | 日期 | |
| 卡点3 时间 | 日期 | |
| 备注 | 文本 | 打回原因 / 阻塞说明 |

### 会话状态字段（v1.3 新增）

- **进度类**：当前阶段 / 当前轮次 / 当前讨论字段 / 已完成字段 / 待补字段
- **归属类**：当前 Owner / 当前接手角色
- **闸门类**：AI Ready（bool）/ Human Confirmed（bool）
- **追溯类**：最近一次 review 结论 / 最近一次提问 / 最近一次写回时间
- **UI 类**：needs_ui（bool）/ UI设计稿链接（text）/ 高保真原型链接（text）

**命名权威**：字段真相源为仓库根目录 `bitable_schema_v12.json`。任何字段新增/重命名/类型变更，必须先修改该 schema，再同步更新 Coordinator 写入映射、Bitable 建表脚本、Agent 字段契约。禁止绕过 schema 单独修改。

---

## 六、UI 设计两阶段详细实现

### 第一阶段：低保真线框图（HUMAN_CONFIRM）

**触发**：状态进入 HUMAN_CONFIRM 且 `needs_ui = true`

**UI 设计 Agent 调用规格**：

| | 内容 |
|---|---|
| **输入** | 需求文档 8 字段（含技术范围声明） |
| **输出** | 低保真线框图描述（Markdown 格式）：① 页面列表 ② 每个页面的主要元素布局 ③ 关键交互说明 ④ 各状态说明（空态/加载/错误/成功） |
| **交付** | 写入飞书文档（需求文档下的"UI 设计草稿"节），更新 Bitable `UI设计稿链接` |

**低保真不要求**：精确的视觉样式、组件代码、与设计系统一致

**低保真必须包含**：所有关键视图的元素布局、所有关键状态的行为说明

### 第二阶段：高保真可运行原型（APPROVED 后）

**触发**：REQ APPROVED 且 `needs_ui = true`

**输入清单**：
1. 需求文档 8 字段
2. 第一阶段低保真线框图（飞书文档链接）
3. 项目设计系统文档（Coordinator 从飞书读取，注入最新版本）

**AI 生成内容标准**：
- 所有关键页面/视图的可交互原型（React / Vue 组件，可在浏览器运行）
- 覆盖所有关键状态：空态、加载态、错误态、成功态
- 完整主路径 + 主要异常路径可走通
- 每个关键视觉/交互选择附设计决策说明

**人工 review 标准**：
- 视觉是否符合产品预期
- 交互流程是否符合用户习惯
- 与已有界面风格是否一致（对照设计系统文档）
- 边界状态是否处理完整

**迭代机制**：AI 根据 review 意见修改，直到产品/设计负责人确认（no 则继续修改，yes 则进入 Spec 生成）

**确认后操作**：
1. Coordinator 将本次设计决策 append 进项目设计系统文档（飞书，append-only）
2. 更新 Bitable `高保真原型链接`
3. 进入 Spec 生成阶段（needs_ui = true 时，Spec 转化 Agent 从原型直接提取 UI 技术规格 → design-ui.md）

---

## 七、飞书文档目录结构

```
飞书文档空间/
├── {项目名-A}/
│   ├── _项目设计系统         ← Coordinator 管理，append-only
│   ├── REQ-PRJA-001 {需求名称}/
│   │   ├── 需求文档           ← 文档同步 Hook，section 级幂等重写
│   │   ├── UI设计草稿（可选）  ← 低保真线框图
│   │   ├── UI高保真原型（可选）← 高保真可运行原型
│   │   └── 审查报告           ← Reviewer Agent 生成，Hook 写入
│   ├── REQ-PRJA-002 {需求名称}/
│   │   └── ...
│   └── ...
├── {项目名-B}/
│   └── ...
└── _模板/
    ├── 需求文档模板
    └── UI设计简报模板
```

---

## 八、需求版本管理规则

| 情况 | 处理方式 |
|---|---|
| 新需求 | 在创建群发起"创建需求"命令 → 生成新 REQ ID |
| 审查前修改 | 在 author 私聊继续补全/修改，状态在 DRAFTING ↔ AI_REVIEW ↔ HUMAN_CONFIRM 之间循环 |
| 审查后变更（小改） | final_review_reject → 回 DRAFTING，同一 REQ ID 继续迭代 |
| 审查后变更（大改） | 新开 REQ ID，走 v2 流程，旧 REQ ID 标记 SUPERSEDED |
| Bug 修复（已上线） | 不走需求层，直接在 GitHub 开 PR |

### 需求版本 vs Spec 版本的关系

本系统中两类版本号语义严格区分，互相不耦合：

| 维度 | 需求版本（`requirement_version`） | Spec 版本（`spec_version`） |
|---|---|---|
| 归属 | 需求层（Bitable 需求主表字段） | 规格层（`spec/REQ-.../acceptance.yaml` 中声明） |
| 变更触发 | 同一 REQ ID 内的需求文档正式变更（`final_review_reject` 后再次 APPROVED 算一次新版）；大改则开新 REQ ID 而非新 `requirement_version` | 已 SPEC_LOCKED 的 Spec 需要更新（AC 写错、性能收紧、非阻断新增 AC）时 increment |
| 与 Spec 的关系 | 每个 `requirement_version` 对应 **0 或 1** 条当前有效 Spec 链（即最新 `spec_version`）；历史 `spec_version` 为该需求版本下的演进记录 | 每个 `spec_version` 必须声明其基于的 `requirement_version`（`acceptance.yaml` 顶部 `based_on_requirement_version` 字段） |
| Fallback 影响 | 被触发"需求回炉 fallback"后，需求主态从 APPROVED 回到 DRAFTING，下次再次 APPROVED 时 `requirement_version` +1 | 回炉时当前 Spec 草稿作废（`SPEC_REJECTED`），不 increment `spec_version`；新需求版本下的首个 Spec 仍为 v1 |
| 锁定时刻 | 进入 APPROVED 时锁定；回炉会解锁 | SPEC_LOCKED 时锁定；只允许通过新 `spec_version` 修改，不原地改 |

**不允许的耦合**：禁止用 `requirement_version` 推算 `spec_version`，也禁止用 `spec_version` 反推需求变更次数。二者在时间线上独立演进，仅通过 `based_on_requirement_version` 字段建立追溯。
