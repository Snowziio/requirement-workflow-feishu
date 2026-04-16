# 分层上下文传递契约原则

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) 的补充原则文档。
> 适用于：所有工作流层的设计、所有 Agent SKILL.md 的编写、所有层间 Review 维度的制定。

---

## 一、核心原则

**在每层设计时，必须显式回答以下五个问题。这不是可选的补充说明，而是每层设计文档的强制组成部分。**

| 问题 | 说明 |
|------|------|
| **消费什么** | 本层需要哪些项目级上下文，来源是什么（Coordinator state / 飞书文档 / GitHub 文件 / callback payload） |
| **如何消费** | 读取机制是什么（fetch-context 接口 / feishu_fetch_doc / GitHub API / 直接注入消息体） |
| **产出什么** | 本层新生成的项目级上下文是什么 |
| **如何传递** | 产出的上下文存到哪里、怎么让下层读到（Coordinator state 字段 / 飞书文档 URL / GitHub 文件 / Bitable 字段） |
| **如何防漂移** | Review 维度中哪一条明确校验本层对上层上下文的覆盖完整性和语义一致性 |

---

## 二、上下文契约模板

每个工作流层的设计文档必须包含以下格式的「上下文契约」声明：

```markdown
## 项目级上下文契约

### 消费（来自上层）
| 上下文产物 | 来源 | 读取机制 |
|-----------|------|---------|
| 需求文档 8 字段 | 飞书需求文档 | feishu_fetch_doc(document_id) |
| latest_review_summary | Coordinator state | fetch-context 接口 |
| ARCHITECTURE.yaml | GitHub 仓库 | GitHub API / 本地文件 |

### 产出（传递给下层）
| 上下文产物 | 内容 | 存储位置 | 更新策略 |
|-----------|------|---------|---------|
| Spec 文档 | 8节技术规格 | 飞书文档（spec_document_url） | 每节写完覆盖写 |
| spec_review_summary | 审查结论 | Coordinator state | 审查完成后写入 |

### 终止（不向下传递）
| 上下文产物 | 终止原因 |
|-----------|---------|
| 需求审查历史 discussion_history | 需求层内部记录，Spec 层不需要逐轮讨论历史 |

### 防漂移验证
| Review 维度 | 验证内容 | 类型 |
|------------|---------|------|
| 需求字段全覆盖 | Spec 8 节与需求文档 8 字段一一对应，无遗漏 | 阻断 |
| 上下文消费声明完整性 | 架构设计节中「项目级上下文消费声明」子节非空 | 阻断 |
```

---

## 三、全链路上下文流动图

```
需求层（DRAFTING → APPROVED）
  产出：需求文档 8 字段 / req_id / review_summary / needs_ui / project_config（技术栈）
  锁定：APPROVED 后需求文档不可修改
  存储：飞书文档（document_id）+ Coordinator state + Bitable
       │
       ▼ 消费：需求文档全部 8 字段 + review_summary + ARCHITECTURE 飞书文档（当前 revision）+ tech_stack
规格层（SPEC_DRAFTING → SPEC_LOCKED）
  产出：Spec 飞书文档（9 节技术规格）+ 演化后的 ARCHITECTURE 飞书文档（同一份跨 REQ 持续更新）+ spec_document_url
  锁定：SPEC_LOCKED 后 Spec 飞书文档不可修改；ARCHITECTURE 永不冻结，随后续 REQ 继续演化
  存储：飞书（spec_document_id + architecture_doc_id）+ Coordinator state（spec_document_url + architecture_doc_revision）
       │
       ▼ 消费：acceptance.yaml（所有 AC）+ design.md（数据模型 + 架构接合点）+ needs_ui + 设计系统快照
Harness 层（HARNESS_GENERATING → HARNESS_READY）
  产出：harness/tests/REQ-xxx/（每条 AC 的测试用例）/ 覆盖率矩阵
  锁定：卡点1b 通过后 Harness 目录只读
  存储：GitHub PR + ACM 注册表（status: finalized）
       │
       ▼ 消费：design.md（接口契约）+ acceptance.yaml（AC 定义）+ ARCHITECTURE.yaml（复用模块）+ 设计系统快照
生成→验证→集成→交付层（IMPLEMENTING → DEPLOYED）
  产出：实现代码 / CI 报告 / 更新后的 ARCHITECTURE.yaml
  存储：GitHub Impl PR + CI artifacts
```

---

## 四、防漂移三原则

### 原则 1：结构化映射优先于语义理解

上层产物到下层产物必须有**显式的字段级映射关系**，而不是依赖 AI 的语义理解来"保留"上层内容。

- 正确：需求文档「输入」节 → Spec 文档「API 入参定义」节（每个需求入参必须在 Spec 中有对应行）
- 错误：让 AI "根据需求写 Spec API"（无结构约束，AI 可能增删字段）

### 原则 2：Review 维度必须包含上层覆盖性检查

每层的 Review 必须有至少一个**阻断维度**，专门验证本层对上层关键上下文的覆盖完整性。

- 正确：Spec Reviewer 维度 1「需求字段全覆盖」= Spec 8 节与需求 8 字段一一对应
- 错误：Spec Reviewer 只检查 Spec 本身的质量，不校验与需求文档的对应关系

### 原则 3：不可修改的上层产物通过 URL 引用传递

APPROVED 后的需求文档、SPEC_LOCKED 后的 Spec 文档，通过 `document_url` 引用传递给下层，而不是将内容复制到下层产物中。下层产物中**引用上层原文**而不是**转述上层内容**。

- 正确：acceptance.yaml 中的 AC 条目引用来源（`source_req_id`、`source_field`），可追溯
- 错误：acceptance.yaml 重新描述验收标准（与需求文档产生分叉，难以发现漂移）

---

## 五、各层上下文契约摘要

### 需求层（Requirement Layer）

| 项 | 内容 |
|----|------|
| 消费 | project_config（技术栈）/ ARCHITECTURE.yaml（技术范围声明时参考）/ 历史 ACM（「历史约束参考」节注入） |
| 产出 | 需求文档 8 字段 / req_id / needs_ui / latest_review_summary |
| 防漂移 | Reviewer 维度：字段完整性 + 输入/输出结构化 + 验收标准可测试 + 技术范围声明存在性 + 内部一致性 |
| 终止 | 无（需求层是起点） |

### Spec 层（Spec Layer）

| 项 | 内容 |
|----|------|
| 消费 | 需求文档 8 字段 / latest_review_summary / ARCHITECTURE 飞书文档当前 revision / tech_stack / 设计系统快照（needs_ui = true 时） |
| 产出 | Spec 飞书文档（9 节）/ **演化后的 ARCHITECTURE 飞书文档**（覆盖写，保留飞书原生 revision 历史）/ spec_document_url / architecture_doc_revision（写后）/ spec_review_summary |
| 消费/产出入口 | 唯一合法入口为 `/queries/openclaw/spec-context` 端点（CLI 子命令 `spec-context`），返回 context_token；提交时必须回传该 token 与写后 revision |
| 防漂移 | Reviewer 维度：需求字段全覆盖 + 上下文消费声明完整性 + 测试用例与 AC 对齐 + 内部一致性；并发安全见本文 §七 |
| 终止 | discussion_history（需求层内部的逐轮讨论记录，Spec 不需要） |

### Harness 层（Harness Layer）

| 项 | 内容 |
|----|------|
| 消费 | acceptance.yaml（全部 AC）/ design.md（数据模型 + 接口定义）/ 设计系统快照（AC-UI 类） |
| 产出 | 测试用例代码 / 覆盖率矩阵 / ACM 注册表（finalized） |
| 防漂移 | 卡点1b 卡片：P0 AC 全覆盖检查 + 测试与 acceptance.yaml 的字段一致性核查 |
| 终止 | design.md 架构叙述（测试只依赖接口契约，不依赖实现架构） |

### 生成层（Generation Layer）

| 项 | 内容 |
|----|------|
| 消费 | design.md（接口契约 + 数据模型 + 架构接合点）/ ARCHITECTURE.yaml（复用模块）/ 设计系统快照 / Harness 测试（作为约束） |
| 产出 | 实现代码 / 更新后的 ARCHITECTURE.yaml（待合并 Impl PR 内） |
| 防漂移 | CI 必须跑全量 Harness；PR review 检查接口签名与 design.md 一致性；ARCHITECTURE.yaml 变更必须在 Impl PR 中可见 |
| 终止 | 需求文档原文（不再需要，已经过 Spec 结构化转化） |

### 验证层（Validation Layer）

| 项 | 内容 |
|----|------|
| 消费 | 实现代码（PR diff）/ Harness 测试（harness/tests/REQ-xxx/）/ 视觉回归基线（needs_ui = true 时）/ ACM 注册表（历史回归 AC 列表） |
| 产出 | CI 报告（P0 测试结果 + 历史回归结果 + 覆盖率 + 视觉差异）/ 失败定位摘要 |
| 防漂移 | P0 测试必须全绿 + 历史 ACM 回归必须全绿才能进入集成层；卡点2 以此报告为判断依据 |
| 终止 | 中间调试日志（仅保留在 CI artifacts，不向集成层传递） |

### 集成层（Integration Layer）

| 项 | 内容 |
|----|------|
| 消费 | CI 全绿的 Impl PR / design.md 接合点声明 / ARCHITECTURE.yaml |
| 产出 | 合并后的主分支 commit / 更新生效的 ARCHITECTURE.yaml / 部署镜像标签（commit-sha） |
| 防漂移 | 合并前再次校验 ARCHITECTURE.yaml 的接合点变更与 design.md 声明一致；Impl PR 合并后立即触发 ACM 注册表 status 更新为 integrated |
| 终止 | PR 讨论串（归档在 GitHub，不进入后续环境） |

### 交付层（Delivery Layer）

| 项 | 内容 |
|----|------|
| 消费 | 集成层输出的部署镜像 / Staging 验证结果 / 设计系统文档（面向运营的操作说明） |
| 产出 | 生产部署版本 / Staging URL（卡点3 审查对象）/ 发布记录（append 至发布日志） |
| 防漂移 | 卡点3 卡片必须基于 Staging 实际页面截图/行为而非代码；上线后 ACM 注册表 status 更新为 released |
| 终止 | Impl PR 内部实现细节（不向下游传递，下一个需求只读 design.md + ARCHITECTURE.yaml + ACM 注册表） |

---

## 六、设计文档检查清单

**每次设计一个新工作流层时，检查以下项目：**

- [ ] 设计文档中有「项目级上下文契约」节（按本文 Section 2 模板）
- [ ] 消费的每个上下文产物都有明确的读取机制
- [ ] 产出的每个上下文产物都有明确的存储位置和更新策略
- [ ] 至少一个 Review 阻断维度专门验证对上层上下文的覆盖完整性
- [ ] Agent SKILL.md 中有「Step 1：读取项目级上下文」步骤，且列出具体读取的产物
- [ ] 终止声明明确（哪些上下文在本层不再需要）

**每次编写 Agent SKILL.md 时，检查以下项目：**

- [ ] 启动流程中第一步是读取项目级上下文（fetch-context 或等价操作）
- [ ] 明确列出从上下文中需要读取的字段和产物
- [ ] 产出内容的存储/上报方式与「上下文契约」中的存储位置一致
- [ ] 不允许的行为中包含「不得跳过上下文读取步骤」
- [ ] 不允许的行为中包含「不得在未成功调用 callback 的情况下结束会话」（见 §八）

---

## 七、并发写回契约

**背景**：Pre-Phase-2 引入 ARCHITECTURE 作为 Spec 层的跨 REQ 共享产出物后，出现新的并发场景——两个 Spec 会话可能读取同一份 ARCHITECTURE 飞书文档、各自做增量合并、先后覆盖写回，导致后写者丢失先写者的变更。需求层不存在此问题（需求文档一 REQ 一份，单作者），但凡涉及**跨 REQ 共享的项目级产出物**，必须走下面的握手协议。

### 握手协议

1. **进入读取**：Agent 调用上下文端点（如 `/queries/openclaw/spec-context`），端点返回：
   - 共享产物的 URL（如 `architecture_doc_url`）
   - 进入时的 revision 快照（如 `architecture_doc_revision`）
   - `context_token`（端点签发的一次性令牌，Coordinator 侧保留对应上下文镜像）
2. **本地合并**：Agent `feishu_fetch_doc` 读取当前 YAML → 基于本次决策做增量合并 → 生成新版 YAML。
3. **覆盖写回**：Agent `feishu_update_doc` 写回共享产物；**写回动作本身不做并发检查**（飞书底层 API 不提供 CAS 语义）。
4. **读后 revision**：写回后 Agent **再次调用上下文端点**（或等价查询），取得**写后 revision**。
5. **提交握手**：Agent 调用提交 callback（如 `spec-submit`），必须同时回传 `context_token` 与写后 revision。Coordinator 校验：
   - `context_token` 未过期且匹配当前会话 → 否则 400 `token_invalid`，要求重走第 1 步
   - 进入时 revision 与 Coordinator 记录一致 → 不一致抛 409 `revision_conflict`，要求 Agent 重新读当前 YAML 合并后再提交
6. **状态推进**：两项校验通过后 Coordinator 才落地状态流转；否则拒绝，Agent 按错误码处理。

### 为什么不是乐观锁

飞书 docx 没有原生 CAS。协议的本质是**把并发仲裁从存储层上移到 Coordinator 层**：Coordinator 用 context_token 识别「是谁发起的这次写」、用 revision 对比识别「这期间有没有别人写过」。token 与 revision 都是必要条件，缺一任何一边都无法防住 session 劫持或静默覆盖。

### 适用范围

| 产物类型 | 是否走本协议 | 原因 |
|---------|------------|------|
| 需求文档 | 否 | 一 REQ 一份，单作者（author Agent + 需求提出者） |
| Spec 飞书文档 | 否 | 一 REQ 一份，单作者（spec-author Agent），SPEC_LOCKED 后冻结 |
| **ARCHITECTURE 项目级飞书文档** | **是** | 跨 REQ 共享、可被任意 Spec 会话演化 |
| 设计系统飞书文档 | 是（Phase 2 启用） | 跨 REQ 共享 |
| ACM 注册表（Phase 3 GitHub） | 否（Git 层面已有 merge 冲突机制） | Git 原生 CAS |

### 对设计文档 / SKILL.md 的要求

- 任何跨 REQ 共享产物的**上下文契约表**必须注明「通过 §七 并发写回契约保护」。
- 相关 Agent 的 SKILL.md 必须显式写明：启动时保留 `context_token` 与进入时 revision、写回后再次拉取 revision、提交 callback 时同时回传；遇到 `token_invalid` / `revision_conflict` 的处理路径。

---

## 八、Callback 作为状态机唯一真相

**背景**：Pre-Phase-2 测试中多次观察到 Agent 在飞书文档写完后，仅以自然语言回复「已完成」「请进入下一步」就结束会话，而没有调用 `send_openclaw_callback.py` 上报。由于 Coordinator 的状态机只响应 callback，这类会话在业务语义上等同于**未完成**，流程会静默卡死在当前状态，人工难以察觉。

**约束**（适用于所有工作流层的所有 Agent）：

1. **callback 是状态推进的唯一合法触发方式**。写入飞书文档、回复用户消息、输出审查报告——全部都不是状态推进，只是产出/观察动作。
2. **本次会话的最终动作必须是 callback**。Agent 的 SKILL.md 必须在各终止分支显式写出：「本次会话最终动作必须是执行 `<具体 callback 命令>`」，并将这条作为硬约束放在输出节的显著位置。
3. **callback 失败必须显式暴露**。HTTP 非 2xx（含 400 token 失效、409 revision 冲突）时必须按错误码处理后重试；仍失败则在回复中明确说明「callback 上报失败」并保留现场，**禁止伪装成已完成**。
4. **不允许的行为必须包含**「不得在未成功调用 callback 的情况下结束会话——写入文档 / 输出文本 ≠ 流程推进，状态机只认 callback」。

**为什么要把这条写进方法论**：AI Agent 天然倾向于以「自然语言回复」作为会话完成信号，而方法论依赖状态机作为流程真相。两者的语义裂缝必须靠约束词条强行对齐，不能靠 Agent 自觉。
