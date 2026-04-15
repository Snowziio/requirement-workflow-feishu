# Harness Engineering 全自动开发工作流：方法论
## v2.0 | 2026-04-14

> **文档定位**
>
> 本文是方法论的"总文档"，描述核心目标、设计哲学、架构原则、各层规格和职责边界。
> 它不涉及具体实现（字段 schema、代码模板、Agent 提示词等）。
> 实现细节见 `docs/context/layers/` 和 `docs/context/infra/` 下的各分文档。
>
> **细节文件索引**
>
> | 主题 | 文件 |
> |---|---|
> | 需求层实现规格 | [layers/requirement-layer.md](layers/requirement-layer.md) |
> | 规格层实现规格（Spec + Harness） | [layers/spec-harness-layer.md](layers/spec-harness-layer.md) |
> | 生成→交付层实现规格 | [layers/generation-delivery-layers.md](layers/generation-delivery-layers.md) |
> | 项目级上下文产物规格 | [infra/project-context.md](infra/project-context.md) |
> | 自研工具清单 | [infra/tooling.md](infra/tooling.md) |
> | 飞书基础设施配置 | [infra/feishu-setup.md](infra/feishu-setup.md) |
> | GitHub 仓库结构与 CI | [infra/github-structure.md](infra/github-structure.md) |
> | **分层上下文传递契约原则** | [infra/context-chain-principle.md](infra/context-chain-principle.md) |

---

## 一、核心目标与设计哲学

### 1.0 适用范围声明

**本方法论面向以下特定场景，超出此范围的系统需另行评估适用性。**

**目标场景定义**：面向企业内部或特定组织的、以功能交付为核心的中小型应用系统，具体特征为：

| 维度 | 范围描述 |
|---|---|
| **技术形态** | 前端以 H5 / 小程序 / 轻量 Web 为主，后端以 API 服务（REST / GraphQL）+ 轻量异步处理为主；单机或小规模服务器部署，无分布式基础设施运维需求 |
| **价值交付节奏** | 单个需求从提出到上线以天到周为单位，不以季度为单位 |
| **企业集成** | 深度嵌入企业 IM 平台（飞书 / 企业微信 / 钉钉），账号体系、权限模型、消息推送与平台打通；不需要独立建设 IAM 系统 |
| **AI 能力** | AI 作为功能模块集成（LLM 调用用于生成、分类、提取、对话），不涉及模型训练、嵌入向量管道、大规模推理基础设施 |
| **团队规模** | 1–10 人核心团队，无需多团队协作流程 |
| **用户规模** | 数十到数千活跃用户（企业内部用户，非 C 端百万量级） |
| **需求迭代频率** | 每月 1–10 个新需求 |
| **代码库规模** | 单 repo，ARCHITECTURE.yaml 架构条目在数十个以内 |

**在范围内的典型产品形态**：嵌入飞书/企业微信的内部工具、企业工作流自动化系统、带 AI 对话/生成能力的后台管理系统、轻量 SaaS（组织内部订阅）、工程效率工具（含本方法论自身的实现）。

**超出范围（暂不覆盖）**：大规模 C 端消费应用、iOS/Android 原生 App、K8s 分布式集群服务、金融/医疗强合规系统、通用开源框架/基础库、实时系统（硬性延迟要求 < 10ms）。

> 超出范围不意味着方法论完全不适用，而是指需要在适用范围内的规格基础上增加额外层次的设计，不能直接套用。

---

### 1.1 核心目标

**用一套标准化工作流，让 AI 成为主要开发执行者，人只在关键决策点介入。**

具体目标：
- 从客户需求到生产部署，全链路可重复、可追溯、可持续迭代
- AI 每次介入都有精确的约束输入（规格、测试、历史上下文），不靠猜
- 人的判断集中在四个卡点，其余全部自动化
- 随着需求积累，AI 干预点逐渐减少（飞轮效应）

### 1.2 核心设计哲学

**1. 规则化优先于个性化**

工作方法（需求讨论流程、Spec 生成流程、CI 配置、部署方式）对任何项目都是一样的。不因项目特性重新设计流程，而是共用同一套规则化工作流服务。

**2. 约定优于协商**

AI 的行为规则写入 CLAUDE.md 和 ACM，不靠每次对话约定。规格和测试代码是 AI 的"合同"，合同不清晰时不是靠重新沟通来解决，而是补充规格。

**3. 结构化产物驱动自动化**

自然语言（需求文档）→ 半结构化（EARS 用户故事）→ 结构化（ACM YAML）→ 可执行（Harness 测试代码）。每一步转化都有明确的格式约定，任何步骤均可被下游机器消费。

**4. 防漂移是基础设施问题，不是纪律问题**

架构漂移、视觉漂移、功能漂移根源在于每次迭代时 AI 缺乏持续积累的历史上下文，而不是因为 AI 不认真。解决方案是项目级上下文基础设施，让历史决定以结构化形式持续注入。

**5. 人工介入集中在判断，不在执行**

人不写代码、不写测试、不配置环境。人只在四个卡点做判断：方案对不对（卡点1a）、覆盖全不全（卡点1b）、质量达没达（卡点2）、效果符不符（卡点3）。

---

## 二、三维框架总览

整个工作流由三个维度构成：

```
┌─────────────────────────────────────────────────────────────────────┐
│                           横向基础设施                                │
│   人工协同轨（飞书 + OpenClaw）  ║   工程自动化轨（GitHub + CI）       │
├──────────╥──────────╥─────────╥──────╥──────╥────────╥─────────────┤
│  需求层   ║规格层-A  ║规格层-B ║生成层║验证层║集成层  ║交付层        │
│Coordinator║  Spec   ║Harness  ║      ║      ║        ║             │
│ Service  ║          ║        ║      ║      ║        ║             │
├──────────╨──────────╨─────────╨──────╨──────╨────────╨─────────────┤
│                     层内子流程（AI 自主处理）                          │
└─────────────────────────────────────────────────────────────────────┘

REQ ID（REQ-{PROJECT}-{NNN}）穿透全链路：
  飞书文档 → Bitable → GitHub branch → PR → ACM → Harness → Impl PR

四个人工卡点：
  ⚡ 1a  方案门（Design 层确认，规格层-A）
  ⚡ 1b  Harness 门（测试覆盖确认，规格层-B）
  ⚡ 2   质量门（CI 全量通过，验证层）
  ⚡ 3   发布门（Staging 验收，集成层）
```

**纵向流程**：从需求到交付的七层流水线（规格层拆为 A/B 两个子层），定义"做什么"。

**横向基础设施**：贯穿所有层的共用基础设施，分为人工协同轨（飞书 + OpenClaw）和工程自动化轨（GitHub + CI）。

**层内子流程**：每层内部的 AI 自主循环，人不感知，行为规则写入项目 CLAUDE.md。

---

## 三、核心架构原则

### 3.1 层间工作流服务三层分离

纵向流程每一层的工作方法高度规则化，与项目无关。将其抽为可复用的**层间工作流服务**，遵循严格的三层分离：

| 层 | 职责 | 关键性质 |
|---|---|---|
| **Workflow Service 层** | 状态机定义、状态转移、hook 派发、状态持久化 | 纯规则、无 AI、无具体业务动作、项目无关 |
| **Hook 实现层** | 状态转移动作的具体实现（onEnter / onExit 回调） | 业务逻辑所在地，调用能力层，可独立测试 |
| **能力提供层** | AI Agent、人工、外部 API 等可插拔能力 | 可替换、契约化、不持有状态 |

**三条不可违背的性质**：
1. Workflow Service 不 import 任何能力层 SDK。它只知道"状态 X → Y 时触发 Hook Z"。
2. 能力层替换零成本：换 Agent 工具只改 Hook 实现层，Workflow Service 一行不动。
3. 状态机和 Hook 实现可以分别独立测试，互不依赖。

**当前已落地的工作流服务**：

| 覆盖层 | 工作流服务 | 说明 |
|---|---|---|
| 需求层 | Coordinator Service | 需求层首个参考实现（`Snowziio/requirement-workflow-feishu`） |
| 规格层-B → 交付层 | checkpoint-handler | 卡点卡片、CI 触发、PR 创建 |
| 生成→验证→集成→交付层 | *待建* | 按同一模板扩展 |

**引入这条原则的教训**：v1.2 曾将 OpenClaw 作为主编排器，但 OpenClaw 的 session 按群绑定，无法跨群共享状态，也无法持久化跨进程状态。根因是把"能力层"错当"Workflow Service 层"来用。三层分离原则从架构上杜绝此类错误。

### 3.2 项目级上下文（防漂移基础设施）

每次迭代的 AI 从零推导历史决定，是架构漂移、视觉漂移、功能漂移的根因。解决方案是**项目级上下文**：跨 session 持久存在的结构化知识，在每次 AI 介入时注入。

#### 五层内容结构

| 层         | 内容                                      | 防止                      |
| --------- | --------------------------------------- | ----------------------- |
| **功能契约层** | ACM 注册表（所有已批准 REQ 的验收条件）、REQ 状态索引       | 功能漂移（新 Spec 与已有契约冲突）    |
| **架构快照层** | ARCHITECTURE.yaml（服务/模块/接口/数据模型）、ADR 归档 | 架构漂移（新实现破坏已有架构约定）       |
| **视觉规范层** | 项目设计系统文档（飞书）、设计系统快照（GitHub）             | 视觉漂移（新 UI 风格与已有界面不一致）   |
| **规范惯例层** | CLAUDE.md、技术栈声明                         | 代码风格漂移（每 session 自动热加载） |
| **需求历史层** | 需求文档集、UI 原型集（飞书）                        | 新需求构造时的历史背景参考           |

#### 双平面存储与职责分工

项目级上下文横跨飞书和 GitHub 两个平面。Coordinator Service 是同步枢纽：

```
飞书平面（人工协同轨）          GitHub 平面（自动化 Coding 轨）
  需求文档集（需求历史层）   ←→   ARCHITECTURE.yaml（架构快照层）
  UI 原型集（需求历史层）    ←→   ACM 注册表（功能契约层）
  项目设计系统文档（视觉层） ←→   设计系统快照（视觉层镜像）
                                CLAUDE.md（规范惯例层）
```

- **Coordinator Service**：管理飞书侧所有项目级资产；在 Spec 生成时导出快照到 GitHub
- **checkpoint-handler**：维护 GitHub 侧 ACM 注册表、ARCHITECTURE.yaml

**关键约束**：UI 设计发生在代码仓库建立之前，设计系统的主存储必须在飞书；GitHub 快照在 Spec 生成时导出，供 AI Coding Agent 消费。

所有更新 **append-only**，可追溯到触发它的 REQ ID。

#### 分层上下文传递契约

项目级上下文在层间的传递有明确的契约规范：每层设计必须显式声明消费哪些上下文、如何消费、产出哪些上下文、如何传递给下层、以及如何防止语义漂移。详见补充原则文档：[infra/context-chain-principle.md](infra/context-chain-principle.md)。

#### 冷热内存注入模型

参考 Codified Context 论文（arXiv 2602.20478），AI Coding Agent 按访问频率分层获取上下文：

| 层级                    | 内容                                        | 注入时机             |
| --------------------- | ----------------------------------------- | ---------------- |
| **热**（每 session 自动加载） | CLAUDE.md；ARCHITECTURE.yaml；当前 REQ 的 Spec | 进入编码 session 即加载 |
| **温**（按 REQ 加载）       | 当前 REQ 的 ACM；技术范围有重叠的历史 ACM               | Spec 生成时注入       |
| **冷**（按需查询）           | 完整 ACM 注册表；完整设计系统历史；ADR 归档                | 显式触发时查询          |

### 3.3 REQ ID 全链路穿透

`REQ-{PROJECT}-{NNN}` 是贯穿全链路的唯一索引，任何工件都能通过 REQ ID 追溯到源头需求：

| 工件 | REQ ID 出现位置 |
|---|---|
| 飞书需求文档 | 文档标题前缀 |
| Bitable 追踪表 | 主键字段 |
| GitHub 分支 | `spec/REQ-{PROJECT}-{NNN}`、`impl/REQ-{PROJECT}-{NNN}` |
| Spec/ACM 文件 | 文件 metadata 字段 `req_id` |
| Harness PR、Impl PR | PR 标题 |
| 飞书卡点卡片 | 卡片标题 |

### 3.4 四卡点人工介入模型

人的判断集中在四个预定义的卡点。卡点之外，人不介入执行。

| 卡点 | 名称 | 层 | 判断内容 | 判断权 |
|---|---|---|---|---|
| ⚡ 1a | 方案门 | 规格层-A | Design 层（接口契约 + 数据模型 + 架构接合点）是否合理；ACM 是否合理 | 技术负责人 |
| ⚡ 1b | Harness 门 | 规格层-B | 每个 AC 是否有对应测试；历史回归是否覆盖 | 技术负责人 |
| ⚡ 2 | 质量门 | 验证层 | CI 全量通过后，是否合并 PR | 技术负责人 |
| ⚡ 3 | 发布门 | 集成层 | Staging 功能 Demo 验收后，是否发布到客户环境 | 产品/客户负责人 |

**卡点的共同性质**：
- 飞书消息卡片发送，卡片上有操作按钮
- 按钮点击事件由 checkpoint-handler 接收，触发对应 GitHub 操作
- 每次判断记录到 Bitable，可追溯

---

## 四、纵向流程各层规格

> **细节文件与层的对应关系**
>
> 细节文件的粒度跟随层的**实现成熟度**而变化，不是机械一层一文件：
> - 已充分设计或实现的层 → 有独立细节文件，内容详实
> - 仍处于概念阶段的层 → 合并在共享文件中，内容以方法论描述为主
>
> 每层头部标注：`[实现状态]` + `细节文件`。
> 迭代规则：**当某层的设计开始产生可实现的细节时，对应细节文件同步更新**；若多层合并在一个文件中，当任一层成熟到需要独立详细规格时，从共享文件拆出。

### 4.1 需求层

> **实现状态**：✅ 已上线（Phase 1 完成）｜**细节文件**：[layers/requirement-layer.md](layers/requirement-layer.md)

**驱动者**：Coordinator Service（Workflow Service 层）+ OpenClaw Author/Reviewer Agent（能力层）

**目标**：将模糊的客户需求转化为经双闸门确认的结构化需求文档，进入规格层-A。

| | 内容 |
|---|---|
| **输入** | 客户描述（口头/文字/会议记录） |
| **输出** | 状态为 APPROVED 的需求文档，包含：问题描述、使用场景、半结构化输入/输出契约、边界、可测试断言式验收标准、非功能要求、技术范围声明 |
| **完成标准** | 通过 AI 审查（AI Ready = true）+ 人工确认（Human Confirmed = true）+ 正式审查通过（FINAL_REVIEW → APPROVED） |

**核心机制**：

**6 态状态机**：
```
CREATED → DRAFTING → AI_REVIEW → HUMAN_CONFIRM → FINAL_REVIEW → APPROVED
                    ↑___________↙              ↑__________↙        ↑________↙
                  （AI退回）              （人工打回）          （审查打回，回 DRAFTING）
```

**双闸门**：AI Ready + Human Confirmed 两道独立的门，分别记录、分别失败、分别追溯。任何一道门失败都回 DRAFTING，不相互污染。双门均通过才能进入 FINAL_REVIEW 阶段。

**三方交互模型**：
- 创建群：发起需求创建，接收 REQ ID
- Author 私聊：字段补全讨论（私密，避免群噪声）
- 项目群：正式审查卡片，项目干系人参与判断

**需求文档格式**：8 个固定 section（问题描述 / 使用场景 / 输入 / 输出 / 边界 / 验收标准 / 非功能要求 / 技术范围声明），后续 section-level 幂等重写（不允许全删重建）。输入/输出格式要求到字段名 + 类型 + 约束粒度，不接受纯自然语言描述；验收标准格式要求为可测试断言（给定输入 → 期望输出 → 判断方式）；技术范围声明是 Spec 生成的必要输入。

**UI 两阶段模型**（`needs_ui = true` 时）：
- **第一阶段（低保真线框图）**：`onEnter(HUMAN_CONFIRM)` 时生成，辅助 author 判断 AI 是否理解需求方向
- **第二阶段（高保真可运行原型）**：REQ APPROVED 后、Spec 生成前独立执行，视觉/交互全貌确认，产出 UI 技术合同；确认后设计决策 append 进项目设计系统文档

**参考实现**：`Snowziio/requirement-workflow-feishu`。实现细节见 [layers/requirement-layer.md](layers/requirement-layer.md)。

---

### 4.2 规格层-A（Spec 子层）

> **实现状态**：⚙️ 设计完成，待实现（Phase 2）｜**细节文件**：[layers/spec-harness-layer.md](layers/spec-harness-layer.md)

**驱动者**：checkpoint-handler（卡点1a 后）+ Spec 转化 Agent（Phase 2 半自动化）

**目标**：将 APPROVED 需求文档转化为 GitHub 中锁定的四层 Spec，为 AI Coding Agent 提供精确技术约定。

| | 内容 |
|---|---|
| **输入** | APPROVED 需求文档（含技术范围声明）+ 高保真 UI 原型（`needs_ui = true` 时）+ 项目级上下文（ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照） |
| **输出** | 四层 Spec（requirements.md + design.md + acceptance.yaml + tasks.md）+ 可选 design-ui.md；存入 `spec/REQ-{PROJECT}-{NNN}/` |
| **完成标准** | 卡点1a（方案门）通过：Design 层经技术负责人确认，ACM 条目完整，兼容性检查无阻断冲突 |

**核心机制**：

**单向转化门**：飞书（需求空间，发散、自由）→ 卡点1a（人工桥接）→ GitHub（锁定空间，确定性、自动化管道）。转化后 GitHub 是唯一权威。

**两阶段 Spec 模型**（关键概念，避免两轨混淆）：

| 阶段 | 载体 | 结构 | 目的 | 可变性 |
|---|---|---|---|---|
| **Spec 草稿（阶段一）** | 飞书 Spec 文档（9 节模板） | 人可读、协作友好 | 技术负责人与 spec-author Agent 讨论、定稿 | 卡点1a 通过前可修改 |
| **Spec 结构化（阶段二）** | GitHub `spec/REQ-{PROJECT}-{NNN}/` 四文件 | 机器可解析（YAML/Markdown） | 喂给 `spec-to-harness.yml` 等自动化管道 | 卡点1a 通过后锁定；仅允许补丁提交 |

阶段一在飞书完成是为了让"讨论与决策"发生在人最熟悉的协作空间；阶段二转到 GitHub 是因为 ACM/Harness/CI 需要确定性的文件结构。卡点1a 是两阶段之间的唯一转化点，一旦通过则飞书 Spec 文档冻结（仅留作历史追溯），后续任何变更在 GitHub 侧以 PR 形式进入。

**四层 Spec 结构**（指阶段二）：

| 层 | 文件 | 生成方式 | 人工介入 |
|---|---|---|---|
| Layer 1 Requirements | requirements.md | 自动（从需求文档 8 字段转为 EARS 格式） | 无（格式化中间产物） |
| Layer 2 Design | design.md（+ design-ui.md） | AI 生成（注入 ARCHITECTURE.yaml + ACM 注册表） | **卡点1a**——唯一人工判断点 |
| Layer 3 ACM | acceptance.yaml | 自动（从 EARS 需求和 Design 层推导） | 卡点1a 时可否决 |
| Layer 4 Tasks | tasks.md | 自动（按 AC 依赖关系排序生成实现任务） | 无 |

**Design 层是整个链路唯一需要深度人工判断的文件**：接口契约（路径/请求/响应/错误码）+ 数据模型变更 + 架构接合点（复用哪些模块，新建什么）+ 兼容性影响（与历史 ACM 的冲突分析）。

**注入的三类项目级上下文**：`ARCHITECTURE.yaml`（现有模块和接口）+ ACM 注册表（历史验收约束）+ 设计系统快照（UI 技术规格来源，`needs_ui = true` 时）

实现细节见 [layers/spec-harness-layer.md](layers/spec-harness-layer.md)。

---

### 4.3 规格层-B（Harness 子层）

> **实现状态**：⚙️ 设计完成，待实现（Phase 3）｜**细节文件**：[layers/spec-harness-layer.md](layers/spec-harness-layer.md)

**驱动者**：`spec-to-harness.yml` GitHub Actions workflow

**目标**：基于锁定的 ACM，由 AI 生成完整的可执行 Harness 测试代码，覆盖所有 AC。

| | 内容 |
|---|---|
| **输入** | 锁定的 ACM（acceptance.yaml）+ Spec（上下文补充）+ 历史 Harness 代码（避免重复） |
| **输出** | `harness/tests/REQ-{PROJECT}-{NNN}/` 下按 AC 组织的测试代码 + 覆盖率矩阵文档 |
| **完成标准** | 卡点1b（Harness 门）通过：每个 AC 有对应测试文件，历史回归覆盖 |

**核心机制**：

**ACM 是 Harness 生成的唯一输入**：每个 AC 的 `given / input / expected` 字段直接对应测试用例的 fixture 和 assertion，AI 无需推断。

**P0 测试是 Impl PR 合并门槛**：priority = P0 的 AC 对应测试必须全部通过，PR 才能合并。P1/P2 允许后续补齐。

**视觉回归测试（`needs_ui = true` 时）**：与功能性 Harness 并行生成。基于 Playwright 的截图比对——对 design-ui.md 定义的关键视图建立截图基线；后续每次 Impl PR 触发比对，超过阈值则阻断 PR。这是 UI 层的 Harness 等价机制，防止 Coding Agent 悄悄改动组件样式。

**历史只读**：已通过卡点1b 的 Harness 目录不得在后续 PR 中修改，只能在新版本目录追加。

---

### 4.4 生成层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（4.4–4.7 合并，待层成熟时拆分）

**驱动者**：`harness-confirmed.yml` GitHub Actions workflow 触发 Claude Code CLI

**目标**：AI 基于锁定的四层 Spec + Harness 自主生成实现代码，直到所有 P0 Harness 通过。

| | 内容 |
|---|---|
| **输入** | 锁定的 Harness（只读）+ 四层 Spec（requirements + design + tasks）+ CLAUDE.md（行为规则）+ 项目级上下文（热加载） |
| **输出** | 通过所有 P0 Harness 测试的实现 PR |
| **完成标准** | CI 全量 Harness 通过（P0 全绿），进入验证层 |

**关键约束**：
- AI **禁止修改** `harness/tests/` 目录（由 CLAUDE.md 和 CI 双重强制）
- AI **禁止修改** `spec/` 目录
- 自修复循环有最大次数上限（默认 3 轮），超限则暂停等待人工介入
- CLAUDE.md 规定当前任务阶段（task: implement），AI 只做实现工作

---

### 4.5 验证层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（4.4–4.7 合并，待层成熟时拆分）

**驱动者**：GitHub Actions CI（自动）+ checkpoint-handler（卡点2）

**目标**：对实现 PR 全量运行 Harness，给出明确的通过/失败信号，触发卡点2。

| | 内容 |
|---|---|
| **输入** | 实现 PR（含完整代码变更） |
| **输出** | 测试报告（全量覆盖率、通过率、构建状态）+ 失败时的 AI 分析摘要（写入 PR 评论） |
| **完成标准** | 卡点2（质量门）通过：技术负责人审查报告后点击合并 |

**AI 参与点**：CI 失败时，AI 分析脚本自动调用 Claude API 解析失败日志，生成结构化失败摘要写入 PR 评论，减少人工排查时间。

---

### 4.6 集成层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（4.4–4.7 合并，待层成熟时拆分）

**驱动者**：`staging.yml` GitHub Actions workflow（合并后自动触发）

**目标**：合并后自动部署到 Staging 环境，运行 Smoke Test，触发卡点3。

| | 内容 |
|---|---|
| **输入** | 合并到 staging 分支的代码 |
| **输出** | 可访问的 Staging 环境 + Smoke Test 报告 |
| **完成标准** | 卡点3（发布门）通过：产品/客户负责人在 Staging 验收功能 Demo 后确认发布 |

**Smoke Test 定义原则**：仅验证核心路径可用性（服务健康 + 主要业务路径能跑通），不追求完整覆盖。完整覆盖由 Harness 承担。

---

### 4.7 交付层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（4.4–4.7 合并，待层成熟时拆分）

**驱动者**：`deploy.yml` GitHub Actions workflow（卡点3 后触发）

**目标**：参数化部署到客户环境，自动健康检查，失败自动回滚。

| | 内容 |
|---|---|
| **输入** | 卡点3 通过信号 + 客户配置文件（`.env` 隔离） |
| **输出** | 运行中的客户生产环境 |
| **完成标准** | 健康检查通过，服务在客户环境响应正常 |

**客户隔离原则**：每个客户一份独立的配置文件，部署脚本参数化，不存在跨客户的配置污染。

---

## 五、横向基础设施

### 5.1 人工协同轨（飞书 + OpenClaw）

覆盖需求层到 Spec 生成前的全部人工协作活动。

**核心服务**：
- **Coordinator Service**：需求层 Workflow Service，持有 7 态状态机和会话状态，管理飞书侧项目级上下文资产
- **OpenClaw**：能力提供层，运行 Author Agent / Reviewer Agent / UI 设计 Agent 等 Skills

**OpenClaw 在三层架构中的位置**：属于能力层，不拥有状态、不掌控流程。通过 Hook 接口被调用。今天是 OpenClaw，明天可以换成 Claude 直连或其他工具，Coordinator Service 一行不动。

**人工协同轨回答五类问题**：

| 问题 | 工具 |
|---|---|
| 什么是真的（规格权威） | 飞书需求文档（需求期）→ GitHub Spec（规格期后） |
| 发生了什么（事件通知） | 飞书机器人 Webhook（GitHub → 飞书） |
| 谁决定了什么（决策记录） | Bitable 决策记录表 |
| 下一步是什么（任务追踪） | Bitable 需求追踪看板 |
| 学到了什么（知识沉淀） | 飞书知识库（项目交付节点整理） |

### 5.2 工程自动化轨（GitHub + CI）

覆盖 Spec 锁定后的全部自动化执行。

**核心服务**：
- **checkpoint-handler**：规格层-B 到交付层的 Workflow Service，处理卡点1b/2/3 的卡片回调，维护 ACM 注册表和 ARCHITECTURE.yaml
- **GitHub Actions**：CI 执行、Harness 生成触发、Staging 部署、客户部署

**工程自动化轨的核心约束**：
- `harness/tests/` 历史版本目录只读
- `spec/` 目录只在 spec 分支修改，合并后锁定
- CLAUDE.md 是 AI Coding Agent 唯一的行为规则来源
- 所有状态变更通过 checkpoint-handler 记录到 Bitable

### 5.3 两轨协作接口

两轨通过 Bitable 共享状态，通过飞书卡片按钮传递人工决定，通过 GitHub API 触发工程动作。

**协作接口定义**：

| 事件 | 触发方 | 接收方 | 传递内容 |
|---|---|---|---|
| REQ APPROVED | Coordinator Service | checkpoint-handler（间接，通过 GitHub 分支创建） | REQ ID + 需求文档位置 |
| 卡点1a 通过 | 人（飞书卡片按钮） | checkpoint-handler | Spec PR 编号 |
| 卡点1b 通过 | 人（飞书卡片按钮） | checkpoint-handler | Harness PR 编号 |
| CI 通过/失败 | GitHub Actions | checkpoint-handler | PR 编号 + 报告 |
| Staging 就绪 | checkpoint-handler | 人（飞书通知） | Staging URL |
| 卡点3 通过 | 人（飞书卡片按钮） | checkpoint-handler | 客户名称 |

---

## 六、实施路线图

### Phase 0：工程自动化轨地基（已完成 ✅）

目标：GitHub 侧基础设施就位，CI → 飞书通知 → 卡点确认 → 部署的端到端链路跑通。

已完成：项目模板仓库（harness-scaffold）、CLAUDE.md 模板、Self-hosted Runner、飞书通知脚本、checkpoint-handler、AI 失败分析脚本、客户部署脚本、飞书 WebSocket 卡片回调验证。

### Phase 1：需求层上线（已完成 ✅）

目标：Coordinator Service 稳定运行，OpenClaw Author/Reviewer Agent 接入，需求全流程（创建 → 讨论 → 审查 → APPROVED）跑通。

已完成：Coordinator Service 部署（`admin@47.251.81.45:8004`）、Author/Reviewer Agent 接入、Bitable 状态流转、正式文档 section-rewrite。

### Pre-Phase-2：需求层稳固与 ARCHITECTURE.yaml 注入（当前进行中）

目标：在启动需求层→规格层桥接之前，补齐需求层存在的信息漂移风险和项目级上下文缺口，避免问题带入下一阶段。

关键任务：
- **ARCHITECTURE.yaml 注入链路**：`fetch-context` 返回项目级 `github_repo_url`，spec-author 在启动时通过 GitHub API 读取 ARCHITECTURE.yaml 并注入上下文
- **既有项目 `github_repo_url` 绑定机制**：创建群引导流程中补充 GitHub 仓库绑定步骤，project_configs 持久化
- **SPEC_DRAFTING 超时提醒**：防止 Spec 会话长时间无进展，Coordinator 侧定时扫描
- **ARCHITECTURE.yaml 启动脚本**：针对已有仓库通过 `bootstrap_architecture.py` 扫描生成初版
- **文档体系清理**：方法论、层次契约、现有环境文档的冲突/冗余统一，作为 Phase 2 实现的干净底座

### Phase 2：需求层→规格层桥接（待启动，依赖 Pre-Phase-2 完成）

目标：打通 APPROVED 需求文档到 GitHub 四层 Spec 的生成链路，卡点1a 跑通。

关键任务：需求文档格式升级（半结构化输入/输出 + 技术范围声明）、UI 设计第二阶段实现、Spec 转化 Agent、ACM 兼容性检查、设计系统文档管理、卡点1a 飞书卡片。

### Phase 3：规格层-B → 生成层自动化（待建）

目标：卡点1a 确认后，Harness 生成 → 卡点1b → AI 实现 → CI 全量自动化。

关键任务：`spec-to-harness.yml` workflow、`harness-confirmed.yml` workflow、视觉回归测试生成、AI 自修复闭环。

### Phase 4：首个真实项目端到端（待建）

目标：用真实业务需求走完完整链路，验证框架可用性，记录需要补丁的地方。

### Phase 5：飞轮运转（持续）

目标：ACM 注册表积累，ARCHITECTURE.yaml 持续更新，AI 干预点逐渐减少，验证飞轮效应。

---

## 附录：关键术语表

| 术语 | 含义 |
|---|---|
| **REQ ID** | 需求唯一标识符，格式 `REQ-{PROJECT}-{NNN}`，穿透全链路 |
| **ACM** | Acceptance Criteria Matrix，验收标准矩阵，YAML 格式，连接自然语言 Spec 和可执行测试 |
| **Harness** | 基于 ACM 生成的可执行测试代码集合，是 Impl PR 合并的前提 |
| **Coordinator Service** | 需求层 Workflow Service，持有状态机和会话状态，参考实现：`Snowziio/requirement-workflow-feishu` |
| **checkpoint-handler** | 规格层-B 到交付层的 Workflow Service，处理卡点回调 |
| **EARS 格式** | Easy Approach to Requirements Syntax：`When X, the system shall Y`，需求文档到 Spec 的格式化中间产物 |
| **项目级上下文** | 跨 session 持久存在的五层结构化知识，防漂移基础设施 |
| **设计系统文档** | Coordinator 管理的飞书文档，记录项目 UI 组件库、Token、交互模式和历次设计决策 |
| **设计系统快照** | 设计系统文档在 Spec 生成时导出到 GitHub 的版本，供 AI Coding Agent 消费 |
| **双闸门** | AI Ready + Human Confirmed，需求层两道独立的准入条件 |
| **三层分离** | Workflow Service / Hook 实现 / 能力提供 三层职责分离原则 |
| **层内子流程** | 各层内部 AI 自主循环，行为规则写入 CLAUDE.md，人不感知 |
| **P0 测试** | 优先级最高的 Harness 测试，Impl PR 合并的硬性门槛 |

---

*v2.0 | 2026-04-14 | 方法论文档重构：总-分结构，实现细节移入 layers/ 和 infra/ 细分文件*
