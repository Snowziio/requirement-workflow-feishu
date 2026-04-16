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

## 二、术语与产出物地图

> 本节提供「先看这里」的概念索引：业界对齐术语、各层产出物一览、跨层核心概念词、易混词辨析。每条词条只给最小定义与跳转锚点；完整 A-Z 索引见文末附录。

### 2.1 业界术语对齐

本方法论不是自创框架,而是业界 `harness engineering` 工程实践在"需求→架构演化"场景下的一次具体落地。下表把业界主流词汇映射到本文术语,读者可据此把本文放回更大的业界语境。

| 业界术语 | 一句话释义 | 本文对应 |
|---|---|---|
| **Harness engineering** | 2025–2026 业内共识:围绕 LLM 构建可自驱 coding Agent 所需的全部结构化支撑层 | 本方法论的总名 |
| **Agent = Model + Harness** | Agent 能力 = 模型能力 × 工程脚手架完备度 | §1 基础设施假设 |
| **Guides(前馈) / Sensors(反馈)** | Martin Fowler 控制论视角:前馈给约束,反馈给偏离信号 | **约束集**(Guides) / **反馈集**(Sensors),见 §5.2 |
| **Computational / Inferential** | 可机械判定(pytest / schema) vs 需判断(LLM judge / 人工 review) | 卡点与 AI 审查的二分;Computational 优先、Inferential 兜底 |
| **Generator-Evaluator loop** | Anthropic "Building Effective Agents" 模式:生成-评审-驳回-再生成 | §5.2 **转化博弈机制**:spec-transformer + spec-transformer-reviewer |
| **Spec-Driven Development (SDD)** | 学术/工程社区的规格先行范式,六要素:outcomes/scope/constraints/prior decisions/tasks/verification | 本文四文件 Spec 覆盖全部六要素 |
| **Rigid tests block completion** | OpenAI Codex 硬约束:测试不通过即不算完成 | P0 Harness 门 + regression scan |
| **Externalized memory** | 外部化记忆(markdown / yaml,而非 token-中的 context) | 项目级上下文五层 + acm-registry.yaml |

深度对齐分析:[infra/harness-engineering-industry-alignment-2026-04-16.md](infra/harness-engineering-industry-alignment-2026-04-16.md)。

### 2.2 各层产出物一览

按七层流水线枚举每层的驱动者、原始产出、派生产出、核心概念词。详细规格见 §5。

| 层 | 驱动者 | 原始产出 | 派生产出 | 核心概念词 |
|---|---|---|---|---|
| 需求层 / Requirements | Coordinator Service | 飞书需求文档(8 节) | — | REQ ID · 双闸门 · 三方交互模型 · UI 两阶段 |
| 规格层 / Spec | Coordinator + spec-author / spec-reviewer / spec-transformer / spec-transformer-reviewer | 飞书 9 节 Spec(人-AI 协作协议) | `docs/specs/REQ-*/` 四文件(design.md + tasks.md + ac-schedule.yaml + harness 骨架)+ `acm-registry.yaml` patch | 三元组(**约束集** / **反馈集** / **边界锚**)· `SPEC_TRANSFORMING` · 转化博弈 · `spec_source_revision` · 卡点 1a |
| Harness 层 / Harness | `spec-to-harness.yml` Actions | — | `harness/tests/REQ-*/` 完整测试代码 + 覆盖率矩阵 | ACM · P0 门 · 卡点 1b · 视觉回归 |
| 生成层 / Generation | `harness-confirmed.yml` + Claude Code CLI | — | Impl PR(通过 P0 Harness) | 自修复循环 · `CLAUDE.md` 行为规则 |
| 验证层 / Verification | CI + checkpoint-handler | — | 测试报告 + AI 失败摘要(PR 评论) | 卡点 2 · 全量 Harness |
| 集成层 / Integration | `staging.yml` Actions | — | Staging 环境 + Smoke Test 报告 | 卡点 3 · Smoke Test |
| 交付层 / Delivery | `deploy.yml` Actions | — | 客户环境部署 + 回滚窗口 | 参数化部署 · 自动健康检查 |

### 2.3 跨层核心概念词

跨多个层出现的概念词,每条指向最权威的章节锚点,避免读者在不同章节反复查同一个词。

| 词 | 最权威定义位置 |
|---|---|
| **REQ ID** | §4.3 |
| **ACM** / **acm-registry.yaml** | §5.2(本 REQ 的 ac-schedule 与根仓库 acm-registry 的角色分工)+ §5.3 |
| **Harness** | §5.3(生成)、§5.5(消费) |
| **项目级上下文五层** | §4.2 |
| **双闸门**(AI Ready + Human Confirmed) | §5.1 |
| **卡点 1a / 1b / 2 / 3** | §4.4 |
| **三元组**(约束集 / 反馈集 / 边界锚) | §5.2 |
| **转化博弈**(`SPEC_TRANSFORMING` 内部循环) | §5.2 |
| **`context_token`** + **revision round-trip** | §5.2 ARCHITECTURE 关系 + [infra/context-chain-principle.md §七](infra/context-chain-principle.md#七并发写回契约) |
| **`spec_source_revision`** | §5.2 转化博弈的设计哲学 |

### 2.4 命名区分(避免混用近义词)

这些词在业界通用语境下可能互换,但在本文有严格区分,必须对齐。

| 词 | 本文含义 | 常见误用 |
|---|---|---|
| **Spec** | 特指「飞书 9 节 Spec(原始)+ GitHub `docs/specs/REQ-*/` 四文件(派生)」的两阶段载体 | 泛指"规格文档" |
| **Specification** | ❌ 本文不用此词 | 误以为与 Spec 等同 |
| **Plan** | ❌ 本文不用此词作为文件名 | 误以为有 `plan.md` |
| **tasks.md** | 规格层派生产出之一,每行 `- [ ] T-NN: verb (acceptance: AC-K)` | 误以为是自由格式计划稿 |
| **ARCHITECTURE** | 项目级上下文,跨 REQ 演化的飞书文档;**被规格层消费并增量写回**,但**不是规格层的专属产出物** | 误以为是规格层交付物或前置基础设施 |
| **design.md** | 四文件 Spec 之一,承载 **约束集**(接口契约 + 数据模型 + 架构接合点 + supersedes 节) | 误以为是架构文档 |
| **acceptance.yaml** | ❌ 已更名为 `ac-schedule.yaml`(强调"本 REQ 的 AC 排班表") | 沿用旧名 |
| **requirements.md** | ❌ v2 不再单独产出(信息并入飞书 9 节 Spec) | 仍按 v1 假定存在 |

---

## 三、三维框架总览

整个工作流由三个维度构成：

```
┌─────────────────────────────────────────────────────────────────────┐
│                           横向基础设施                                │
│   人工协同轨（飞书 + OpenClaw）  ║   工程自动化轨（GitHub + CI）       │
├──────────╥──────────╥─────────╥──────╥──────╥────────╥─────────────┤
│  需求层   ║ 规格层  ║Harness 层║生成层║验证层║集成层 ║交付层         │
│Coordinator║  Spec   ║ Harness ║      ║      ║        ║             │
│ Service  ║          ║         ║      ║      ║        ║             │
├──────────╨──────────╨─────────╨──────╨──────╨────────╨─────────────┤
│                     层内子流程（AI 自主处理）                          │
└─────────────────────────────────────────────────────────────────────┘

REQ ID（REQ-{PROJECT}-{NNN}）穿透全链路：
  飞书文档 → Bitable → GitHub branch → PR → ACM → Harness → Impl PR

四个人工卡点：
  ⚡ 1a  方案门（Design 层确认，规格层）
  ⚡ 1b  Harness 门（测试覆盖确认，Harness 层）
  ⚡ 2   质量门（CI 全量通过，验证层）
  ⚡ 3   发布门（Staging 验收，集成层）
```

**纵向流程**：从需求到交付的七层流水线（规格层与 Harness 层并列为独立工程层），定义"做什么"。

**横向基础设施**：贯穿所有层的共用基础设施，分为人工协同轨（飞书 + OpenClaw）和工程自动化轨（GitHub + CI）。

**层内子流程**：每层内部的 AI 自主循环，人不感知，行为规则写入项目 CLAUDE.md。

---

## 四、核心架构原则

### 4.1 层间工作流服务三层分离

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
| 需求层 + 规格层 | Coordinator Service | 需求层首个参考实现（`Snowziio/requirement-workflow-feishu`）；规格层复用同一服务，延伸出 Spec 子状态机（见 §5.2）并负责卡点 1a 卡片 |
| Harness 层 → 交付层 | checkpoint-handler | 卡点 1b/2/3 卡片、CI 触发、PR 创建 |
| 生成→验证→集成→交付层 | *待建* | 按同一模板扩展 |

对应的能力层 Agent（当前已落地或规划中）：需求层为 OpenClaw author / reviewer；规格层为 spec-author / spec-reviewer（飞书 9 节阶段）+ spec-transformer / spec-transformer-reviewer（GitHub 四文件博弈转化阶段）；Harness 层起由 Claude Code CLI / GitHub Actions 接管。

**引入这条原则的教训**：v1.2 曾将 OpenClaw 作为主编排器，但 OpenClaw 的 session 按群绑定，无法跨群共享状态，也无法持久化跨进程状态。根因是把"能力层"错当"Workflow Service 层"来用。三层分离原则从架构上杜绝此类错误。

### 4.2 项目级上下文（防漂移基础设施）

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
飞书平面（人工协同轨 + 原始 Spec 草稿轨）   GitHub 平面（自动化 Coding 轨）
  需求文档集（需求历史层）                  ACM 注册表（功能契约层）
  UI 原型集（需求历史层）                   设计系统快照（视觉层镜像）
  项目设计系统文档（视觉层）                CLAUDE.md（规范惯例层）
  ARCHITECTURE 项目级文档（架构快照层）
```

- **Coordinator Service**：管理飞书侧所有项目级资产；在 Spec 生成时导出设计系统快照到 GitHub
- **spec-author Agent**：在每条 REQ 的 Spec 阶段演化 ARCHITECTURE 飞书文档（读当前 YAML → 增量合并 → 覆盖写回）
- **checkpoint-handler**：维护 GitHub 侧 ACM 注册表（Phase 3 引入）

**关键约束**：
- ARCHITECTURE 是**项目级上下文**，被 Spec 层消费并演化，不是 Spec 层的专属产出物也不是前置基础设施。主存储在飞书（和需求文档、UI 原型同平面），跨 REQ 持续演化；0→1 初始化通过需求建立时的「产品形态模板」解决（首条 REQ 的 Spec 撰写时即落下基线，后续 REQ 增量合并）。GitHub 侧不需要 ARCHITECTURE.yaml 镜像（Harness/Impl 层未来若要消费，再走快照导出机制）。
- UI 设计发生在代码仓库建立之前，设计系统的主存储必须在飞书；GitHub 快照在 Spec 生成时导出，供 AI Coding Agent 消费。

所有更新 **append-only** 或飞书原生 revision 版本化，可追溯到触发它的 REQ ID。

#### 分层上下文传递契约

项目级上下文在层间的传递有明确的契约规范：每层设计必须显式声明消费哪些上下文、如何消费、产出哪些上下文、如何传递给下层、以及如何防止语义漂移。详见补充原则文档：[infra/context-chain-principle.md](infra/context-chain-principle.md)。

#### 冷热内存注入模型

参考 Codified Context 论文（arXiv 2602.20478），AI Coding Agent 按访问频率分层获取上下文：

| 层级                    | 内容                                        | 注入时机             |
| --------------------- | ----------------------------------------- | ---------------- |
| **热**（每 session 自动加载） | CLAUDE.md；ARCHITECTURE 项目级飞书文档当前 revision；当前 REQ 的 Spec | 进入编码 session 即加载 |
| **温**（按 REQ 加载）       | 当前 REQ 的 ACM；技术范围有重叠的历史 ACM               | Spec 生成时注入       |
| **冷**（按需查询）           | 完整 ACM 注册表；完整设计系统历史；ADR 归档                | 显式触发时查询          |

### 4.3 REQ ID 全链路穿透

`REQ-{PROJECT}-{NNN}` 是贯穿全链路的唯一索引，任何工件都能通过 REQ ID 追溯到源头需求：

| 工件 | REQ ID 出现位置 |
|---|---|
| 飞书需求文档 | 文档标题前缀 |
| Bitable 追踪表 | 主键字段 |
| GitHub 分支 | `spec/REQ-{PROJECT}-{NNN}`、`impl/REQ-{PROJECT}-{NNN}` |
| Spec/ACM 文件 | 文件 metadata 字段 `req_id` |
| Harness PR、Impl PR | PR 标题 |
| 飞书卡点卡片 | 卡片标题 |

### 4.4 四卡点人工介入模型

人的判断集中在四个预定义的卡点。卡点之外，人不介入执行。

| 卡点 | 名称 | 层 | 事件名 | 判断内容 | 判断权 |
|---|---|---|---|---|---|
| ⚡ 1a | 方案门 | 规格层 | `checkpoint_1a_pass` / `checkpoint_1a_reject` | Design 层（接口契约 + 数据模型 + 架构接合点）是否合理；ACM 是否合理 | 技术负责人 |
| ⚡ 1b | Harness 门 | Harness 层 | `checkpoint_1b_pass` / `checkpoint_1b_reject` | 每个 AC 是否有对应测试；历史回归是否覆盖 | 技术负责人 |
| ⚡ 2 | 质量门 | 验证层 | `checkpoint_2_pass` / `checkpoint_2_reject` | CI 全量通过后，是否合并 PR | 技术负责人 |
| ⚡ 3 | 发布门 | 集成层 | `checkpoint_3_pass` / `checkpoint_3_reject` | Staging 功能 Demo 验收后，是否发布到客户环境 | 产品/客户负责人 |

**卡点的共同性质**：
- 飞书消息卡片发送，卡片上有操作按钮
- 按钮点击事件由 checkpoint-handler 接收，触发对应 GitHub 操作
- 每次判断记录到 Bitable，可追溯

---

## 五、纵向流程各层规格

> **细节文件与层的对应关系**
>
> 细节文件的粒度跟随层的**实现成熟度**而变化，不是机械一层一文件：
> - 已充分设计或实现的层 → 有独立细节文件，内容详实
> - 仍处于概念阶段的层 → 合并在共享文件中，内容以方法论描述为主
>
> 每层头部标注：`[实现状态]` + `细节文件`。
> 迭代规则：**当某层的设计开始产生可实现的细节时，对应细节文件同步更新**；若多层合并在一个文件中，当任一层成熟到需要独立详细规格时，从共享文件拆出。

### 5.1 需求层

> **实现状态**：✅ 已上线（Phase 1 完成）｜**细节文件**：[layers/requirement-layer.md](layers/requirement-layer.md)

**驱动者**：Coordinator Service（Workflow Service 层）+ OpenClaw Author/Reviewer Agent（能力层）

**目标**：将模糊的客户需求转化为经双闸门确认的结构化需求文档，进入规格层。

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

### 5.2 规格层

> **实现状态**：⚙️ 设计完成，待实现（Phase 2）｜**细节文件**：[layers/spec-harness-layer.md](layers/spec-harness-layer.md)

**驱动者**：Coordinator Service（Workflow Service 层）+ OpenClaw spec-author / spec-reviewer / spec-transformer / spec-transformer-reviewer（能力层）。

**使命**：把「模糊的客户需求」转化为「让生成层能够自驱 coding 的**机器可解析三元组**」。飞书 9 节 Spec 不是本层交付物，而是「人-AI 协作协议」；一旦卡点 1a 通过，后续各层只消费 GitHub 四文件。

**三元组交付**（本层的唯一实质产出）：

- **约束集（what / where）**——接口契约 + 数据模型 + 架构接合点，承载于 `design.md`；规定生成层必须遵守的输入输出形状与模块边界。
- **反馈集（oracle）**——`ac-schedule.yaml` 的声明式 `expected` + harness 骨架的可执行判定；两者组合让生成层无人工介入也能自我校验。
- **边界锚（must-not-drift）**——`design.md` 的 `supersedes` 节 + `acm-registry.yaml` patch + ARCHITECTURE 当前 revision；防止生成层越界触碰其他 REQ 的既有契约或项目架构。

| | 内容 |
|---|---|
| **输入** | APPROVED 需求文档 + `needs_ui = true` 时的高保真 UI 原型 + 项目级上下文（ARCHITECTURE 当前 revision + ACM 注册表 + 设计系统快照） |
| **输出** | **原始产出**：飞书 9 节 Spec（卡点 1a 锁定的协作草稿）<br>**派生产出**：GitHub 四文件（`design.md` + `tasks.md` + `ac-schedule.yaml` + harness 骨架）+ `acm-registry.yaml` patch，统一落在 `docs/specs/REQ-{PROJECT}-{NNN}/` 的 Spec PR |
| **完成标准** | 卡点 1a 通过 → 博弈收敛（或死锁后人工兜底）→ Spec PR 合入 → `SPEC_LOCKED` |

**两阶段 Spec 模型**（避免两轨混淆）：

| 阶段 | 载体 | 目的 | 可变性 |
|---|---|---|---|
| **原始（阶段一）** | 飞书 9 节 Spec | 人-AI 协作协议；卡点 1a 的人类审阅界面 | 卡点 1a 前可改；通过后冻结 |
| **派生（阶段二）** | GitHub `docs/specs/REQ-*/` 四文件 | 喂给 `spec-to-harness.yml` 等自动化管道；ACM/CI 唯一数据源 | 博弈转化产出；Spec PR 合入后锁定 |

阶段一让"讨论与决策"发生在人最熟悉的协作空间；阶段二让自动化链路有确定性文件结构。**卡点 1a 是两阶段之间的唯一人工决策点**——通过即授权 AI 博弈转化，转化过程不引入新的人工节点（除非死锁）。

**Spec 子状态机**：需求层 6 态机的下挂子状态，仅在 `requirement.status == APPROVED` 时生效；与需求层正交，Spec 驳回或中止**不会**回写 `requirement.status`。

```
                 spec_start
      null ─────────────────────► SPEC_DRAFTING
       ▲                            │   ▲
       │                            │   │  ai_review_reject
       │                            │   └──────────────  (留在 SPEC_DRAFTING)
       │                  ai_review_pass
       │                            ▼
       │                    （等待卡点 1a）
       │         checkpoint_1a_pass │     (捕获 spec_source_revision)
       │                            ▼
       │                    SPEC_TRANSFORMING ◄───┐ transform_deadlock
       │                            │             │ (自循环，写人工工单，
       │                            │             │  不回退 SPEC_DRAFTING)
       │                            ├─────────────┘
       │                 transform_converged
       │                            ▼
       │                      SPEC_LOCKED ──► 进入 Harness 层
       │
       │         checkpoint_1a_reject / spec_abort
       └──────────────────── SPEC_REJECTED
                                 （仅作历史留档，不回退需求层状态；
                                  需人工决定是否重启 spec_start）
```

事件命名：`spec_start` / `spec_submit` / `ai_review_pass` / `ai_review_reject` / `checkpoint_1a_pass` / `checkpoint_1a_reject` / `transform_converged` / `transform_deadlock` / `spec_abort`。

**六阶段工作流 TL;DR**：Phase 1 授权与上下文组装 → Phase 2 飞书 9 节撰写-审查循环（`SPEC_DRAFTING`）→ **⚡ 卡点 1a**（唯一人工决策）→ Phase 3 转化博弈（`SPEC_TRANSFORMING`）→ Phase 4 回归扫描（机械闸门，防旧 AC 遗弃）→ Phase 5 Spec PR 发布（Coordinator GitHub I/O）→ Phase 6 飞书冻结、`SPEC_LOCKED`。详见 [layers/spec-harness-layer.md §五](layers/spec-harness-layer.md)。

**闸门哲学**（人工介入点唯一，其余全机械）：Inferential signals（能力层 Agent 判断）只用于飞书阶段的 spec-reviewer 与博弈阶段的 spec-transformer-reviewer；Computational signals（机械判定）前置所有 schema / 正则 / 路径一致性 / 回归扫描；Human signal 只保留一个——卡点 1a。

**四道工程闸门**（每道闸门的实现细节见 [layers/spec-harness-layer.md §六](layers/spec-harness-layer.md)）：

| 闸门 | 位置 | 性质 | 作用 |
|---|---|---|---|
| **Round 0 AC 认领** | 博弈起点 | 机械 | spec-transformer 必须先回显全部 AC-K，再开始产出，堵住"漏 AC" |
| **Computational gate** | 每轮 transformer → reviewer 之间 | 机械 | 预检 schema / tasks 正则 / supersedes / 路径一致性，节约 Inferential 预算 |
| **transform_trace** | 博弈全程 | 可观测性 | 每轮事件写入审计轨迹，支撑 deadlock 诊断与回溯 |
| **Regression scan** | `SPEC_LOCKED` 前 | 机械 | 扫描 `acm-registry` 有效 AC 是否全部被新骨架绑定，防止旧 AC 遗弃 |

**转化博弈的设计哲学**（参数与 agent 契约见细节文件）：

- **收敛有硬上限**——多轮博弈有固定 `max_rounds`，超出即 deadlock；避免 agent 陷入无限重写。
- **死锁不回退**——deadlock 状态留在 `SPEC_TRANSFORMING` 自循环 + 写人工工单，**不回退 `SPEC_DRAFTING`**：卡点 1a 已有人工决策，回退会让用户的结论失效。
- **凭据隔离**——所有 GitHub I/O 由 Coordinator 的 `GitHubGateway` 独占，agent 只产文本；能力层替换零风险，凭据审计面收敛到单一进程。
- **单向审计**——`spec_source_revision` + Spec PR number + `transform_round` 合成单向链路（飞书 → GitHub），不做双向握手（飞书 Spec PR 合入后已冻结，无并发写回风险）。

**ARCHITECTURE 与本层的关系**：ARCHITECTURE 是**项目级上下文**（见 §4.2），被规格层"消费并演化"，不是本层专属产出物。并发写回的 `context_token` + revision round-trip 协议见 [infra/context-chain-principle.md §七](infra/context-chain-principle.md#七并发写回契约)。ACM / 设计系统快照在本层是**只读输入**。

实现细节（四文件字段 schema、Agent prompt 契约、博弈参数、卡片模板、harness 目录结构、治理事件）见 [layers/spec-harness-layer.md](layers/spec-harness-layer.md)。

---

### 5.3 Harness 层

> **实现状态**：⚙️ 设计完成，待实现（Phase 3）｜**细节文件**：[layers/spec-harness-layer.md §十](layers/spec-harness-layer.md)

**驱动者**：`spec-to-harness.yml` GitHub Actions workflow + Claude Code CLI（能力层）

**使命**：把规格层产出的 harness 骨架填充为完整可执行测试代码，覆盖每条 AC；提供 Impl PR 的合并硬门槛。

| | 内容 |
|---|---|
| **输入** | 锁定的四文件 Spec（`ac-schedule.yaml` + `design.md` + `tasks.md` + harness 骨架，只读）+ 项目历史 Harness 代码（去重参考） |
| **输出** | `harness/tests/REQ-{PROJECT}-{NNN}/` 下按 AC 组织的完整测试代码 + 覆盖率矩阵文档 |
| **完成标准** | 卡点 1b（Harness 门）通过：每个 AC 有对应测试文件，P0 全绿，历史回归覆盖 |

**核心机制**：

**ACM 是唯一权威输入**：每条 AC 的 `given / input / expected` 字段直接对应测试的 fixture 与 assertion；AI 不再推断判定标准。

**P0 是 Impl PR 硬门槛**：`priority=P0` 的 AC 对应测试必须全部通过，PR 才能合并；P1/P2 允许后续补齐。

**视觉回归测试（`needs_ui = true` 时）**：与功能性 Harness 并行生成，基于 Playwright 对 `design-ui.md` 定义的关键视图做截图比对；超过阈值阻断 PR——UI 层的 Harness 等价机制，防止 Coding Agent 悄悄改动组件样式。

**历史只读**：已通过卡点 1b 的 Harness 目录在后续 PR 中不可修改，只能在新版本目录追加；保证回归基线单调累积。

---

### 5.4 生成层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（5.4–5.7 合并，待层成熟时拆分）

**驱动者**：`harness-confirmed.yml` GitHub Actions workflow 触发 Claude Code CLI

**目标**：AI 基于锁定的四文件 Spec + Harness 自主生成实现代码，直到所有 P0 Harness 通过。

| | 内容 |
|---|---|
| **输入** | 锁定的 Harness（只读）+ 四文件 Spec（design + tasks + ac-schedule + harness 骨架）+ CLAUDE.md（行为规则）+ 项目级上下文（热加载） |
| **输出** | 通过所有 P0 Harness 测试的实现 PR |
| **完成标准** | CI 全量 Harness 通过（P0 全绿），进入验证层 |

**关键约束**：
- AI **禁止修改** `harness/tests/` 目录（由 CLAUDE.md 和 CI 双重强制）
- AI **禁止修改** `docs/specs/` 目录
- 自修复循环有最大次数上限（默认 3 轮），超限则暂停等待人工介入
- CLAUDE.md 规定当前任务阶段（task: implement），AI 只做实现工作

---

### 5.5 验证层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（5.4–5.7 合并，待层成熟时拆分）

**驱动者**：GitHub Actions CI（自动）+ checkpoint-handler（卡点2）

**目标**：对实现 PR 全量运行 Harness，给出明确的通过/失败信号，触发卡点2。

| | 内容 |
|---|---|
| **输入** | 实现 PR（含完整代码变更） |
| **输出** | 测试报告（全量覆盖率、通过率、构建状态）+ 失败时的 AI 分析摘要（写入 PR 评论） |
| **完成标准** | 卡点2（质量门）通过：技术负责人审查报告后点击合并 |

**AI 参与点**：CI 失败时，AI 分析脚本自动调用 Claude API 解析失败日志，生成结构化失败摘要写入 PR 评论，减少人工排查时间。

---

### 5.6 集成层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（5.4–5.7 合并，待层成熟时拆分）

**驱动者**：`staging.yml` GitHub Actions workflow（合并后自动触发）

**目标**：合并后自动部署到 Staging 环境，运行 Smoke Test，触发卡点3。

| | 内容 |
|---|---|
| **输入** | 合并到 staging 分支的代码 |
| **输出** | 可访问的 Staging 环境 + Smoke Test 报告 |
| **完成标准** | 卡点3（发布门）通过：产品/客户负责人在 Staging 验收功能 Demo 后确认发布 |

**Smoke Test 定义原则**：仅验证核心路径可用性（服务健康 + 主要业务路径能跑通），不追求完整覆盖。完整覆盖由 Harness 承担。

---

### 5.7 交付层

> **实现状态**：📋 概念阶段（Phase 3）｜**细节文件**：[layers/generation-delivery-layers.md](layers/generation-delivery-layers.md)（5.4–5.7 合并，待层成熟时拆分）

**驱动者**：`deploy.yml` GitHub Actions workflow（卡点3 后触发）

**目标**：参数化部署到客户环境，自动健康检查，失败自动回滚。

| | 内容 |
|---|---|
| **输入** | 卡点3 通过信号 + 客户配置文件（`.env` 隔离） |
| **输出** | 运行中的客户生产环境 |
| **完成标准** | 健康检查通过，服务在客户环境响应正常 |

**客户隔离原则**：每个客户一份独立的配置文件，部署脚本参数化，不存在跨客户的配置污染。

---

## 六、横向基础设施

### 6.1 人工协同轨（飞书 + OpenClaw）

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

### 6.2 工程自动化轨（GitHub + CI）

覆盖 Spec 锁定后的全部自动化执行。

**核心服务**：
- **checkpoint-handler**：Harness 层到交付层的 Workflow Service，处理卡点1b/2/3 的卡片回调，维护 ACM 注册表和 ARCHITECTURE.yaml
- **GitHub Actions**：CI 执行、Harness 生成触发、Staging 部署、客户部署

**工程自动化轨的核心约束**：
- `harness/tests/` 历史版本目录只读
- `docs/specs/` 目录只在 `spec/REQ-*` 分支修改，合并后锁定
- CLAUDE.md 是 AI Coding Agent 唯一的行为规则来源
- 所有状态变更通过 checkpoint-handler 记录到 Bitable

### 6.3 两轨协作接口

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

## 七、实施路线图

### Phase 0：工程自动化轨地基（已完成 ✅）

目标：GitHub 侧基础设施就位，CI → 飞书通知 → 卡点确认 → 部署的端到端链路跑通。

已完成：项目模板仓库（harness-scaffold）、CLAUDE.md 模板、Self-hosted Runner、飞书通知脚本、checkpoint-handler、AI 失败分析脚本、客户部署脚本、飞书 WebSocket 卡片回调验证。

### Phase 1：需求层上线（已完成 ✅）

目标：Coordinator Service 稳定运行，OpenClaw Author/Reviewer Agent 接入，需求全流程（创建 → 讨论 → 审查 → APPROVED）跑通。

已完成：Coordinator Service 部署（`admin@47.251.81.45:8004`）、Author/Reviewer Agent 接入、Bitable 状态流转、正式文档 section-rewrite。

### Pre-Phase-2：需求层稳固与 ARCHITECTURE 作为 Spec 产出物（已完成 ✅）

目标：在启动需求层→规格层桥接之前，补齐需求层存在的信息漂移风险和项目级上下文缺口，澄清 ARCHITECTURE 的归属定位，避免错误假设带入 Phase 2。

**关键结论（相对 v2.0 初稿的修正）**：
- **ARCHITECTURE 定位反转**：原计划将 ARCHITECTURE.yaml 作为 Spec 层的**前置输入**（通过 bootstrap 脚本/Coordinator bootstrap 在项目接入时预置到 GitHub）。实践中发现两个前置假设都站不住：当前项目产出边界只到 Spec 不触及 Impl，GitHub 仓库可能不存在；bootstrap 阶段尚无任何需求沉淀，空骨架对 Spec 决策无价值。因此重新定位：**ARCHITECTURE 是 Spec 层的核心产出物之一，随每条 REQ 的 Spec 迭代演化**，主存储落在飞书项目级文档。GitHub 绑定 / Bootstrapper / Onboarding 流程全部拆除。
- **Spec 层独立上下文端点**：需求层 `fetch-context` 不含 `architecture_doc_url`/revision；新增 `/queries/openclaw/spec-context` 端点（CLI 子命令 `spec-context`），返回 `architecture_doc_url` + `architecture_doc_revision` + `context_token`，状态门控 `APPROVED | SPEC_DRAFTING`。
- **context_token + revision round-trip**：Spec 层写回 ARCHITECTURE 飞书文档存在并发竞争，必须走「进入时 revision → 写回 → 再次读取获得写后 revision → 回传」握手，Coordinator 据此决定是否接受 spec-submit。见 [infra/context-chain-principle.md §七](infra/context-chain-principle.md#七并发写回契约)。
- **Callback 即状态机唯一真相**：写完飞书文档 ≠ 流程推进，状态机只认 `send_openclaw_callback.py` 的 HTTP 2xx。所有 Agent SKILL.md 强制要求「本次会话最终动作必须是 callback」，未成功上报即视为未完成,不允许伪装成已完成。

已完成关键产出：
- Spec 层两份核心产出物（Spec 文档 + ARCHITECTURE 飞书文档）端到端跑通，含 context_token/revision 并发保护
- 四个 OpenClaw Agent SKILL.md 统一加入「状态机驱动硬约束」措辞
- 需求层 section-level 幂等重写稳定；Bitable schema v1.2 就绪

**Pre-Phase-2 已知遗留**（收口时登记到 session memory，不阻塞 Phase 2 启动）：
- `needs_ui` 两阶段 UI 流程尚未实现（APPROVED 时仅占位创建空设计系统文档）
- `architecture_doc_url` 持久化依赖 state.json 容器卷，重启丢失风险待治理
- `scripts/sync_bitable_schema_v12.py` 存在 field_type 类型 bug（生产表已手工对齐）
- OpenClaw 服务端 agent 配置除 SKILL.md / callback CLI 外未纳入仓库版本化

### Phase 2：需求层→规格层桥接（待启动，依赖 Pre-Phase-2 完成）

目标：打通 APPROVED 需求文档 → 飞书 9 节 Spec → 卡点 1a → spec-transformer 博弈 → GitHub 四文件 Spec PR 的完整链路，参见 [epics/spec-transform-epic-2026-04.md](epics/spec-transform-epic-2026-04.md)。

关键任务：需求文档格式升级（半结构化输入/输出 + 技术范围声明）、UI 设计第二阶段实现、Spec 转化 Agent、ACM 兼容性检查、设计系统文档管理、卡点1a 飞书卡片。

### Phase 3：Harness 层 → 生成层自动化（待建）

目标：卡点1a 确认后，Harness 生成 → 卡点1b → AI 实现 → CI 全量自动化。

关键任务：`spec-to-harness.yml` workflow、`harness-confirmed.yml` workflow、视觉回归测试生成、AI 自修复闭环。

### Phase 4：首个真实项目端到端（待建）

目标：用真实业务需求走完完整链路，验证框架可用性，记录需要补丁的地方。

### Phase 5：飞轮运转（持续）

目标：ACM 注册表积累，ARCHITECTURE.yaml 持续更新，AI 干预点逐渐减少，验证飞轮效应。

---

## 附录：关键术语表（A-Z 索引）

本表是查询用完整索引。"先看这里"的概念地图见 §2。

### 业界对齐术语

| 术语 | 含义 |
|---|---|
| **Agent = Model + Harness** | 业内 2025–2026 共识公式：Agent 能力 = 模型 × 工程脚手架完备度 |
| **Computational signal** | Martin Fowler 术语：可机械判定的反馈信号（pytest / jsonschema / 类型检查） |
| **Externalized memory** | 把决策/约束外部化为 markdown/yaml 文件，而非放在 LLM token 里 |
| **Generator-Evaluator loop** | Anthropic "Building Effective Agents" 收敛模式：生成-评审-驳回-再生成，max_rounds 约束 |
| **Guides（前馈）** | Fowler 术语：生成之前注入的约束（对应本文**约束集**） |
| **Harness engineering** | 业内 2025–2026 术语：围绕 LLM 构建自驱 coding Agent 所需的全部结构化支撑层 |
| **Inferential signal** | Fowler 术语：需判断的反馈信号（LLM judge / 人工 review） |
| **Rigid tests block completion** | OpenAI Codex 硬约束：测试不通过即不算完成（对应本文 P0 门 + regression scan） |
| **Sensors（反馈）** | Fowler 术语：生成之后或过程中检测偏离的机制（对应本文**反馈集**） |
| **Spec-Driven Development (SDD)** | 学术社区规格先行范式；六要素：outcomes / scope / constraints / prior decisions / tasks / verification |

### 本文专有术语

| 术语 | 含义 |
|---|---|
| **acm-registry.yaml** | 根仓库级全局 AC 注册表，承接 supersedes 链；每次 SPEC_LOCKED 由 Coordinator 自动 patch |
| **ac-schedule.yaml** | 本 REQ 的 AC 排班表；四文件 Spec 之一；反馈集的声明部分 |
| **ACM** | Acceptance Criteria Matrix，验收标准矩阵 |
| **ARCHITECTURE** | 项目级上下文，跨 REQ 演化的飞书文档；被规格层消费并写回，不是规格层专属产出物 |
| **checkpoint-handler** | Harness 层到交付层的 Workflow Service，处理卡点回调 |
| **context_token + revision round-trip** | ARCHITECTURE 并发写回的握手协议：入口 revision → 写回 → 读取写后 revision → 回传 |
| **Coordinator Service** | 需求层 + 规格层的 Workflow Service，持有需求状态机 + Spec 子状态机 + GitHubGateway |
| **design.md** | 四文件 Spec 之一；承载**约束集**（接口契约 + 数据模型 + 架构接合点 + supersedes 节） |
| **Harness** | 基于 ACM 生成的可执行测试代码集合；Impl PR 合并前提 |
| **harness 骨架** | 四文件 Spec 之一；每条 AC 的 pytest 占位文件，`@pytest.mark.ac("AC-K")` 锚定 |
| **卡点 1a / 1b / 2 / 3** | 方案门 / Harness 门 / 质量门 / 发布门，四个人工判断点 |
| **P0 测试** | priority=P0 的 Harness 测试；Impl PR 合并的硬性门槛 |
| **三层分离** | Workflow Service / Hook 实现 / 能力提供，三层职责分离原则 |
| **三元组** | 规格层的真正交付：**约束集** + **反馈集** + **边界锚** |
| **设计系统文档** | Coordinator 管理的飞书文档，记录项目 UI 组件库 / Token / 交互模式 / 历次设计决策 |
| **设计系统快照** | 设计系统文档在 Spec 生成时导出到 GitHub 的版本，供 AI Coding Agent 消费 |
| **双闸门** | 需求层 AI Ready + Human Confirmed 两道独立准入条件 |
| **spec_source_revision** | 飞书 Spec 在卡点 1a 通过时的 revision，写入 Spec PR body + Bitable 作为审计锚点 |
| **SPEC_TRANSFORMING** | 规格层子状态机的中间态；spec-transformer / spec-transformer-reviewer 博弈产出四文件 |
| **supersedes** | design.md 的必需小节；显式声明被本 REQ 取代的旧 AC，或 `"no supersession"` |
| **tasks.md** | 四文件 Spec 之一；每行 `- [ ] T-NN: verb (acceptance: AC-K)` |
| **项目级上下文** | 跨 session 持久存在的五层结构化知识：ARCHITECTURE / ACM / 视觉 / 规范惯例 / 需求历史 |
| **REQ ID** | 需求唯一标识符，格式 `REQ-{PROJECT}-{NNN}`，穿透全链路 |
| **转化博弈** | `SPEC_TRANSFORMING` 内部循环：spec-transformer 产出四文件 → reviewer 5 维度审 → converged 或 max_rounds=3 死锁 |

---

*v2.0 | 2026-04-14 | 方法论文档重构：总-分结构，实现细节移入 layers/ 和 infra/ 细分文件*
*v2.0 · §5.2 更新 | 2026-04-16 | 规格层引入 `SPEC_TRANSFORMING` 中间态 + spec-transformer 博弈 + 四文件 Spec（`docs/specs/REQ-*/`）；ARCHITECTURE 定位回归「项目级上下文」。参见 epics/spec-transform-epic-2026-04.md。*
*v2.0 · §2 新增 | 2026-04-16 | 术语与产出物地图章节前置；原 §2–§6 顺延为 §3–§7。*
*v2.0 · 规格层命名与 §5.2/§5.3 精简 | 2026-04-16 | 规格层 A/B 子层命名收敛为「规格层 + Harness 层」；§5.2/§5.3 压缩为概念/流程/哲学层面（六阶段 TL;DR + 四道工程闸门 + 博弈哲学），四文件字段 schema、博弈参数、卡片模板等实现细节统一指向 layers/spec-harness-layer.md。*
