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
       ▼ 消费：需求文档全部 8 字段 + review_summary + ARCHITECTURE.yaml + tech_stack
规格层-A：Spec 子层（SPEC_DRAFTING → SPEC_LOCKED）
  产出：design.md（8节技术规格）/ requirements.md / acceptance.yaml / spec_document_url
  锁定：SPEC_LOCKED 后 Spec 文档不可修改
  存储：GitHub PR（spec/REQ-xxx/）+ Coordinator state（spec_document_url）
       │
       ▼ 消费：acceptance.yaml（所有 AC）+ design.md（数据模型 + 架构接合点）+ needs_ui + 设计系统快照
规格层-B：Harness 子层（HARNESS_GENERATING → HARNESS_READY）
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
| 消费 | 需求文档 8 字段 / review_summary / ARCHITECTURE.yaml / tech_stack / 设计系统快照（needs_ui = true 时） |
| 产出 | design.md（含架构设计节）/ requirements.md / acceptance.yaml / spec_document_url / spec_review_summary |
| 防漂移 | Reviewer 维度：需求字段全覆盖 + 上下文消费声明完整性 + 测试用例与 AC 对齐 + 内部一致性 |
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
| 产出 | 实现代码 / 更新后的 ARCHITECTURE.yaml |
| 防漂移 | CI 必须跑全量 Harness；PR review 检查接口签名与 design.md 一致性 |
| 终止 | 需求文档原文（不再需要，已经过 Spec 结构化转化） |

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
