# Harness Engineering 全自动开发工作流：完整方法论
## v1.3 | 2026-04-10

> **贯穿本文的参考案例**
> 客户需求：在租赁业务平台中，使用大模型自动解读申请人的营业执照与征信信息，生成面向租赁场景的格式化风控报告。
> 本文所有流程设计均以此案例为锚点进行说明。

> **v1.4 变更摘要（2026-04-14）**
> - 新增 §1.4 **项目级上下文**：五层内容结构（功能契约/架构快照/视觉规范/规范惯例/需求历史）、双平面存储（飞书+GitHub）、Coordinator Service 作为同步枢纽、冷热内存模型（参考 arXiv 2602.20478）
> - §2.1.5 需求文档模板升级：输入/输出从纯描述升级为半结构化契约（字段名+类型+约束）；验收标准升级为可测试断言；新增"技术范围声明"section（Spec 生成必需）
> - §2.1.11 UI 设计方式升级为两阶段模型：低保真线框图（HUMAN_CONFIRMING，验证理解）+ 高保真可运行原型（APPROVED 后，视觉技术合同）
> - §2.2 规格层-A 重构：四层 Spec 结构（Requirements/Design/ACM/Tasks）；注入三类项目级上下文（ARCHITECTURE.yaml+ACM注册表+设计系统快照）；卡点1a 仅对 Design 层
> - §2.3 规格层-B 新增视觉回归测试（Playwright），作为 UI 层的 Harness 等价机制
> - §五 新增工具14-17：设计系统文档管理器、高保真 UI 原型生成 Agent、ACM 注册表维护服务、视觉回归测试生成器
>
> **v1.3.1 参考实现对齐（2026-04-13）**
> - 状态名与 `Snowziio/requirement-workflow-feishu` 参考实现对齐：方法论概念层保留7态，同时标注参考实现5态简化名称（DRAFTING / AI_REVIEW / HUMAN_CONFIRM / FINAL_REVIEW / APPROVED）
> - DISCUSSION_ROUTING 状态：确认在参考实现中已合并进创建流程，不单独成状态
> - §2.1.3 双闸门约束伪代码：事件名统一为参考实现 `Event` 枚举命名
> - §2.1.7 Bitable 状态枚举：更新为参考实现实际使用的状态值
>
> **v1.3 变更摘要**
> - 新增 §1.3 **层间工作流服务模式**：纵向每层通过 "Workflow Service + Hook 实现 + 能力层" 三层分离的方式落地，作为贯穿全文的顶级架构原则
> - 需求层架构反转：**Coordinator Service** 取代 OpenClaw 成为真相源与状态机；OpenClaw 降级为 Author/Reviewer Agent
> - 需求层状态机从 5 态扩展为 **7 态**，AI 审查与人工确认解耦为独立阶段
> - **双闸门**：AI Ready + Human Confirmed 独立记录、独立失败、独立追溯，状态机层面强制
> - **三方交互模型**：创建群 / Author 私聊 / 项目群严格区分，各司其职
> - **正式文档 section-level 幂等重写规则**：禁止追加和全删重建
> - **UI 设计**由独立状态降为 `onEnter(HUMAN_CONFIRMING)` Hook 层内容，状态机保持 7 态不变
> - 首个参考实现：`Snowziio/requirement-workflow-feishu`（方法论正文保持与参考实现解耦，两边以定期人工对齐的方式维持一致）
>
> **v1.2 变更摘要**（⚠️ 需求层主编排部分已在 v1.3 被反转，保留此处仅作历史记录）
> - 需求层重设计：引入 OpenClaw Agent 作为飞书生态内的工作流编排器
> - 需求层内部四阶段子流程：需求创建 → 需求讨论 → UI 设计（可选）→ 需求审查
> - REQ ID（`REQ-{PROJECT}-{NNN}`）作为跨层级唯一索引，穿透飞书→GitHub 全链路
> - Bitable 需求追踪表作为全生命周期状态机
> - OpenClaw 与 checkpoint-handler 分工明确：飞书侧 vs GitHub 侧
>
> **v1.1 变更摘要**
> - 规格层拆分为 Spec 子层（人+AI 协作写作）与 Harness 子层（AI 生成测试代码）
> - 引入 ACM（验收标准矩阵）作为 Spec 与 Harness 之间的结构化桥梁
> - 卡点从 3 个扩展为 4 个：新增卡点1b（Harness门）
> - 引入"单向转化门"设计，解决飞书草稿空间与 GitHub 锁定空间的工具差异
> - harness/tests/ 改为按功能+版本组织，支持多版本共存和历史兼容性

---

## 一、三维框架总览

整个工作流由三个维度构成，缺一不可：

```
┌──────────────────────────────────────────────────────────────────┐
│                          横向基础设施                              │
│  人工协同轨（飞书+OpenClaw）  ║    工程自动化轨（GitHub+CI）       │
├───────────╥─────────────╥─────╥──────╥──────╥────────────────────┤
│  需求层    ║规格层A║规格层B║生成层║验证层║集成层║交付层 ← 纵向流程  │
│Coordinator║Spec  ║Harness║      ║      ║      ║                  │
│  Service  ║      ║       ║      ║      ║      ║                  │
├───────────╨─────────────╨─────╨──────╨──────╨────────────────────┤
│                  层内子流程（AI自主处理）                           │
└──────────────────────────────────────────────────────────────────┘

REQ ID（REQ-{PROJECT}-{NNN}）穿透全链路：飞书文档 → Bitable → GitHub branch → PR → ACM

四个人工卡点：
  ⚡1a 方案门（Spec + ACM 确认）
  ⚡1b Harness门（测试覆盖确认）
  ⚡2  质量门（CI通过，合并确认）
  ⚡3  发布门（Staging验收）

需求层状态机（Coordinator Service 驱动，参考实现 5 状态）：
  CREATED → DRAFTING → AI_REVIEW → HUMAN_CONFIRM → FINAL_REVIEW → APPROVED
  （方法论概念层用 7 态描述，见 §2.1.2；参考实现合并了 DISCUSSION_ROUTING）
```

**纵向流程**：从需求到交付的七层流水线（规格层拆分为A/B两个子层），定义"做什么"。
**横向基础设施**：贯穿所有层的共用基础设施，分为人工协同和工程自动化两轨。
**层内子流程**：每层内部的AI自主循环，人不感知，由CLAUDE.md约束。
**层间工作流服务**：各层由规则化工作流服务驱动（需求层：Coordinator Service；规格→交付层：checkpoint-handler），OpenClaw 作为 Hook 实现层的 AI Agent 能力提供者。

**核心原则**：人只在四个卡点做判断，其余全部由AI或自动化完成。

### 1.3 层间工作流服务模式

v1.3 新增的顶级架构原则，贯穿 §2 所有纵向层的实现。

#### 1.3.1 背景

纵向流程的每一层（以及层与层之间的衔接点）都对应一套工作方法。这些工作方法有一个共同特征：**高度规则化、基本不以具体项目特性为转移**。例如：

- 需求层的方法："创建 → 多轮讨论 → AI 审查 → 人工确认 → 正式审查"，对任何项目都一样。
- 规格层→生成层的方法："规格确认 → Harness 生成 → 卡点 → 失败分析 → 重试 → 实现触发"，对任何项目都一样。
- 生成层→验证层的方法："代码生成 → CI → 失败回灌 → 重试"，同样与项目无关。

既然工作方法是固定的，就应该抽成**可复用的服务**，让每个项目不用重新设计流程。这就是"层间工作流服务"：每一层（或层间衔接点）都有一个属于自己的、规则化的工作流服务。

#### 1.3.2 三层分离

每个层间工作流服务遵循严格的三层架构：

| 层 | 职责 | 特性 |
|---|---|---|
| **Workflow Service 层** | 状态机定义、状态转移、hook 派发、真相源持久化、工作流启动与恢复 | 纯规则、无 AI、无具体业务动作、项目无关 |
| **Hook 实现层** | 状态转移动作的具体实现：onEnter / onExit / onTransition 等回调 | 业务逻辑所在地、调用能力层、可独立单测 |
| **能力提供层** | AI Agent、人工、外部 API 等可插拔能力 | 可替换、契约化、不持有状态 |

**核心性质**：

1. **Workflow Service 不 import 任何能力层 SDK**。它只知道"状态 X → Y 时触发 hook Z"，不知道 hook Z 内部是调 OpenClaw 还是调 Claude。
2. **能力替换零成本**。把 OpenClaw 换成 Claude 直连只需改 Hook 实现层，Workflow Service 一行不动。
3. **状态机可以独立测试**。用 mock hook 注入 Workflow Service，就能单测全部状态转移逻辑，不依赖任何外部服务。
4. **Hook 实现可以独立测试**。用 mock state 调用 Hook，就能单测外部调用，不依赖状态机。
5. **每一层的 Workflow Service 都是可独立部署的自研工具**。它们在 §五 自研工具清单中单列一类。

#### 1.3.3 应用示例（前向引用）

| 纵向层 / 层间 | Workflow Service 实现 | 主要 Hook 类型 | 主要能力层 |
|---|---|---|---|
| 需求层（§2.1） | Coordinator Service | author/reviewer 触发、Bitable 同步、正式文档 section rewrite、UI 原型生成 | OpenClaw Author/Reviewer Agent、Feishu IM / Bitable / Docx API |
| 规格层→生成层（§2.2 / §2.3） | checkpoint-handler | 卡点卡片发送、CI 触发、失败分析、PR 创建 | Claude API、GitHub API、Feishu 卡片 |
| 生成层→验证层（§2.4 / §2.5） | *待建* | CI 执行调度、测试聚合、失败回灌 | GitHub Actions、测试框架 |
| 验证层→集成层（§2.5 / §2.6） | *待建* | 合并确认、发布准备 | GitHub API、部署脚本 |
| 集成层→交付层（§2.6 / §2.7） | *待建* | 客户环境部署、验收触达 | deploy.sh、Staging 监控 |

#### 1.3.4 为什么这条原则重要

v1.2 曾把需求层的主编排交给 OpenClaw。首次部署过程中发现 OpenClaw 作为第三方 Agent 平台无法承载"真相源"的职责——session 绑群、长连接不稳定、无法持久化跨进程状态。问题不在 OpenClaw 本身，而在于**把"能力层"错当成了"Workflow Service 层"来用**。

三层分离原则直接杜绝此类错误：
- 能力层只负责"做什么"，不持有状态、不掌控流程。
- Workflow Service 层独占流程和状态，实现上可以用最稳定的语言和框架写（不需要追 AI 平台的版本迭代）。
- Hook 实现层作为两者的粘合层，让整套系统既稳定又灵活。

同时这条原则给后续未建成的纵向层提供了**统一模板**：每加一层只需写一个新的 Workflow Service + 一组新的 Hook，不用重新设计工作流架构。规格层→生成层的 checkpoint-handler 就是按这个模板先落地的第一个实例，需求层的 Coordinator Service 是第二个。

#### 1.3.5 与"层内子流程"的关系

本方法论在前文提到过"层内子流程：AI 自主处理，规则写入各项目的 CLAUDE.md"。层间工作流服务和层内子流程的区别是：

| 维度 | 层间工作流服务 | 层内子流程 |
|---|---|---|
| 控制者 | Workflow Service（外部服务） | AI Agent（项目内 CLAUDE.md） |
| 规则存储 | Workflow Service 代码 | 项目的 CLAUDE.md |
| 可替换性 | 能力层可换，服务本身稳定 | 整个子流程由项目 CLAUDE.md 定义 |
| 跨项目性 | 项目无关，一套服务服务所有项目 | 可能因项目定制 |
| 典型示例 | "需求创建 → 讨论 → 审查 → 确认" | "AI 生成代码 → CI 失败 → 自修复 → 重试" |

两者不冲突：层间工作流服务负责**层之间的衔接**和**层内的结构化阶段**；层内子流程负责**层内部 AI 自主循环**的具体技术细节。举例：规格层→生成层的卡点触发是 checkpoint-handler 的事（层间工作流服务），而生成层内部"AI 写代码 → 失败 → 读 CI → 修 → 重试"是 Coding Agent 按 CLAUDE.md 自主完成的（层内子流程）。

---

### 1.4 项目级上下文

v1.4 引入的贯穿全链路基础概念。

#### 1.4.1 定义

项目级上下文是一个项目在整个生命周期中积累的、**跨 session 持久存在的结构化知识**，使得任何 Agent（对话式或编码式）在任何时刻介入，都能理解"这个项目现在是什么状态、已经做了哪些决定、约束是什么"，而不需要从头推导。

这是防止架构漂移、视觉漂移、功能漂移的根本机制。没有项目级上下文，每次迭代的 AI 都在"失忆"状态下工作，不可避免地与历史决定冲突。

#### 1.4.2 五层内容结构

| 层 | 名称 | 代表产物 | 防止 |
|---|---|---|---|
| Layer 1 | 功能契约层 | ACM 注册表（consolidated.yaml）、REQ 索引 | 功能漂移（新 Spec 与已有契约冲突） |
| Layer 2 | 架构快照层 | ARCHITECTURE.yaml、ADR 归档 | 架构漂移（新实现破坏已有架构约定） |
| Layer 3 | 视觉规范层 | 项目设计系统文档（飞书）、设计系统快照（GitHub） | 视觉漂移（新 UI 与已有界面风格不一致） |
| Layer 4 | 规范惯例层 | CLAUDE.md、技术栈声明 | 代码风格漂移（AI 每次 session 自动加载） |
| Layer 5 | 需求历史层 | 需求文档集（飞书）、UI 原型集（飞书） | — （新需求构造时的历史背景参考） |

#### 1.4.3 双平面存储模型

项目级上下文横跨两个存储平面，由 Coordinator Service 作为同步枢纽：

```
飞书平面（人工协同轨）
  ├── 需求文档集（Layer 5）
  ├── UI 原型集（Layer 5）
  └── 项目设计系统文档（Layer 3）

         ↕ Coordinator Service（同步枢纽）
         · 管理飞书侧所有项目级资产
         · 在 Spec 生成时导出快照到 GitHub
         · 提供跨 session 的上下文查询接口

GitHub 平面（自动化 Coding 轨）
  ├── ARCHITECTURE.yaml（Layer 2）
  ├── ACM 注册表（Layer 1）：specs/registry/consolidated.yaml
  ├── 设计系统快照（Layer 3 镜像）：specs/design-system-snapshot.yaml
  └── CLAUDE.md（Layer 4，热加载）
```

**关键约束**：UI 设计发生在代码仓库建立之前，设计系统文档的主存储必须在飞书平面；GitHub 快照是在 Spec 生成时由 Coordinator 导出，供 AI Coding Agent 在编码轨消费。

#### 1.4.4 管理职责分工

```
Coordinator Service（人工协同轨管理者）
  管理：Layer 3 视觉规范（飞书）
        Layer 5 需求历史（飞书）
        REQ 状态索引（Bitable + JSON）
  职责：飞书 → GitHub 快照导出（Spec 生成触发时）

checkpoint-handler（自动化 Coding 轨管理者）
  管理：Layer 1 功能契约（ACM 注册表，GitHub）
        Layer 2 架构快照（ARCHITECTURE.yaml，GitHub）
        Layer 4 规范惯例（CLAUDE.md，人工触发）
```

#### 1.4.5 事件驱动更新表

| 触发事件 | 更新内容 | 执行者 |
|---|---|---|
| REQ 创建 | REQ 索引新增条目 | Coordinator |
| REQ APPROVED | REQ 索引状态更新 | Coordinator |
| UI 设计确认 | 设计系统文档 append（飞书） | Coordinator |
| Spec 生成（卡点1a 通过） | ACM 注册表新增条目；设计系统快照导出 GitHub | Coordinator 触发，checkpoint-handler 执行 |
| Harness 通过（卡点1b） | ACM 注册表该条目标记 finalized | checkpoint-handler |
| Impl PR 合并 | ARCHITECTURE.yaml 更新（如有接口变更） | checkpoint-handler Hook |
| 架构决策发生 | ADR 新增文档 | 人工写入 |

**核心原则：所有更新 append-only，可追溯到触发它的 REQ ID。**

#### 1.4.6 冷热内存模型

参考 Codified Context 论文（arXiv 2602.20478），上下文按访问频率分层注入 AI Coding Agent：

| 层级 | 内容 | 加载时机 |
|---|---|---|
| **热**（每次 session 自动加载） | CLAUDE.md；ARCHITECTURE.yaml；当前 REQ 的 Spec（Requirements + Design + Tasks）；design-system-snapshot.yaml（需要UI = true 时） | 进入编码 session 即加载 |
| **温**（按 REQ 加载） | 当前 REQ 的 ACM；与当前 REQ 技术范围有重叠的历史 ACM 条目 | Spec 生成时注入 |
| **冷**（按需查询） | 完整 ACM 注册表（兼容性检查时）；设计系统完整历史（UI 决策追溯时）；ADR 归档（架构决策参考时） | 显式触发时查询 |

---

## 二、纵向流程详解

### 2.1 需求层（Coordinator Service 驱动，OpenClaw 作为 Author/Reviewer Agent）

**目标**：将模糊的客户需求转化为经过双闸门确认的结构化需求文档。

| 项目 | 内容 |
|---|---|
| 输入 | 客户描述（口头/文字/会议记录） |
| 输出 | 经 AI 审查 + 人工确认 + 正式审查三道关的需求文档 |
| 人的工作 | 创建群发起、author 私聊补全字段、项目群确认审查结论 |
| AI 的工作 | 引导式字段补全（Author Agent）、多轮质量审查（Reviewer Agent）、HUMAN_CONFIRMING 阶段的 UI 原型生成（Hook 内可选） |
| 自动化 | Coordinator Service 驱动状态机、Hook 层执行 Bitable 写回和正式文档 section rewrite |
| 索引 | REQ ID（`REQ-{PROJECT}-{NNN}`），跨层唯一标识 |

**需求层在飞书内完全闭环**，不接触 GitHub。输出的需求文档是规格层-A 的输入。本节遵从 §1.3 层间工作流服务模式，Coordinator Service 是该模式在需求层的首个参考实现。

#### 2.1.0 v1.3 重要变更：从"OpenClaw 主编排"反转为"Coordinator Service 主编排"

v1.2 曾把 OpenClaw 定位为需求层的**主编排器**。在首次部署过程中我们发现这个假设不成立：

- **根因**：OpenClaw 的 session 是**按群绑定**的，同一个需求在"创建群"和"author 私聊"两个上下文之间无法共享状态。
- **次因**：OpenClaw 作为第三方 Agent 平台，没有稳定的事件订阅和长连接保活机制，不能作为需求状态的唯一真相源。
- **结论**：需求层必须有一个**我们自己掌控**的后端作为真相源，OpenClaw 被降级为纯粹的"字段补全 Agent"和"质量审查 Agent"——即 **Author Agent** 和 **Reviewer Agent**。

架构反转后的三层分离（符合 §1.3 层间工作流服务模式）：

```
Coordinator Service（Workflow Service 层）
  - 7 态状态机 + 转移表
  - Bitable / JSON snapshot 持久化
  - 工作流启动与恢复
  - 完全不 import OpenClaw / Feishu SDK
         │ 触发 transition hooks
         ▼
状态转移 Hook 实现层
  - onEnter(DISCUSSING) → 调 Author Agent 补全字段
  - onEnter(AI_REVIEWING) → 调 Reviewer Agent 判 AI Ready
  - onEnter(HUMAN_CONFIRMING) → 组装结论 + 生成 UI 原型（如需）→ 推送 author 私聊
  - onExit(DISCUSSING) → 同步 Bitable + section rewrite 正式文档
  - onEnter(REVIEWING) → 发送审查卡片到项目群
         │ 调用
         ▼
能力提供层（可替换）
  - OpenClaw Author Agent / Reviewer Agent（当前实现）
  - UI 设计 Agent（design.md / UIUX ProMax 或其它）
  - Feishu IM / Bitable / Docx API
```

**Coordinator Service** 是需求层的核心自研组件，地位等同于规格→生成层的 `checkpoint-handler`。首个参考实现见本节末尾的参考实现引用。

#### 2.1.1 三方交互模型

需求层的交互**严格区分三个上下文**，不能混用：

| 上下文 | 人员 | Hook 层职责 | 消息性质 |
|---|---|---|---|
| **创建群** | 需求发起人 + 项目相关人 | 接收"创建需求"命令，回复 REQ ID 和入口链接 | 群消息，公开可见 |
| **Author 私聊** | 仅需求发起人（author） | 逐字段引导补全、接收多轮讨论输入、推送 HUMAN_CONFIRMING 阶段的 AI 结论 + UI 原型 | 1:1 私聊，避免群噪声 |
| **项目群** | 项目所有干系人 | 发送正式审查结论卡片、接收"通过/打回"的确认 | 群消息，REVIEWING 阶段在这里 |

上下文切换的约束：
- 同一个需求的状态由 Coordinator Service 唯一持有，三个上下文共享同一个真相源。
- Hook 层根据当前状态决定向哪个上下文发送消息，不依赖 Agent 平台的 session。

#### 2.1.2 状态机（7 态）

v1.2 的 5 态模型把"AI 审查"和"人工确认"合并成一件事，导致两者无法独立失败独立重试。v1.3 扩展为 7 态：

**概念层（7 态，完整语义）**：

```
CREATED                    ─ 需求刚在创建群里发起
  ↓  create_requirement
DISCUSSION_ROUTING         ─ 等待 author 发起私聊建立绑定
  ↓  handoff_to_author
DISCUSSING / DRAFTING      ─ author 私聊多轮字段补全
  ↓  author_submit
AI_REVIEWING / AI_REVIEW   ─ Reviewer Agent 判定 AI Ready
  ├─ ai_review_reject ──→ DRAFTING（回炉）
  └─ ai_review_pass   ──↓
HUMAN_CONFIRMING / HUMAN_CONFIRM ─ author 人工确认 AI 结论（含 UI 原型，如需）
  ├─ human_confirm_no  ──→ DRAFTING（回炉）
  └─ human_confirm_yes ──↓
REVIEWING / FINAL_REVIEW   ─ 正式审查（项目群内）
  ├─ final_review_pass    ──→ APPROVED
  └─ final_review_reject  ──→ DRAFTING（回炉）
APPROVED / REQ_APPROVED    ─ 终态，进入规格层-A
```

**参考实现（5 态，`Snowziio/requirement-workflow-feishu`）**：

DISCUSSION_ROUTING 阶段被合并进创建流程（Coordinator 创建需求后直接私信 author 发送启动指令，author 在私聊发送「开始需求构造 REQ-ID」后即进入 DRAFTING），不单独成状态。其余状态使用右侧的简化名称（`/` 后），事件名以参考实现为准。

**关键原则**：FINAL_REVIEW 是一个**独立阶段**，不能被"穿透"。即使 Human Confirmed = true，也要显式经过 FINAL_REVIEW 阶段，由人触发 final_review_pass 才能进 APPROVED。这一条在状态机约束层硬编码（见 §2.1.3）。

#### 2.1.3 双闸门（AI Ready + Human Confirmed）

v1.2 只有一道"人工确认"门。v1.3 引入**两道独立的门**：

| 闸门 | 判定者 | 判定依据 | 存储字段 | 进入条件 |
|---|---|---|---|---|
| **AI Ready** | Reviewer Agent | 7 个讨论字段全部有实质内容 + 一致性/可测试性通过 | Bitable `AI Ready` (bool) | `AI_REVIEW → HUMAN_CONFIRM` |
| **Human Confirmed** | Author（需求发起人） | 私聊里看到 AI 结论 + UI 原型（如需）后主动确认 | Bitable `Human Confirmed` (bool) | `HUMAN_CONFIRM → FINAL_REVIEW` |

**两道门必须都为 true** 才能进入 REVIEWING 阶段。状态机层面强制以下约束（伪代码）：

```
约束 1（AI Ready 前置）：
  若 event = human_confirm_yes 且 ai_ready = false：
    → 拒绝转移，保持当前状态，原因「AI Ready 未满足，不能进入正式审查」

约束 2（Human Confirmed 前置）：
  若 event = final_review_pass 且 human_confirmed = false：
    → 拒绝转移，保持当前状态，原因「Human Confirmed 未满足，不能批准需求」
```

事件名以参考实现 `state_machine.py` 的 `Event` 枚举为准：`author_submit`、`ai_review_reject`、`ai_review_pass`、`human_confirm_yes`、`human_confirm_no`、`final_review_pass`、`final_review_reject`。

双闸门的意义：AI 和人的判断**独立记录、独立失败、独立追溯**。任何一方觉得不 ready 都能单独回炉，不会互相污染。这两条约束属于 Workflow Service 层的职责，必须在状态机里硬编码，不能下沉到 Hook 层。

#### 2.1.4 状态转移 Hook ↔ Agent 能力契约

Hook 实现层调用能力层时遵循契约化接口，契约与具体 Agent 平台解耦。当前需求层的三类主要 Agent 契约如下：

| 角色 | Hook 调用时机 | 契约输入 | 契约输出 |
|---|---|---|---|
| **Author Agent** | `onEnter(DISCUSSING)`、每一轮 author 私聊消息到达时 | 当前需求快照 + 讨论字段进度 + 本轮 author 发言 | 下一个要问的字段 / 下一句话 / 是否等待用户 |
| **Reviewer Agent** | `onEnter(AI_REVIEWING)` | 完整需求快照（所有讨论字段 + 最近一轮变更） | `ai_ready: bool` + 结论摘要 + 维度打分（完整性/一致性/可测试性/历史冲突） |
| **UI 设计 Agent**（可选，见 2.1.10） | `onEnter(HUMAN_CONFIRMING)` 且 `需要UI = true` | 完整需求快照 | UI 原型（组件树 + 样式 + 交互逻辑 + 线框图链接） |

**关键原则**：
- Workflow Service 对 Agent 平台**无感知**。今天 Agent 能力由 OpenClaw 提供，明天可以换成 Claude 直连或任何其他实现，Workflow Service 一行代码不动。
- 每个契约必须定义**失败语义**：Agent 调用失败时，Hook 层负责重试、回退或记录到 Bitable 追溯字段，状态机不感知失败细节。
- 契约的具体字段定义以首个参考实现为准。

#### 2.1.5 需求文档模板结构（v1.4 升级）

需求文档使用固定的 section 结构，是 §2.1.6 section-level 幂等重写的目标对象。v1.4 在原有 7 个讨论字段基础上，升级了**输入/输出格式要求**并新增了**技术范围声明** section，为 Spec 生成提供必要的技术输入。

```markdown
# REQ-{ID} {需求名称}
> 创建人: {人员} | 创建时间: {日期} | 状态: {状态}

## 历史约束参考（只读，系统注入）
[AI 从 GitHub ACM 注册表拉取，列出可能受影响的历史验收标准]

## 问题描述
这个功能解决什么业务问题？

## 使用场景
用户在什么情况下触发，期望得到什么结果？

## 输入（v1.4：升级为半结构化契约）
列出所有输入字段，每条包含：字段名 + 类型 + 主要约束。
示例：
  - license_image: 图片文件，支持 jpg/png，最大 5MB
  - credit_report: JSON 对象，包含 applicant_id（string）和 credit_score（number）

## 输出（v1.4：升级为半结构化契约）
列出输出字段，每条包含：字段名 + 类型 + 可能的枚举值。
示例：
  - risk_level: enum（low / medium / high）
  - score: integer（0-100）
  - report_id: string（UUID）

## 边界（不包含什么）
明确排除的功能范围。

## 验收标准（v1.4：升级为可测试断言，不可省略）
每条必须能回答：给定什么输入 → 期望什么输出 → 怎么判断通过。
示例：
- 给定完整营业执照和征信数据，返回的 risk_level 字段必须存在且为 low/medium/high 之一
- 给定缺失 credit_score 的输入，系统返回 422 + error_code: MISSING_CREDIT_SCORE

## 非功能要求
性能、安全、合规等约束（含具体数值，如"P99 响应时间 < 3s"）。

## 技术范围声明（v1.4 新增，Spec 生成必需）
  - 涉及现有模块：[从 ARCHITECTURE.yaml 选取，或填"无"]
  - 操作类型：新增接口 / 修改现有接口 / 纯数据处理（选填）
  - 数据持久化：是否需要新增/修改数据表（是/否）
  - 对外依赖：调用哪些第三方服务（无则填"无"）
```

**Author Agent 引导策略变更**：
- 引导用户将输入/输出补全到"字段名 + 类型 + 主要约束"粒度（不需要完整 OpenAPI schema）
- 从 ARCHITECTURE.yaml 拉取现有模块列表供用户勾选，降低技术范围声明的填写成本
- Reviewer Agent 新增两个退回条件：①输入/输出仍为纯描述（无字段名）；②技术范围声明为空

#### 2.1.6 正式文档 section-rewrite 规则

需求的正式文档（飞书文档）在每一轮 author 提交后都会被**文档同步 Hook** 同步（属于 `onExit(DISCUSSING)` Hook 的职责，不是 Workflow Service 的职责）。v1.3 强制 **section 级幂等重写**规则：

1. 文档的每个 section（问题描述 / 使用场景 / 输入 / 输出 / 边界 / 验收标准 / 非功能要求）有**稳定的标题锚点**。
2. 每次写回**只替换对应 section 的内容**，不追加、不全删重建。
3. 如果 section 不存在则新建在固定位置；如果存在则原地覆盖。
4. 写回操作必须**幂等**：同一内容写多次结果一致，不产生重复段落。

**为什么这么严**：v1.2 方法论没有规定这条，首个参考实现的初版用了"全删重建"的偷懒方式，导致任何人工在文档里加的注解都会被下一轮 AI 写回抹掉。这是严重的信任破坏。section-rewrite 规则把"对正式文档的可预测性"作为一条硬约束。

#### 2.1.7 Bitable 需求追踪表（扩展为状态机 + 会话状态）

v1.2 的 Bitable 只记录**生命周期状态**。v1.3 的 Bitable 同时承担**会话状态存储**。原因：Coordinator Service 需要一份跨重启可恢复的"当前讨论进度"，而 Bitable 本身也是 Feishu Automation 的条件源，两用合一最省事。

**生命周期字段**（保留自 v1.2，状态枚举在 v1.3 替换为 7 态需求状态 + 后续层的状态）：

| 字段 | 类型 | 说明 |
|------|------|------|
| req_id | 文本（主键） | REQ-RISK-001 |
| 名称 | 文本 | 需求名称 |
| 项目 | 单选 | 项目代号 |
| 状态 | 单选 | 需求层（参考实现）：CREATED / DRAFTING / AI_REVIEW / HUMAN_CONFIRM / FINAL_REVIEW / APPROVED ； 规格层→交付层（待建）：SPEC_DRAFTING / SPEC_LOCKED / HARNESS_GENERATING / HARNESS_READY / IMPLEMENTING / CI_PENDING / STAGING / DEPLOYED |
| 创建人 | 人员 | |
| 创建时间 | 日期 | |
| 需求文档 | 链接 | 飞书文档 URL |
| 审查报告 | 链接 | 飞书文档 URL |
| Spec 版本 | 数字 | 1 |
| Spec PR | 链接 | GitHub PR URL |
| Harness PR | 链接 | GitHub PR URL |
| Impl PR | 链接 | GitHub PR URL |
| 当前卡点 | 单选 | 无 / 1a / 1b / 2 / 3 |
| 卡点1a 时间 | 日期 | Spec 确认时间 |
| 卡点1b 时间 | 日期 | Harness 确认时间 |
| 卡点2 时间 | 日期 | CI 通过确认时间 |
| 卡点3 时间 | 日期 | 发布确认时间 |
| 备注 | 文本 | 打回原因/阻塞说明 |

**v1.3 新增的五类会话状态字段**（概念层，不列完整 schema，实际字段名以参考实现为准）：

- **进度类**：`当前阶段` / `当前轮次` / `当前讨论字段` / `已完成字段` / `待补字段`
- **归属类**：`当前 Owner` / `当前接手角色`
- **闸门类**：`AI Ready` / `Human Confirmed`
- **追溯类**：`最近一次 review 结论` / `最近一次提问` / `最近一次写回时间`
- **UI 类**：`需要UI`（bool） / `UI设计稿链接`（text）

**命名一致性**：Bitable 实际字段名（含大小写）以参考实现为准；方法论正文不再单独描述字段名，避免命名漂移。

**参考实现约定**：字段真相源固定为仓库根目录的 `bitable_schema_v12.json`。任何字段新增、重命名、类型变更，必须先修改该 schema，再派生更新：

- Coordinator 写入映射
- Bitable 建表 / schema sync 脚本
- author / reviewer 可读字段 contract
- 远端 agent 模板中的字段说明

禁止直接在代码、Bitable 后台或 agent 模板里绕过 schema 单独新增字段，否则视为配置漂移。

#### 2.1.8 REQ ID 跨层穿透映射（保留自 v1.2，无变更）

| 层 | 载体 | REQ ID 出现位置 |
|---|---|---|
| 需求层 | 飞书 Bitable | 主键字段 |
| 需求层 | 飞书文档 | 文档标题前缀 |
| 规格层-A | GitHub branch | `spec/REQ-{PROJECT}-{NNN}` |
| 规格层-A | Spec/ACM 文件 | `metadata.req_id` 字段 |
| 规格层-B | Harness PR | PR title 包含 REQ ID |
| 生成层 | GitHub branch | `impl/REQ-{PROJECT}-{NNN}` |
| 所有卡点 | 飞书卡片 | 卡片标题包含 REQ ID |

#### 2.1.9 飞书文档目录结构（项目→需求映射）

```
飞书文档空间/
├── {项目名-A}/
│   ├── REQ-PRJA-001 {需求名称}/
│   │   ├── 需求文档              ← 文档同步 Hook 按 section 规则同步
│   │   ├── UI设计稿（可选）       ← UI 设计 Agent 生成（需要UI = true 时）
│   │   └── 审查报告              ← Reviewer Agent 生成，Hook 写入
│   ├── REQ-PRJA-002 {需求名称}/
│   │   └── ...
│   └── ...
├── {项目名-B}/
│   └── ...
└── _模板/
    ├── 需求文档模板
    └── UI设计简报模板
```

#### 2.1.10 需求版本管理

| 操作 | 处理方式 |
|------|----------|
| 新需求 | 在创建群发起"创建需求"命令 → 生成新 REQ ID |
| 需求修改（审查前） | 在 author 私聊里继续补全/修改，状态在 DRAFTING ↔ AI_REVIEW ↔ HUMAN_CONFIRM 之间循环 |
| 需求变更（审查后） | 走"打回"分支（REVIEWING → DISCUSSING），状态回到 DISCUSSING；若是大变更则新开 REQ ID 走 v2 |
| Bug 修复（已上线） | 不走需求层，直接在 GitHub 开 PR |

#### 2.1.11 UI 设计的嵌入方式（v1.4 更新：两阶段模型）

v1.4 正式定义 UI 设计的**两阶段模型**，区分两个目的不同、不可合并的阶段：

| 阶段 | 形态 | 时机 | 目的 | 受众 |
|---|---|---|---|---|
| **第一阶段：低保真线框图** | 组件树 + 交互说明 | `onEnter(HUMAN_CONFIRMING)`（Hook 层生成） | 验证 AI 是否理解了需求方向，辅助 author 判断 | 需求发起人 |
| **第二阶段：高保真可运行原型** | 可在浏览器运行的前端代码 | REQ APPROVED 后、Spec 生成前（独立阶段） | 视觉/交互全貌确认；产出 UI 技术合同供 Coding Agent 使用 | 产品/设计负责人 + Coding Agent |

**第一阶段（低保真，HUMAN_CONFIRMING）**：

1. 需求创建或首轮讨论时确定 `需要UI = true/false`（由 author 声明或 Author Agent 判定）。
2. 状态从 `AI_REVIEWING` 迁移到 `HUMAN_CONFIRMING` 时，`onEnter(HUMAN_CONFIRMING)` Hook：
   - 组装 AI 审查结论（结构化文字）。
   - 若 `需要UI = true`，调 UI 设计 Agent 生成低保真线框图（组件树 + 主要交互逻辑 + 线框图说明），写入飞书文档并更新 `UI设计稿链接`。
   - 把「审查结论 + 线框图链接」一起推送到 author 私聊。
3. Author 判断：认可 → `human_confirm_yes`；不认可（包括"文字对但 UI 方向不对"）→ `human_confirm_no` → 回 DISCUSSING，下次进入 HUMAN_CONFIRMING 时线框图重新生成。
4. `需要UI = false` 时跳过线框图生成，流程不受影响。

**第二阶段（高保真，APPROVED 后）**：

1. **触发条件**：REQ APPROVED 且 `需要UI = true`
2. **输入**：需求文档 7 字段 + 第一阶段低保真线框图 + 项目设计系统文档（Coordinator 从飞书读取）
3. **AI 生成内容**（以可运行前端代码为交付形式）：
   - 所有关键页面/视图的可交互原型（React/Vue 组件，可在浏览器中运行）
   - 核心状态的完整展示：空状态、加载态、错误态、成功态
   - 完整用户流程：主路径 + 主要异常路径
   - 设计决策说明：每个关键视觉/交互选择的依据
4. **人工 review**：视觉是否符合预期；交互是否符合习惯；风格是否与已有界面一致（对照设计系统文档）
5. **迭代**：AI 根据 review 意见修改原型，直到产品/设计负责人确认通过
6. **确认后**：Coordinator 将设计决策 append 进项目设计系统文档（飞书，append-only），更新 `UI设计稿链接`
7. **产物流向**：进入 Spec 生成时，AI 从高保真原型直接提取 UI 技术规格（组件树/接口/状态机）→ `design-ui.md`，无需凭空推导

**`需要UI = false` 的需求**：跳过两个阶段的 UI 生成，状态机和 Spec 生成流程完全不受影响。

**与分层工作流服务模式的契合**：UI 设计 Agent 属于能力层，是可替换的（今天是 design.md / UIUX ProMax，明天可以换 v0 / Figma Make / 其他）。Workflow Service 不感知 UI 工具，生成时机由 Hook 实现层控制。符合 §1.3 的三层分离原则。

---

**首个参考实现**：`Snowziio/requirement-workflow-feishu`。该仓库是需求层 Coordinator Service + OpenClaw Author/Reviewer 的首个落地版本，具体 schema、状态迁移表、section rewrite 规则、Agent 契约的实现细节见该仓库的 `docs/specs/` 目录。方法论正文保持与参考实现解耦，两边以定期人工对齐的方式维持一致。

---

### 2.2 规格层-A（Spec 子层）—— 需求层→GitHub 桥接

**目标**：将飞书中经审查的需求文档转化为 GitHub 中锁定的四层 Spec，为 AI Coding Agent 提供精确的技术约定。

> **设计原理：单向转化门**
>
> 需求写作（发散、频繁交互、飞书原生）和后续自动化（确定性、事件驱动、GitHub 管道）需要不同的工具。
> 解决方案：一个**单向转化门**：
> - 飞书 = 需求空间（自由、发散、OpenClaw 驱动协作）
> - GitHub = 锁定空间（结构化、确定性、自动化管道）
> - 转化门 = 卡点1a，由人工桥接或半自动完成
> - 转化后 GitHub 是唯一权威，飞书需求文档添加版本标记但不再更新

| 项目 | 内容 |
|---|---|
| 输入 | APPROVED 需求文档（含技术范围声明）+ 高保真 UI 原型（需要UI = true 时）+ 项目级上下文（ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照） |
| 输出 | 四层 Spec（requirements.md + design.md + acceptance.yaml + tasks.md）+ 可选 design-ui.md |
| 人工介入 | 仅 Design 层 review（卡点1a）——这是整个链路唯一需要深度人工判断的环节 |
| AI 的工作 | 从需求文档和注入的项目上下文，生成四层 Spec + 兼容性检查报告 |
| 索引 | 目录：`spec/REQ-{PROJECT}-{NNN}/`，所有文件含 `req_id` metadata |

#### 四层 Spec 结构

Spec 存储于 GitHub `spec/REQ-{PROJECT}-{NNN}/` 目录：

```
spec/REQ-PROJECT-001/
  requirements.md       ← Layer 1（自动生成，无需人工 review）
  design.md             ← Layer 2（AI 生成 + 卡点1a 人工 review，唯一卡点）
  design-ui.md          ← Layer 2 UI 技术规格（需要UI = true 时自动生成）
  acceptance.yaml       ← Layer 3 ACM（自动生成，人可在卡点1a 否决）
  tasks.md              ← Layer 4（自动生成，按依赖排序）
```

##### Layer 1：Requirements（自动生成）

从需求文档 7 字段自动转换为 EARS 格式用户故事。**无需人工 review**，仅作 AI 生成 Design 层的格式化中间产物。

```markdown
## 功能场景

### UC-001：提交风控报告
**When** 用户提交有效的营业执照和征信数据
**The system shall** 在 3 秒内返回包含 risk_level 的结构化风控报告

**When** 用户提交缺失 credit_score 的数据
**The system shall** 返回 422 错误，error_code 为 MISSING_CREDIT_SCORE

## 非功能约束
- 响应时间：P99 < 3s
- 可用性：99.9%
```

##### Layer 2：Design（AI 生成 + ⚡卡点1a 人工 review）

**这是整个链路唯一需要深度人工判断的层。** AI 注入三类上下文后生成：

**注入的项目级上下文**：
- `ARCHITECTURE.yaml`（现有服务/模块/接口）
- ACM 注册表（历史验收约束，用于兼容性检查）
- 技术范围声明（从需求文档读取，指定涉及的模块和操作类型）

```markdown
## 接口契约
POST /api/v1/risk-report
  Request:  { license_image: File, credit_report: CreditReport }
  Response: { risk_level: "low"|"medium"|"high", score: number, report_id: string }
  Errors:   422 MISSING_CREDIT_SCORE | 422 INVALID_LICENSE | 500 ANALYSIS_FAILED

## 数据模型变更
新增表：risk_reports
  - id: UUID（主键）
  - applicant_id: string（外键 → users.id）
  - risk_level: enum("low","medium","high")
  - created_at: timestamp

## 架构接合点
- 在 risk-assessment-service 新增 /api/v1/risk-report 路由
- 复用 license-parser 模块（已有，无需新建）
- 调用 CreditDataGateway（已有封装）

## 兼容性影响
[由 ACM 注册表兼容性检查自动生成]
- 无影响：该接口为全新接口，不修改现有接口
```

若 `需要UI = true`，同时生成 `design-ui.md`（从高保真原型直接提取，无需 AI 凭空推导）：

```markdown
## UI 技术规格

### 组件树
RiskReportPage
  ├── UploadSection（license_image + credit_report 上传）
  │   ├── FileUploader（复用现有组件）
  │   └── UploadProgress
  ├── SubmitButton（复用 PrimaryButton，loading 状态）
  └── ReportResult（条件渲染，提交成功后显示）
      ├── RiskBadge（risk_level 对应颜色标签）
      └── ScoreDisplay

### 组件接口
RiskBadge:
  props: { level: "low"|"medium"|"high" }
  states: low（绿色）/ medium（橙色）/ high（红色）

### 关键交互状态机
idle → uploading → submitted → success | error
```

##### Layer 3：ACM（验收标准矩阵，自动生成）

ACM 是连接"需求层约定"和"可执行 Harness 测试"的结构化桥梁，解决三个问题：
1. **消除歧义**：自然语言验收标准 → 机器可读的量化指标
2. **追溯链**：每个验收标准 ↔ 每个测试函数，一一对应
3. **版本兼容**：明确记录历史 AC 的继承和变更

```yaml
# spec/REQ-PROJECT-001/acceptance.yaml

req_id: REQ-PROJECT-001
spec_version: 1
created_at: 2026-04-08
locked_at: ""          # 卡点1a 确认时自动填充

acceptance_criteria:
  - id: AC-001
    priority: P0       # P0（必须）/ P1（重要）/ P2（次要）
    title: "有效输入返回风控报告"
    given:
      - "营业执照图片有效（jpg/png，< 5MB）"
      - "credit_report 包含 applicant_id 和 credit_score"
    input:
      license_image: "valid.jpg"
      credit_report: { applicant_id: "u001", credit_score: 720 }
    expected:
      status: 200
      body:
        risk_level: { enum: ["low", "medium", "high"] }
        score: { type: integer, min: 0, max: 100 }
    test_type: integration
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: ""      # 由规格层-B 生成后回填
    test_function: ""

  - id: AC-002
    priority: P0
    title: "缺失 credit_score 返回 422"
    input:
      license_image: "valid.jpg"
      credit_report: { applicant_id: "u001" }
    expected:
      status: 422
      body:
        error_code: "MISSING_CREDIT_SCORE"
    test_type: integration
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

compatibility:
  inherits_from: []       # 本版本基于哪些历史版本（新功能为空）
  breaking_changes: []
  impact_analysis: |
    本次为新功能首次发布，无历史版本约束。
  cross_feature_dependencies: []
```

**ACM 版本演进**：当需求变更时（如 v2 收紧性能要求），新版 ACM 继承历史 AC，变更的 AC 标记 `breaking_change: true`，由 ACM 兼容性检查脚本（工具9）自动生成 impact analysis 注入卡点1a 卡片。

##### Layer 4：Tasks（自动生成，按依赖排序）

```markdown
## 实现任务

### Task-1：数据模型
- 新建 risk_reports 表 migration（见 design.md 数据模型）
- 依赖：无

### Task-2：接口实现
- 在 risk-assessment-service 实现 POST /api/v1/risk-report
- 调用 license-parser 模块和 CreditDataGateway
- 对应 AC：AC-001
- 依赖：Task-1

### Task-3：错误处理
- 实现输入校验和错误返回
- 对应 AC：AC-002
- 依赖：Task-2

### Task-4：前端页面（需要UI = true）
- 实现 RiskReportPage（见 design-ui.md）
- 基于设计系统快照中现有组件
- 对应 AC：AC-UI-001
- 依赖：Task-2
```

#### Spec 生成流程（人工桥接 → 半自动化演进）

**Phase 1：人工桥接（当前实施）**

```
1. Coordinator 通知: "REQ-XXX-001 需求审查通过，可进入规格层"
2. 开发者:
   → git checkout -b spec/REQ-XXX-001
   → 从飞书读取需求文档 + UI 原型（如有）
   → 从 GitHub 读取 ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照
   → 使用 Claude Code / AI 工具生成四层 Spec 到 spec/REQ-XXX-001/ 目录
   → git push → 创建 PR
3. 开发者触发: Bitable 状态 → SPEC_DRAFTING → 触发卡点1a 飞书卡片
```

**Phase 2：半自动化（后续实施）**

```
1. 人: @Coordinator 创建Spec REQ-XXX-001
2. Coordinator:
   → 飞书 API: 读取需求文档 + UI 原型内容
   → GitHub API: 读取 ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照
   → 调用 Spec 转化 Agent: 需求文档 + 项目上下文 → 四层 Spec
   → GitHub API: 创建分支 spec/REQ-XXX-001，commit 四层 Spec 文件，创建 PR
   → 导出设计系统快照到 GitHub（specs/design-system-snapshot.yaml）
   → Bitable: 状态 → SPEC_DRAFTING，记录 PR 链接
   → 触发卡点1a 飞书卡片
```

#### Spec 版本管理规则

| 情况 | 处理方式 |
|------|----------|
| 现有功能报错 | 直接开 PR 修复，不需要新 Spec |
| 现有功能行为不符预期但测试通过 | Spec 验收标准写错了，需要新 Spec 版本 |
| 新增能力 | 新 Spec + 新 ACM |
| 性能改进 | 新 Spec 版本，ACM 中标记 `breaking_change: true` |

**⚡ 卡点1a（方案门）**：飞书发送确认卡片，包含：
- Design 层全文预览（接口契约 + 数据模型 + 架构接合点）
- ACM 验收标准清单（优先级 + given/expected 格式）
- 兼容性检查报告（与历史 ACM 的冲突点，AI 自动生成）
- 按钮：[确认提交] [返回修改]

确认后，四层 Spec 自动提交 GitHub，ACM 注册表新增条目，设计系统快照导出，Bitable 状态进入 SPEC_LOCKED，自动触发 Harness 生成。

---

### 2.3 规格层-B（Harness 子层）—— 需求契约代码化

**目标**：基于锁定的 ACM，由 AI 生成完整的 Harness 测试代码。

| 项目 | 内容 |
|---|---|
| 输入 | 锁定的 ACM（YAML）+ Spec（上下文补充）+ 历史 Harness 代码 |
| 输出 | harness/tests/{feature}/v{N}/ 下的完整测试代码 + 覆盖率矩阵 |
| 人的工作 | 审核覆盖率矩阵：每个 AC 是否有对应测试（卡点1b） |
| AI的工作 | 读取 ACM → 生成测试代码 → 回填 ACM 的 test_file/test_function 字段 |
| 自动化 | `spec-to-harness.yml` workflow 自动触发 |

#### Harness 目录结构（按功能+版本组织）

```
harness/tests/
├── risk-report/
│   ├── v1/                          # spec-v1 对应测试（历史只读）
│   │   ├── unit/
│   │   │   ├── test_ocr_parser.py
│   │   │   ├── test_credit_parser.py
│   │   │   └── test_error_handling.py
│   │   └── integration/
│   │       ├── test_api_output.py
│   │       └── test_performance.py
│   └── v2/                          # spec-v2 对应测试
│       ├── unit/
│       │   └── test_multilingual.py  # v2 新增
│       └── integration/
│           └── test_performance_v2.py  # v2 改进
├── ocr-service/
│   └── v1/
└── conftest.py                      # 共享 fixture
```

**关键规则**：
- 每个 spec 版本对应一个版本目录
- 历史版本目录**只读**，任何 PR 不得修改
- CI 运行 `pytest harness/tests/`（全量，包含所有历史版本）
- 新版本测试不得删除旧版本已覆盖的验收标准（除非显式 BREAKING CHANGE）

#### 覆盖率矩阵（供卡点1b 人工审核）

AI 生成 Harness 后，同时输出覆盖率矩阵文档：

```markdown
# 覆盖率矩阵 - risk-report v1

| AC 编号 | 验收标准 | 测试文件 | 测试函数 | CI 运行 |
|---------|---------|---------|---------|---------|
| AC-001  | 识别准确率>=95% | v1/unit/test_ocr_parser.py | test_ocr_field_accuracy | Yes |
| AC-002  | 响应时间<=30s | v1/integration/test_performance.py | test_report_generation_time | No (Staging) |
| AC-003  | 输出Schema合规 | v1/integration/test_api_output.py | test_report_schema_compliance | Yes |
| AC-004  | 错误处理场景 | v1/unit/test_error_handling.py | test_error_scenarios | Yes |

历史回归：无（v1 为首版）
```

#### 风控报告案例中的关键测试用例

```python
# harness/tests/risk-report/v1/unit/test_ocr_parser.py

import pytest

class TestOCRFieldAccuracy:
    """AC-001: 营业执照字段识别准确率 >= 95%"""

    def test_extract_company_name(self):
        """公司名称提取准确率测试"""

    def test_extract_registration_date(self):
        """注册日期提取并校验格式"""

    def test_handle_blurry_image(self):
        """模糊图片应返回明确错误，不得崩溃"""

    @pytest.mark.parametrize("image", STANDARD_TEST_IMAGES)
    def test_field_accuracy_batch(self, image):
        """批量准确率测试，assert accuracy >= 95"""


# harness/tests/risk-report/v1/integration/test_performance.py

@pytest.mark.performance
@pytest.mark.skipif_ci  # CI 不跑，仅 Staging
class TestPerformance:
    """AC-002: 报告生成时间 <= 30s"""

    def test_report_generation_time(self):
        """完整报告生成不超过 30 秒"""


# harness/tests/risk-report/v1/integration/test_api_output.py

class TestAPIOutput:
    """AC-003: 输出格式标准化"""

    def test_report_schema_compliance(self):
        """输出 JSON 必须通过 risk-report-schema-v1.json 验证"""

    def test_complete_report_matches_template(self):
        """端到端：标准材料输入 → 报告格式完全一致"""
```

**⚡ 卡点1b（Harness门）**：飞书发送确认卡片，包含：
- 覆盖率矩阵（每个 AC 对应的测试函数）
- 历史回归分析（v1 的测试是否仍通过）
- 按钮：[确认 Harness] [打回重生成]

确认后，harness/tests/ 目录状态冻结。此后进入生成层，AI **严禁修改** harness/tests/。

#### 视觉回归测试（UI 层的 Harness 等价机制）

当 `需要UI = true` 时，Harness 生成阶段同时生成视觉回归测试（与功能性 Harness 共同构成完整测试覆盖）：

**机制**：基于 Playwright 的截图比对
- 对所有 design-ui.md 中定义的关键视图生成初始截图基线（首次 CI 通过时建立）
- 后续每次 Impl PR 触发视觉回归测试：当前渲染结果 vs 截图基线
- 像素差异超过阈值 → PR 自动阻断，防止 Coding Agent 在实现时悄悄改动组件样式

**覆盖范围**：
- 所有 design-ui.md 中定义的关键视图（含 idle / loading / error / success 状态）
- 仅 P0 视觉 AC 对应的测试作为 Impl PR 合并门槛（与功能性 Harness 同等权重）

**与功能性 Harness 的关系**：视觉回归测试是 UI 层的"Harness"，两者在卡点1b 的覆盖率矩阵中分别列出；`需要UI = false` 时不生成，CI 流程不受影响。

---

### 2.4 生成层

**目标**：AI基于锁定的Harness生成实现代码，直到测试全部通过。

| 项目 | 内容 |
|---|---|
| 输入 | 锁定的 Harness + ACM + Spec + CLAUDE.md |
| 输出 | 实现代码（`src/`）+ 自测通过报告 + PR |
| 人的工作 | 无（除非 AI 多轮失败触发上报） |
| AI的工作 | 生成代码、本地运行测试、自修复、创建 PR |
| 自动化 | Docker 本地测试环境 + `harness-confirmed.yml` 触发 |

**层内子流程（AI 自主完成，人不感知）**：
```
读取 CLAUDE.md + ACM + Harness + Spec
    → 生成实现代码（只允许写 src/）
    → 本地 Docker 运行 harness/tests/（全量）
    → 失败 → 分析错误 → 修复 src/ 代码 → 再测试
    → 循环直到全部通过（最多 3 轮）
    → 超过 3 轮 → 停止，写 STUCK.md，飞书通知人工介入
    → 全部通过 → 创建 PR，附带测试通过报告
```

#### AI 自修复约束规则

```markdown
## AI 自修复规则（写入项目 CLAUDE.md）

### 文件权限（生成层阶段）
- 允许写入：src/, app/, tests/（业务辅助测试）
- 严禁修改：harness/tests/（已在卡点1b 冻结）
- 严禁修改：docs/specs/（已在卡点1a 冻结）

### 失败处理
- 同一测试失败超过 3 轮（含），必须停下来：
  1. 写 STUCK.md 说明：当前卡点、已尝试方案、错误日志
  2. 通过飞书通知人工介入（不是继续硬试）
- 禁止：修改测试以绕过失败
- 禁止：注释掉断言
- 禁止：使用 skip/xfail 装饰器跳过失败测试

### 测试运行
- 必须运行 harness/tests/ 全量（包含所有历史版本目录）
- 性能测试（@pytest.mark.performance）在本地可跳过，
  但 PR 描述中必须注明"性能测试待 Staging 验证"
```

**CLAUDE.md 约束规则**（风控报告项目示例）：
```markdown
# 风控报告生成服务

## 项目背景
为租赁平台提供AI驱动的自动风控报告生成能力。

## 当前任务阶段（由 workflow 自动设置）
# task: implement  ← spec/harness 阶段为 task: spec 或 task: harness

## 强制规则
- 先让 Harness 通过，再考虑代码优雅性
- 禁止修改 harness/tests/ 目录下的任何文件（生成层阶段）
- 禁止注释掉或 skip 任何失败测试
- 所有外部 API 调用必须有对应的 mock 用于测试
- 所有配置项走环境变量，禁止硬编码
- 同一测试失败超过 3 轮，停止并写 STUCK.md

## 安全规则
- 用户上传的文件处理完毕后立即删除，不得持久化
- 所有接口必须验证鉴权 token

## 技术栈
- Python 3.11 + FastAPI
- OCR: [指定服务]
- LLM: Claude API (claude-sonnet-4-6)
- 测试: pytest + httpx

## 本地开发
docker compose up -d        # 启动开发环境
docker compose run test     # 运行全套测试

## Harness 通过标准（CI 必须全绿）
- pytest harness/tests/ 全量通过（包含所有历史版本）
- 测试覆盖率 >= 80%
- docker build 成功
- 无安全漏洞（依赖检查通过）
```

---

### 2.5 验证层

**目标**：自动化执行Harness，给出明确的通过/失败信号。

| 项目 | 内容 |
|---|---|
| 输入 | PR（含实现代码） |
| 输出 | 测试报告（覆盖率、通过率、构建状态） |
| 人的工作 | 查看报告摘要，决定是否合并（卡点2） |
| AI的工作 | 失败时自动分析原因，写入PR评论 |
| 自动化 | GitHub Actions全自动运行 |

**GitHub Actions CI配置**（`.github/workflows/ci.yml`）：
```yaml
name: Harness Gate

on:
  pull_request:
    branches: [main, staging]

jobs:
  harness:
    runs-on: self-hosted  # ARM服务器
    steps:
      - uses: actions/checkout@v4

      - name: Run Full Harness
        run: |
          docker compose -f docker/docker-compose.test.yml up \
            --abort-on-container-exit \
            --exit-code-from test

      - name: Upload Test Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-report
          path: reports/

      - name: Notify Feishu on Failure
        if: failure()
        run: |
          python scripts/notify_feishu.py \
            --event "ci_failed" \
            --pr "${{ github.event.pull_request.number }}" \
            --report "reports/summary.json"

      - name: Notify Feishu on Success
        if: success()
        run: |
          python scripts/notify_feishu.py \
            --event "ci_passed" \
            --pr "${{ github.event.pull_request.number }}" \
            --report "reports/summary.json"
```

**⚡ 卡点2（质量门）**：飞书机器人发送通知 → 你查看报告摘要 → 点击"合并"或"拒绝"。

---

### 2.6 集成层

**目标**：合并后自动部署到Staging，支持功能Demo验收。

| 项目 | 内容 |
|---|---|
| 输入 | 合并到staging分支的代码 |
| 输出 | 可访问的Staging环境 + Smoke Test报告 |
| 人的工作 | 访问Staging验证功能Demo（卡点3前置） |
| AI的工作 | 无 |
| 自动化 | 构建镜像、部署、Smoke Test、通知 |

**分支策略**：
```
feature/xxx
    → PR → main（触发CI，卡点2）
main
    → 自动部署staging（触发集成层）
staging验收通过
    → 手动触发 → 客户环境（交付层，卡点3）
```

**风控报告案例的Smoke Test**：
```python
# smoke_test.py：部署后自动运行
def test_service_health():
    """服务健康检查接口响应正常"""

def test_sample_report_generation():
    """使用内置测试材料，生成一份完整风控报告"""
    # 验证：报告格式正确、风险等级字段存在、生成时间<30s
```

**⚡ 卡点3（发布门）**：飞书通知Staging就绪 → 你访问Demo → 点击"发布到客户环境"或"打回修改"。

---

### 2.7 交付层

**目标**：一键部署到客户环境，参数化隔离，自动健康检查。

| 项目 | 内容 |
|---|---|
| 输入 | 卡点3通过信号 + 客户配置文件 |
| 输出 | 运行中的客户生产环境 |
| 人的工作 | 触发部署命令（卡点3后自动或手动触发） |
| AI的工作 | 无 |
| 自动化 | 构建客户镜像、SSH部署、健康检查、失败回滚 |

**客户配置隔离方案**：
```
deploy/
├── customers/
│   ├── client-a.env    # 客户A的API密钥、数据库、域名等
│   └── client-b.env    # 客户B的配置
└── deploy.sh           # 通用部署脚本
```

```bash
# deploy.sh 核心逻辑
CUSTOMER=$1
source deploy/customers/${CUSTOMER}.env

docker compose -f docker/docker-compose.prod.yml up -d
# 等待健康检查
# 失败则自动回滚到上一版本
```

---

## 三、横向基础设施详解

### 3.1 人工协同轨（飞书 + OpenClaw 生态）

#### ⓪ 层间工作流服务与 OpenClaw 分工（v1.3 更新）

v1.3 对 OpenClaw 角色做了根本性调整：**OpenClaw 不再是工作流编排器，而是 AI Agent 能力提供层**。工作流编排职责由专用的层间工作流服务承担（见 §1.3）。

**三层结构**：

```
工作流服务层        Hook 实现层            Agent 能力层
─────────────────  ──────────────────────  ──────────────────
Coordinator        feishu_gateway.py       OpenClaw
Service            (Author/Reviewer        (提供 LLM 能力、
（状态机 +         Hook 实现)              飞书工具调用)
hook dispatcher）
                   checkpoint-handler      GitHub Actions
                   的卡点 Hook 实现        (CI/CD 能力)
```

**Coordinator Service 职责**（需求层工作流服务）：
- 状态机管理（7 状态，见 §2.1.2）
- Hook 触发（`onEnter` / `onExit` 每个状态节点）
- 真实来源（Bitable + JSON 持久化）
- 不持有任何 AI SDK 依赖

**OpenClaw 职责**（Agent 能力层）：
- 提供 Author Agent 能力（多轮引导需求填写）
- 提供 Reviewer Agent 能力（五维度审查）
- 提供 UI Design Agent 能力（可选，`需要UI=true` 时）
- 通过 Hook 接口被调用，不主动驱动状态机

**OpenClaw Skills 配置**：

| Skill | 用途 | 来源 |
|-------|------|------|
| `feishu-doc` | 读写飞书文档，Markdown↔飞书格式转换 | 官方 |
| `feishu-bitable-creator` | 创建和管理 Bitable 表 | 官方 |
| `feishu-automation` | 文档模板批量操作、变更通知 | 官方 |
| `requirement-writer` | 需求模板引导、完整度检查、历史约束注入 | 自定义 |
| `requirement-reviewer` | 需求审查五维度检查、审查报告生成 | 自定义 |
| `ui-design-bridge` | 调用 design.md / UIUX ProMax 生成 UI 设计稿 | 自定义 |
| `github-bridge` | GitHub API（分支/PR/文件操作） | 自定义 |
| `acm-validator` | ACM 兼容性检查（读取历史 ACM 比对） | 自定义 |

**工作流服务横向对比**：

| 维度 | Coordinator Service | checkpoint-handler |
|------|--------------------|--------------------|
| 覆盖层 | 需求层 | 规格层-B → 交付层 |
| 运行方式 | 独立服务（飞书 WebSocket） | 独立服务（飞书 WebSocket） |
| 状态存储 | Bitable + JSON 持久化 | 无持久状态 |
| 交互方式 | 创建群 / Author 私聊 / 项目群（三通道） | 仅飞书卡片按钮回调 |
| AI 能力来源 | OpenClaw（Hook 实现层调用） | GitHub Actions（CI/CD） |
| 卡点处理 | 卡点1a（方案门，HUMAN_CONFIRMING 状态） | 卡点1b/2/3 |

**两个工作流服务的协作接口**：
- 卡点1a 完成（`REQ_APPROVED`）→ Coordinator Service 更新 Bitable → 触发 GitHub 分支创建 → checkpoint-handler 接管
- 通信方式：共享 Bitable 表（Coordinator Service 写需求层状态，checkpoint-handler 写开发层状态字段）

负责回答五类核心问题：

#### ① 什么是真的（知识/规格权威来源）

| 阶段 | 工具 | 内容 |
|---|---|---|
| 需求期 | 飞书文档（OpenClaw 管理） | 需求文档、UI 设计稿、审查报告 |
| 开发期 | GitHub repo (`docs/`) | Spec、ACM、技术设计、架构决策（ADR） |
| 交付后 | 飞书知识库 | 客户档案、经验总结、可复用方案 |

**飞书知识库结构**：
```
飞书知识库/
├── 客户档案/
│   └── [客户名]/
│       ├── 项目背景与需求
│       ├── 关键技术决策
│       ├── 交付物说明
│       └── 经验与教训
├── 通用方案库/
│   ├── OCR集成方案
│   ├── LLM报告生成模式
│   └── 客户部署模板
└── AI提示词库/
    └── 经过验证的高效提示词
```

#### ② 发生了什么（事件与通知）

飞书机器人Webhook接收GitHub事件，发送到项目群：

| 事件 | 通知内容 | 接收群 |
|---|---|---|
| PR创建 | 新PR待CI验证 | 开发群 |
| CI通过 | 需要你合并（卡点2） | @你 |
| CI失败 | 失败原因摘要，AI分析结果 | 开发群 |
| Staging就绪 | 需要你验收Demo（卡点3） | @你 |
| 部署成功 | 客户环境已上线 | 开发群 |
| 部署失败 | 自动回滚，需人工介入 | @你 |

#### ③ 谁决定了什么（决策记录）

**飞书多维表格：决策记录库**（学习层核心）

| 字段 | 说明 |
|---|---|
| 项目/功能 | 风控报告 / OCR解析模块 |
| 卡点类型 | Spec确认 / 质量门 / 发布门 |
| 决策内容 | 通过 / 拒绝 / 附条件通过 |
| 理由与背景 | 为什么做这个判断 |
| 结果反馈 | 后续发现这个决策是否正确 |
| 客户类型标签 | 租赁 / 制造 / 零售… |
| 功能类型标签 | OCR / LLM分析 / 报告生成… |
| AI干预点 | 本次AI生成哪里需要人工修正 |

最后一个字段是CLAUDE.md改进的直接输入源。

#### ④ 下一步是什么（任务追踪）

使用飞书多维表格作为轻量项目看板：

```
状态列：待启动 / Spec编写中 / 开发中 / CI验证 / Staging验收 / 已交付
```

不需要复杂的项目管理工具，一张表够用。

#### ⑤ 学到了什么（知识沉淀）

**触发时机**：项目交付节点（不是每次功能上线）。

**过滤标准**："下一个类似客户项目开始时知道这件事，能省多少时间？"

**三个产出**：
1. 飞书知识库 → 客户档案（外部可见的结论）
2. CLAUDE.md更新 → AI上下文改善（AI干预点字段的直接输出）
3. 飞书多维表格 → 决策记录补充结果反馈

---

### 3.2 工程自动化轨（GitHub + CI/CD + 测试）

#### 代码仓库结构（所有项目通用模板，v1.1 更新）

```
project-name/
├── CLAUDE.md                        # AI工作说明书（最重要）
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                   # PR验证（卡点2触发）
│   │   ├── staging.yml              # 合并后自动部署staging
│   │   ├── deploy.yml               # 手动触发客户部署（卡点3后）
│   │   ├── spec-to-harness.yml      # 卡点1a后自动生成Harness（v1.1新增）
│   │   └── harness-confirmed.yml    # 卡点1b后触发AI实现（v1.1新增）
│   ├── ISSUE_TEMPLATE/
│   │   └── feature-spec.md          # Spec填写模板
│   └── PULL_REQUEST_TEMPLATE.md     # PR描述模板
├── docs/
│   ├── specs/                       # 需求规格文档（v1.1更新）
│   │   ├── risk-report-v1.md        #   结构化 Spec
│   │   ├── risk-report-v1-acceptance.yaml  #   ACM 验收标准矩阵
│   │   ├── risk-report-v1-api.yaml  #   API 契约（如有）
│   │   └── risk-report-v1-coverage-matrix.md  # 覆盖率矩阵（AI生成）
│   ├── designs/                     # 技术设计文档
│   └── decisions/                   # 架构决策记录（ADR）
├── harness/
│   └── tests/                       # 按功能+版本组织（v1.1更新）
│       ├── risk-report/
│       │   ├── v1/                  #   spec-v1 测试（卡点1b后只读）
│       │   │   ├── unit/
│       │   │   └── integration/
│       │   └── v2/                  #   spec-v2 测试（如有）
│       ├── ocr-service/
│       │   └── v1/
│       └── conftest.py              #   共享 fixture
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml           # 本地开发
│   ├── docker-compose.test.yml      # CI测试
│   ├── docker-compose.staging.yml   # Staging
│   └── docker-compose.prod.yml      # 生产
├── deploy/
│   ├── customers/                   # 客户配置文件（gitignore）
│   └── deploy.sh
├── scripts/
│   └── notify_feishu.py             # 飞书通知脚本
└── src/                             # AI生成的应用代码
```

#### 测试分层策略

| 层次 | 范围 | Mock策略 | 运行时机 |
|---|---|---|---|
| 单元测试 | 单个函数/类 | 全部mock外部依赖 | 每次CI |
| 集成测试 | 模块间交互 | Mock第三方API | 每次CI |
| 端到端测试 | 完整业务流程 | 使用测试账号/数据 | CI + Staging部署后 |
| Smoke测试 | 核心路径可用性 | 无mock，真实环境 | 每次部署后 |

#### GitHub Actions Runner配置

ARM服务器作为Self-hosted Runner，承担：
- CI测试执行（隔离Docker环境，每次测试后清理）
- Staging部署
- 飞书通知发送

**注意**：ARM架构需确认所有Docker基础镜像支持arm64，或使用`docker buildx`构建多架构镜像。

---

### 3.3 两轨接口：卡点设计（v1.1 更新为四卡点）

四个卡点是两轨之间的唯一接口。其中卡点1a（方案门）有**双门前置条件**（v1.3 新增），由 Coordinator Service 在工作流服务层强制执行，两个条件均满足才允许进入 REVIEWING 状态：

- **AI Ready**：Reviewer Agent 判定需求文档已达到审查标准（`ai_ready = true`）
- **Human Confirmed**：Author 在私聊确认"信息无误"（`human_confirmed = true`）

双门约束写在 Coordinator Service 的状态机中，不依赖 Hook 实现层的配合。

```
工程自动化轨产出结果
    → 飞书机器人通知（附报告摘要）
    → 你在飞书做判断（approve/reject）
    → 判断触发工程自动化轨下一步
    → 判断自动记录到飞书多维表格
```

#### 卡点总览

| 卡点 | 名称 | 触发时机 | 输入 | 按钮动作 |
|------|------|---------|------|---------|
| 1a | 方案门 | Spec 写完，AI 转化后 | Spec + ACM + 兼容性报告 | 确认提交 / 返回修改 |
| 1b | Harness门 | AI 生成测试代码后 | 覆盖率矩阵 + 测试代码 PR | 确认 Harness / 打回重生成 |
| 2 | 质量门 | CI 全通过 | 测试报告 + 覆盖率 | 合并 PR / 拒绝并注释 |
| 3 | 发布门 | Staging 部署就绪 | Smoke 报告 + Demo 地址 | 发布到客户 / 打回修改 |

#### 卡点消息格式

**卡点1a（方案门）**：
```
[卡点1a · 方案门] risk-report v1

Spec 产物：
  ✅ 结构化 Spec：risk-report-v1.md
  ✅ ACM 验收标准：4 条（P0:3, P1:1）
  ✅ API 契约：risk-report-v1-api.yaml
  ✅ 兼容性检查：无冲突（首版）

验收标准摘要：
  AC-001: 识别准确率 >= 95%
  AC-002: 响应时间 <= 30s
  AC-003: 输出 Schema 合规
  AC-004: 错误处理降级

[查看完整 Spec] [确认提交] [返回修改]
```

**卡点1b（Harness门）**：
```
[卡点1b · Harness门] risk-report v1 · PR #38

覆盖率矩阵：
  AC-001 → test_ocr_parser.py::TestOCRFieldAccuracy (4 cases)
  AC-002 → test_performance.py::test_report_generation_time (Staging only)
  AC-003 → test_api_output.py::test_report_schema_compliance
  AC-004 → test_error_handling.py::test_error_scenarios (3 cases)

  覆盖率：4/4 AC 全覆盖
  历史回归：无（首版）

[查看测试代码] [确认 Harness] [打回重生成]
```

**卡点2（质量门）**：
```
[卡点2 · 质量门] PR #42 · 风控报告OCR模块

✅ 测试结果：47/47 通过（含历史版本）
✅ 覆盖率：83%
✅ 构建：成功
⚠️  注意：test_blurry_image 耗时28.3s（接近30s上限）
📋 性能测试待 Staging 验证（AC-002）

[查看详细报告] [合并PR] [拒绝并注释]
```

**卡点3（发布门）**：格式不变，同 v1.0。

#### 按钮动作与 checkpoint-handler 映射

| 按钮 | checkpoint-handler action | 后续触发 |
|------|--------------------------|---------|
| 确认提交（1a） | `spec_confirm` | Spec/ACM 提交 GitHub → 触发 `spec-to-harness.yml` |
| 返回修改（1a） | `spec_reject` | 飞书通知返回草稿阶段 |
| 确认 Harness（1b） | `harness_confirm` | 合并 harness PR → 触发 `harness-confirmed.yml` |
| 打回重生成（1b） | `harness_reject` | harness PR 写评论 → 重新触发 AI 生成 |
| 合并 PR（2） | `merge` | GitHub API 合并 → 触发 `staging.yml` |
| 拒绝并注释（2） | `reject` | PR 评论 + 飞书通知 AI 修复 |
| 发布到客户（3） | `deploy` | 触发 `deploy.yml` |
| 打回修改（3） | `reject_staging` | GitHub Issue + 飞书通知 |

---

## 四、OA基础设施配置清单（飞书侧）

以下是需要在飞书中配置的完整清单：

### 4.1 飞书应用（自建应用）
- 创建一个飞书自建应用，获取App ID和Secret
- 配置权限：发送消息、读写多维表格、读写知识库、读写飞书文档
- 这是所有自动化的权限基础

### 4.2 OpenClaw Agent（v1.2 新增）
- 安装 OpenClaw 飞书插件
- 配置飞书连接（WebSocket 长连接）
- 安装官方 Skills: `feishu-doc`, `feishu-bitable-creator`, `feishu-automation`
- 开发并安装自定义 Skills: `requirement-writer`, `requirement-reviewer`, `ui-design-bridge`, `github-bridge`
- 在项目群中添加 OpenClaw Agent，配置 @mention 响应

### 4.3 飞书多维表格
- **需求追踪表**（v1.2 新增）：字段见2.1节 Bitable 表结构，所有项目共用一张表，按项目字段筛选视图
- **决策记录库**：字段见3.1节③，所有项目共用一张表
- **项目看板**：状态列视图（CREATED → ... → DEPLOYED）

### 4.4 飞书文档空间
- 创建项目文档空间，按2.1节目录结构组织
- 创建需求文档模板 + UI 设计简报模板
- 设置权限：仅内部成员可见

### 4.5 飞书知识库
- 按3.1节①的结构创建目录
- 设置权限：仅内部成员可见

### 4.6 飞书机器人（checkpoint-handler 用）
- 在开发项目群中添加机器人
- 配置Webhook地址（供GitHub Actions调用）

### 4.7 消息卡片模板（v1.2 更新为五类）
- 需求审查卡片：审查结果 + [通过，进入规格层 / 需要修改]
- 卡点1a（方案门）：Spec + ACM 摘要 + 兼容性报告 + [确认提交/返回修改]
- 卡点1b（Harness门）：覆盖率矩阵 + 历史回归 + [确认 Harness/打回重生成]
- 卡点2（质量门）：测试报告 + 覆盖率 + [合并PR/拒绝并注释]
- 卡点3（发布门）：Smoke 报告 + Demo 地址 + [发布到客户/打回修改]

---

## 五、需要自研的工具清单

以下是现有工具无法覆盖、需要自行开发的能力：

### 工具1：飞书通知脚本（`scripts/notify_feishu.py`）
**用途**：GitHub Actions调用，发送结构化卡点通知到飞书。
**输入**：事件类型、PR信息、报告摘要JSON。
**输出**：飞书消息卡片（含操作按钮）。
**复杂度**：低，一次开发，所有项目复用。

### 工具2：卡点响应处理器（飞书回调服务）
**用途**：接收飞书按钮点击事件，触发对应的GitHub API操作（合并PR、触发部署）并记录到多维表格。
**输入**：飞书消息卡片回调。
**输出**：GitHub API调用 + 多维表格写入。
**复杂度**：中，需要一个常驻的轻量Web服务（可部署在ARM服务器上）。
**说明**：这是整个自动化流程的关键枢纽，建议优先开发。

### 工具3：AI失败分析脚本（`scripts/analyze_failure.py`）
**用途**：CI失败时，自动调用Claude API分析测试日志，生成人类可读的失败原因摘要，写入PR评论。
**输入**：测试失败日志。
**输出**：结构化失败分析（原因 + 建议修复方向）。
**复杂度**：低，调用Claude API即可。

### 工具4：项目交付回顾模板生成器
**用途**：项目交付时，从决策记录库中提取本项目所有记录，生成回顾报告初稿，供人工整理后迁移到飞书知识库。
**输入**：项目名称（从多维表格拉取数据）。
**输出**：结构化Markdown回顾文档初稿。
**复杂度**：低。

### 工具5：客户部署脚本（`deploy/deploy.sh`）
**用途**：参数化部署到任意客户环境，含健康检查和自动回滚。
**输入**：客户名称（对应`.env`文件）。
**输出**：已运行的客户生产环境。
**复杂度**：中，需处理多种部署场景（公有云/私有云/托管）。

### 工具6：Spec 转化服务（v1.1 新增）
**用途**：接收飞书"提交 Spec"按钮事件，将飞书 PRD 草稿转化为结构化 Spec + ACM + API 契约，提交到 GitHub。
**输入**：飞书文档 ID（草稿内容）+ 历史 ACM 文件列表（从 GitHub 读取）。
**输出**：GitHub commit（docs/specs/ 下三个文件）+ 兼容性检查报告。
**复杂度**：中，核心是 AI 调用（将自然语言转为 YAML 结构）+ 兼容性比对逻辑。
**依赖**：飞书文档 API + GitHub API + Claude API。

### 工具7：Harness 生成 workflow（`spec-to-harness.yml`，v1.1 新增）
**用途**：卡点1a 确认后，自动触发 Claude Code CLI 读取 ACM 生成 harness/tests/ 测试代码。
**输入**：ACM YAML 文件路径 + 历史 harness 目录。
**输出**：harness PR + 覆盖率矩阵文档 + ACM 回填（test_file/test_function）。
**复杂度**：中，GitHub Actions workflow + Claude Code CLI 调用。

### 工具8：实现触发 workflow（`harness-confirmed.yml`，v1.1 新增）
**用途**：卡点1b 确认后，合并 harness PR，创建 impl 分支，触发 Claude Code CLI 生成实现代码。
**输入**：harness PR 编号 + Spec + ACM 路径。
**输出**：实现 PR（src/ 代码 + 测试通过报告）。
**复杂度**：中，GitHub Actions workflow + Claude Code CLI 调用。

### 工具9：ACM 兼容性检查脚本（v1.1 新增）
**用途**：对比新版 ACM 与历史版本 ACM，生成兼容性报告（新增/变更/删除的 AC，breaking changes 列表）。
**输入**：新 ACM YAML + 历史 ACM YAML 列表。
**输出**：兼容性报告（JSON/Markdown），注入飞书卡点1a 卡片。
**复杂度**：低，纯 YAML 解析 + 比对逻辑。

### 工具10：OpenClaw 自定义 Skill — requirement-writer（v1.2 新增）
**用途**：需求撰写 Agent 的核心 Skill，按需求模板逐项引导用户填写，实时写入飞书文档，检查完整度。
**输入**：飞书文档 ID + 需求模板结构。
**输出**：填写完成的需求文档 + 完整度检查报告。
**复杂度**：中，需要对话式引导逻辑 + feishu-doc API 调用。

### 工具11：OpenClaw 自定义 Skill — requirement-reviewer（v1.2 新增）
**用途**：需求审查 Agent 的核心 Skill，五维度检查（完整性/一致性/可测试性/历史冲突/UI对齐）。
**输入**：需求文档内容 + UI 设计稿内容（可选）+ Bitable 历史需求列表。
**输出**：审查报告（写入飞书文档）+ 通过/不通过判定。
**复杂度**：中，核心是 AI prompt 工程 + 历史数据查询。

### 工具12：OpenClaw 自定义 Skill — ui-design-bridge（v1.2 新增）
**用途**：桥接 UI 设计工具（design.md / UIUX ProMax），基于需求文档生成可被 Coding Agent 直接还原的 UI 设计稿。
**输入**：需求文档内容。
**输出**：UI 设计稿（组件树 + 样式规范 + 交互逻辑），写入飞书文档。
**复杂度**：中，主要是 AI 工具调用和格式转换。

### 工具13：OpenClaw 自定义 Skill — github-bridge（v1.2 新增）
**用途**：在 OpenClaw 中操作 GitHub（创建分支、提交文件、创建 PR、读取 ACM 历史）。
**输入**：操作类型 + 参数（仓库、分支名、文件内容等）。
**输出**：GitHub API 操作结果。
**复杂度**：低，封装 GitHub REST API 调用。
**说明**：半自动化阶段的关键工具，使 OpenClaw 能直接触发 GitHub 操作。

### 工具14：设计系统文档管理器（v1.4 新增）
**用途**：管理飞书侧项目设计系统文档的生命周期：创建初始文档、append 新设计决策、导出快照到 GitHub。
**输入**：项目名称 + 操作类型（create / append / export）+ 内容（Token / 组件记录 / UI 决策日志）。
**输出**：飞书文档更新结果 + GitHub 快照文件（`specs/design-system-snapshot.yaml`，export 时）。
**复杂度**：中，飞书 Docx API + GitHub API + append-only 写入逻辑。
**触发时机**：UI 设计阶段确认时（append）；卡点1a 通过时（export 到 GitHub）。

### 工具15：高保真 UI 原型生成 Agent（v1.4 新增）
**用途**：APPROVED 后（需要UI = true 时）生成可在浏览器运行的高保真前端原型，供产品/设计负责人做视觉/交互全貌确认。
**输入**：需求文档 7 字段 + 低保真线框图链接 + 设计系统文档（Coordinator 注入）。
**输出**：可运行的前端组件代码（覆盖所有关键状态：空态/加载/错误/成功）+ 设计决策说明。
**复杂度**：高，核心是 AI 生成前端原型代码 + 与设计系统的视觉一致性保障。
**注意**：属于能力层，可替换（v0 / Figma Make / design.md / UIUX ProMax 等）。Workflow Service 不感知具体工具。

### 工具16：ACM 注册表维护服务（v1.4 新增）
**用途**：维护 GitHub 侧 ACM 注册表（`specs/registry/consolidated.yaml`）：新条目追加、状态更新（finalized）、兼容性查询接口。
**输入**：操作类型（append / finalize / query）+ 新 ACM 文件路径 / REQ ID。
**输出**：更新后的 consolidated.yaml + 兼容性报告（query 时）。
**复杂度**：中，YAML 解析 + append-only 写入 + 兼容性比对逻辑（与工具9 ACM 兼容性检查脚本合并或复用）。
**触发时机**：卡点1a 通过时（append）；卡点1b 通过时（finalize）。

### 工具17：视觉回归测试生成器（v1.4 新增）
**用途**：基于 design-ui.md 自动生成 Playwright 视觉回归测试代码（UI 层的 Harness 等价机制）。
**输入**：design-ui.md（组件树 + 关键视图定义）+ 高保真原型代码（作为截图基线来源）。
**输出**：`harness/tests/REQ-{PROJECT}-{NNN}/visual/` 下的 Playwright 测试脚本 + 初始截图基线。
**复杂度**：中，Playwright 脚本生成 + 基线截图捕获 + CI 集成配置。
**触发时机**：Harness 生成阶段（需要UI = true 时与功能性 Harness 同步生成）。

---

## 六、实施路线图

### Phase 0：工程自动化轨地基（已完成 ✅）

**目标**：GitHub 侧基础设施就位。

```
✅ 创建项目模板仓库（Snowziio/harness-scaffold）
✅ 写好通用CLAUDE.md模板（规则部分）
✅ 配置ARM服务器GitHub Actions Self-hosted Runner
✅ 开发飞书通知脚本（工具1）
✅ 开发卡点响应处理器（工具2）
✅ 开发AI失败分析脚本（工具3）
✅ 开发客户部署脚本（工具5）
✅ 飞书 WebSocket 卡片回调端到端验证通过

验收：提交PR → CI自动跑 → 飞书收到通知 → 点按钮合并 → 自动部署Staging ✅
```

### Phase 1：人工协同轨地基 — OpenClaw + 飞书工作流（当前阶段）

**目标**：Coordinator Service 稳定运行，OpenClaw Author/Reviewer Agent 接入，需求创建到批准全流程跑通。

```
Step 1: OpenClaw 基础配置
□ 安装 OpenClaw 飞书插件，配置 WebSocket 连接
□ 安装官方 Skills: feishu-doc, feishu-bitable-creator, feishu-automation
□ 在项目群添加 OpenClaw Agent，验证 @mention 响应

Step 2: Bitable 需求追踪表
□ 创建 Bitable 表（字段见 2.1 节表结构）
□ 创建视图：按项目筛选、按状态分组看板
□ 验证 OpenClaw 能读写 Bitable（CRUD 测试）

Step 3: 飞书文档模板 + 目录结构
□ 创建需求文档模板（含历史约束参考占位区）
□ 创建 UI 设计简报模板
□ 搭建项目文档空间目录结构
□ 验证 OpenClaw 能从模板创建文档并写入内容

Step 4: 自定义 Skills 开发
□ requirement-writer（工具10）：引导式填写 + 完整度检查
□ requirement-reviewer（工具11）：五维度审查 + 审查报告生成
□ ui-design-bridge（工具12）：UI 设计工具桥接
□ github-bridge（工具13）：GitHub API 封装

Step 5: 端到端验证（用测试需求）
□ @OpenClaw 创建需求 → 文档创建 + Bitable 行插入
□ @OpenClaw 开始讨论 → 引导式填写 → 文档更新
□ @OpenClaw UI设计 → 设计稿生成 → 文档写入
□ @OpenClaw 进入审查 → 审查报告 → 飞书卡片确认
□ 确认后 → Bitable 状态 REQ_APPROVED → 通知进入规格层

验收：在飞书群中走完 创建→讨论→审查→通过 全流程，Bitable 状态正确流转
```

### Phase 2：需求层→规格层桥接

**目标**：打通飞书需求文档到 GitHub Spec/ACM 的转化链路。

```
□ 人工桥接验证：手动从飞书复制需求文档 → Claude Code 转化 → 提交 GitHub
□ 开发 ACM 兼容性检查脚本（工具9）
□ 开发 Spec 转化服务（工具6）：需求文档 → 结构化 Spec + ACM
□ checkpoint-handler 新增 spec_confirm/harness_confirm action
□ 飞书卡片模板扩展到 5 类
□ 端到端验证：需求审查通过 → Spec PR → 卡点1a 确认
```

### Phase 3：规格层→生成层自动化

**目标**：卡点1a 确认后全链路自动化。

```
□ 开发 spec-to-harness.yml workflow（工具7）
□ 开发 harness-confirmed.yml workflow（工具8）
□ 验证 CI 全量 harness/tests/（含版本目录结构）
□ 验证 AI 自修复闭环（失败→修复→重试，max 3轮）
□ 端到端验证：卡点1a → Harness 生成 → 卡点1b → AI 实现 → CI → Staging
```

### Phase 4：首个真实项目端到端

**目标**：用真实业务需求走完完整链路，验证整个框架可用性。

```
□ 选择一个真实需求（风控报告或其他）
□ 走完 需求层(飞书) → 规格层-A → 规格层-B → 生成层 → CI → Staging → 部署
□ 记录所有需要补丁的地方
□ 更新方法论文档和工具
```

### Phase 5：飞轮运转

**目标**：AI 上下文持续改善，交付质量稳定提升。

```
□ 验证 ACM 版本管理：Spec-v2 能否正确继承 v1
□ 飞书多维表格：卡点决策自动写入
□ 建立飞书知识库通用方案库
□ 验证飞轮效果：新项目 AI 干预点是否减少
□ 根据实际情况调整卡点判断标准
```

---

## 附录A：关键原则备忘

1. **Harness优先**：测试定义先于实现，测试是规格说明书。
2. **人只做判断**：四个卡点之外，人不介入具体执行。
3. **约束写入CLAUDE.md**：所有AI行为规则在此处定义，不依赖口头约定。
4. **知识及时沉淀**：每次项目交付后执行回顾，不积累技术债。
5. **工具服务于流程**：不为了用工具而用工具，工具选型以"最小化维护成本"为准。
6. **ACM 是枢纽**：自然语言 Spec 和可执行 Harness 之间必须经过 ACM 结构化桥梁，消除歧义。（v1.1）
7. **单向转化门**：飞书需求空间和 GitHub 锁定空间各司其职，边界处 AI 翻译、人确认。（v1.1）
8. **版本只增不改**：harness/tests/ 历史版本目录只读，Spec 文件只追加新版本。（v1.1）
9. **REQ ID 穿透**：需求 ID 从飞书文档标题贯穿到 GitHub 分支名、PR、ACM metadata，全链路可追溯。（v1.2）
10. **飞书内闭环**：需求层全部工作在飞书生态内完成，不提前进入 GitHub。（v1.2）

## 附录B：全链路流程总图（v1.3 更新）

```
┌─────────────────────────────────────────────────────────────────┐
│        飞书需求空间（Coordinator Service 管理，OpenClaw 提供 AI 能力）│
│                                                                 │
│  客户需求 → 发消息到创建群 → Coordinator Service 创建 REQ-XXX-001 │
│                    ↓                                            │
│  需求讨论（需求撰写 Agent 引导）→ 需求文档完成                     │
│                    ↓                                            │
│  UI 设计（可选，UI 设计 Agent）→ UI 设计稿完成                     │
│                    ↓                                            │
│  需求审查（需求审查 Agent）→ 飞书卡片 [通过/修改]                   │
│                    ↓ 通过                                        │
│  Bitable: REQ_APPROVED                                          │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓ 人工桥接（或半自动）
┌─────────────────────┼───────────────────────────────────────────┐
│              GitHub 锁定空间（结构化、自动化管道）                  │
│                      ↓                                          │
│  分支 spec/REQ-XXX-001 → Spec + ACM + API 契约                  │
│  ⚡ 卡点1a（方案门）：[确认提交] [返回修改]                        │
│                      ↓ spec-to-harness.yml                      │
│  Claude Code 生成 harness/tests/{feature}/v{N}/                 │
│  ⚡ 卡点1b（Harness门）：[确认] [打回]                            │
│                      ↓ harness-confirmed.yml                    │
│  Claude Code 生成 src/（Harness 只读）                           │
│  ⚡ 卡点2（质量门）：CI 全量通过 → [合并] [拒绝]                   │
│                      ↓ staging.yml                              │
│  ⚡ 卡点3（发布门）：Staging 验收 → [发布] [打回]                  │
│                      ↓ deploy.yml                               │
│  客户环境部署                                                    │
└─────────────────────────────────────────────────────────────────┘

Bitable 需求追踪表全程记录状态（Coordinator Service + checkpoint-handler 协作更新）
```

## 附录C：自研工具完成状态（v1.3 更新）

### 层间工作流服务（v1.3 新增类别）

| # | 工具 | 状态 | 位置 |
|---|------|------|------|
| W1 | Coordinator Service（需求层工作流服务） | ✅ 完成（参考实现） | `Snowziio/requirement-workflow-feishu` |
| W2 | 卡点响应处理器 / checkpoint-handler（规格→交付层） | ✅ 完成 | `services/checkpoint-handler/` |

### 脚本与 CI 工具

| # | 工具 | 状态 | 位置 |
|---|------|------|------|
| 1 | 飞书通知脚本 | ✅ 完成 | `scripts/notify_feishu.py` |
| 2 | AI 失败分析脚本 | ✅ 完成 | `scripts/analyze_failure.py` |
| 3 | 客户部署脚本 | ✅ 完成 | `deploy/deploy.sh` |
| 4 | 项目回顾生成器 | □ 待建 | — |
| 5 | Spec 转化服务 | □ 待建 | — |
| 6 | spec-to-harness workflow | □ 待建 | `.github/workflows/spec-to-harness.yml` |
| 7 | harness-confirmed workflow | □ 待建 | `.github/workflows/harness-confirmed.yml` |
| 8 | ACM 兼容性检查脚本 | □ 待建 | — |

### OpenClaw Hook 实现（Agent 能力层）

| # | 工具 | 状态 | 位置 |
|---|------|------|------|
| O1 | OpenClaw Skill: requirement-writer | □ 待建 | OpenClaw custom skill |
| O2 | OpenClaw Skill: requirement-reviewer | □ 待建 | OpenClaw custom skill |
| O3 | OpenClaw Skill: ui-design-bridge | □ 待建 | OpenClaw custom skill |
| O4 | OpenClaw Skill: github-bridge | □ 待建 | OpenClaw custom skill |

---

*版本：v1.3 | 日期：2026-04-10*
*v1.3 变更：层间工作流服务模式（§1.3）、需求层架构反转（Coordinator Service 主导）、7 状态机、双门约束、UI 设计 Hook 机制、Bitable 会话状态字段扩展*
*v1.2 变更：OpenClaw 集成、需求层四阶段子流程、Bitable 状态机、REQ ID 跨层穿透*
*v1.1 变更：规格层拆分、ACM 引入、四卡点模型、两阶段流程设计*
*首个参考实现：Snowziio/requirement-workflow-feishu*
