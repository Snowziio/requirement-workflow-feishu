# Harness Engineering 全自动开发工作流：方法论 v3.0
> v3.0 | 2026-04-21 | 完整重构：双主语言 + 终态倒推 + 两段式层结构

---

## 序 | 文档定位与阅读路径

### 序章

方法论 v2.6 经过多轮增量修订，在 2026-04-21 已显现体系性矛盾：切面描述不正交、北极星叙事断裂、层数与卡点数前后不一、历史遗留协议与新模型并存。v3.0 是对方法论的**彻底重写**，以"AI 自驱实施闭环"（定义见 §二）为唯一终态北极星，以倒推逻辑重新推导上游每层的职责，以 2×3 矩阵（项目级/需求级上下文 × Guides/Sensors/Invariants 三元组）作为贯穿全文的主语言骨架。

**v2.6 将归档至 `docs/archive/harness-engineering-methodology-v2.6.md`**（由后续归档任务完成），其内容不再维护；本文为唯一权威。凡与 v2.6 有冲突之处，以本文为准。

**推荐阅读路径**：初次阅读建议先读 §二（终态倒推），理解整个方法论的"为什么"；再读 §三（上下文条目类型表），掌握全方法论的共用字典；其余章节（§四–§九及附录）可按需跳读。已熟悉 v2.6 的读者可参考附录 B 查阅语义变更结论。

### 序·写作规范

本文以下五条规范对全文所有章节强制生效：

1. **口径统一**：同一概念在本文只使用唯一 canonical 名称；替代说法（alias）退出正文，仅在附录 A 标注。
2. **业界术语优先**：业界已有成熟表达的概念，使用业界术语；见 §1.4 对齐概述及附录 A。
3. **首次必有定义**：任何关键术语在首次出现处必须给出定义（inline 定义，或标注"见附录 A 条目"）。
4. **不造新词原则**：本方法论特有设计（如"构造期/实施期 SOT 时相分段"、"项目级/需求级上下文二分"）保留自造术语并在附录 A 显式标注"本方法论独创"；已有业界概念禁止另造新词，v2.6 自造词一律替换为业界术语。
5. **引用规范**：引用业界文献（Fowler / Anthropic / OpenAI / Codified Context 等）时标注来源；引用本文其他章节时使用 §N.M 锚点；链接只指向本文中实际存在的章节。

---

## §一 核心目标与设计哲学

### §1.1 适用范围声明

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
| **代码库规模** | 单 repo，ARCHITECTURE 架构条目在数十个以内 |

**在范围内的典型产品形态**：嵌入飞书/企业微信的内部工具、企业工作流自动化系统、带 AI 对话/生成能力的后台管理系统、轻量 SaaS（组织内部订阅）、工程效率工具（含本方法论自身的实现）。

**超出范围（暂不覆盖）**：大规模 C 端消费应用、iOS/Android 原生 App、K8s 分布式集群服务、金融/医疗强合规系统、通用开源框架/基础库、实时系统（硬性延迟要求 < 10ms）。

> 超出范围不意味着方法论完全不适用，而是指需要在适用范围内的规格基础上增加额外层次的设计，不能直接套用。

---

### §1.2 核心目标

**用一套标准化工作流，让 AI 成为主要开发执行者，人只在关键决策点介入。**

具体目标：
- 从客户需求到生产部署，全链路可重复、可追溯、可持续迭代
- AI 每次介入都有精确的约束输入（规格、测试、历史上下文），不靠猜
- 人的判断集中在若干 Checkpoint，其余全部自动化
- 随着需求积累，AI 干预点逐渐减少（飞轮效应）

方法论 v3.0 明确以 **AI 自驱实施闭环** 为终态北极星，上游层的一切产出职责由此倒推得出，详见 §二。

---

### §1.3 五条设计哲学

**1. 规则化优先于个性化**

工作方法（需求讨论流程、Spec 生成流程、CI 配置、部署方式）对任何项目都是一样的。不因项目特性重新设计流程，而是共用同一套规则化工作流服务。

**2. 约定优于协商**

AI 的行为规则写入 CLAUDE.md 和 ACM，不靠每次对话约定。规格和测试代码是 AI 的"合同"，合同不清晰时不是靠重新沟通来解决，而是补充规格。

**3. 结构化产物驱动自动化**

自然语言（需求文档）→ 半结构化（EARS 用户故事）→ 结构化（ACM YAML）→ 可执行（Harness 测试代码）。每一步转化都有明确的格式约定，任何步骤均可被下游机器消费。

**4. Drift Prevention（防漂移）是基础设施问题，不是纪律问题**

架构漂移（architectural drift）、视觉漂移（visual drift）、功能漂移（functional drift）根源在于每次迭代时 AI 缺乏持续积累的历史上下文，而不是因为 AI 不认真。解决方案是项目级上下文基础设施，让历史决策以结构化形式持续注入。

**5. 人工介入集中在判断，不在执行**

人不写代码、不写测试、不配置环境。人只在若干 Checkpoint 做判断：方案对不对（Checkpoint 1a）、覆盖全不全（Checkpoint 1b）、质量达没达（Checkpoint 2）、效果符不符（Checkpoint 3）。

---

### §1.4 业界对齐概述

本方法论不是自创框架，而是业界 `harness engineering` 工程实践在"需求→架构演化"场景下的一次具体落地。下表把业界主流词汇映射到本文 canonical 术语，读者可据此把本文放回更大的业界语境。

| 业界术语 | 一句话释义 | 本文对应 |
|---|---|---|
| **Harness engineering** | 2025–2026 业内共识：围绕 LLM 构建可自驱 coding Agent 所需的全部结构化支撑层 | 本方法论的总名 |
| **Agent = Model + Harness** | Agent 能力 = 模型能力 × 工程脚手架完备度 | 本方法论整体假设；由 §二 终态倒推展开 |
| **Guides / Sensors**（Martin Fowler 控制论） | Fowler 控制论视角：Guides 给生成前约束，Sensors 给生成后偏离信号 | **Guides（约束集）** / **Sensors（偏离检测集）**，三元组之二；见 §三 |
| **Invariants（不变量）** | 跨生成步骤保持不变的边界条件（CS/工程通用术语） | **Invariants（不变量）**，三元组之三；见 §三 |
| **Generator-Evaluator Loop** | Anthropic "Building Effective Agents" 模式：生成-评审-驳回-再生成 | **Spec Transformation Loop（规格翻译闭环）**：spec-transformer + spec-transformer-reviewer；见 §六 |
| **Spec-Driven Development (SDD)** | 学术/工程社区的规格先行范式，六要素：outcomes / scope / constraints / prior decisions / tasks / verification | 本文四文件 Spec 覆盖全部六要素 |
| **Rigid tests block completion** | OpenAI Codex 硬约束：测试不通过即不算完成 | P0 Harness 门 + regression scan；见 §七 |
| **Externalized memory** | 外部化记忆（markdown / yaml，而非 token 中的 context） | Project-level Context 五类条目 + `acm-registry.yaml`；见 §三 |
| **Computational / Inferential** | 可机械判定（pytest / schema）vs 需判断（LLM judge / 人工 review） | Checkpoint 与 AI 审查的二分；Computational 优先、Inferential 兜底 |

| **Parallel Sub-State Tracks** | 并行子状态机轨道（业界并行子状态机术语） | 规划层 DesignStatus / PlanStatus / SpecStatus 三轨并行；见 §六 |
| **Cascading Reset** | 上游状态重置触发下游连锁清除（业界通用） | `/plan restart` 清 Spec；`/design restart` 清 Plan+Spec；见 §六 |
| **Drift Prevention** | 防止架构 / 视觉 / 功能漂移（业界 architectural drift 通用） | §1.3 第四条设计哲学；项目级上下文基础设施是实现手段 |

> 深度对齐分析：[infra/harness-engineering-industry-alignment-2026-04-16.md](infra/harness-engineering-industry-alignment-2026-04-16.md)
>
> 本文中出现的 Fowler 术语（Guides / Sensors）以其控制论原意使用，来源：Martin Fowler，"Control System Patterns"。其余 canonical 术语映射见附录 A。

---

## §二 终态倒推（End-State Backward Derivation）

本章回答一个根本性问题：v3.0 的层结构、条目类型表、2×3 矩阵是**为什么**被设计成这个样子？上游每一层的职责边界、每一类上下文条目的存在理由，都不是凭直觉添加的，而是从唯一终态北极星——**AI 自驱实施闭环**——逐步倒推得出的。本章是 v3.0 所有后续章节（§三-§九及附录）的理论推导源；读懂本章，即读懂整个方法论的"为什么"。

---

### §2.1 终态定义：AI 自驱实施闭环的准入条件

**AI 自驱实施闭环**（本方法论独创，定义见附录 A）是指：从 `SPEC_LOCKED`（**Spec Transformation Loop** 收敛时触发的状态，标志构造期向实施期切换）进入之后，AI Coding Agent 在无需额外人工介入的情况下，独立完成从代码生成到部署就绪的完整实施路径。

这一终态的准入，有且仅有三个必要条件：

1. **完整机器可解析的输入**：交给 AI 的上下文必须足够完整、明确且机器可消费——不是自然语言描述，而是结构化规格产物（**Spec Artifacts**（本方法论独创，定义见附录 A）：`ac-schedule.yaml` / `design.md` / `tasks.md`，可追加 `harness/` 骨架）。
2. **自修复实施循环**：AI 能够独立完成"实现（implement）→ 对齐（align）→ 纠正（correct）"的循环——每轮偏离后可凭结构化反馈自主修正，无需人工介入解释方向。
3. **CI oracle 推进**：产出物由 CI 作为外部事实裁判（oracle）验证，测试通过即可自动推进到下一阶段——"不通过即不算完成"是硬性约束（对应业界 OpenAI Codex 原则"Rigid tests block completion"）。

三个条件缺一不可：缺少结构化输入，AI 无根据猜测；缺少自修复循环，AI 每轮失败都需要人工诊断；缺少 CI oracle，完成判定无法自动化，整个闭环的"环"就不成立。

---

### §2.2 从终态倒推：为何需要三元组

三个准入条件倒推出一个立即推论：AI 的"完整机器可解析输入"必须同时具备三个维度，缺少任何一个维度都无法满足准入。这三个维度即为 v3.0 全文的主语言骨架——**Guides / Sensors / Invariants 三元组**。

**Guides（约束集，前馈约束，Fowler 术语）**——生成之前注入的设计契约。包括接口定义、数据模型约定、架构接合点声明。Guides 的作用是在生成动作发生之前就将解空间压缩到正确的子空间内，使 AI 无需从零出发猜测设计意图。**缺少 Guides 的后果**：AI 在接口兼容性、数据模型选型、架构耦合方式上完全无根据，每次生成都是一次有风险的猜测，输出结果与系统整体契约大概率不吻合。

**Sensors（偏离检测集，后馈反馈，Fowler 术语）**——生成之后或过程中检测偏离的机制。包括 AC oracle（`ac-schedule.yaml` 驱动的验收条件判定）、Harness 测试代码（P0 门）、视觉回归（Phase 2 UI 路径）。Sensors 是 CI oracle 的具体承载形式，是"自修复实施循环"中"align → correct"两步得以自动化的前提。**缺少 Sensors 的后果**：AI 无法自判成败——它可以生成代码，但无法知道生成结果是否正确，整个自修复循环退化为单次生成，必须由人在每轮结束时手工判定是否通过。

**Invariants（不变量）**——跨生成步骤保持不变的边界条件，包括历史 AC 的 `supersedes` 关系（本方法论独创，定义见附录 A）、项目级硬约束（**Known Constraint / KC**，本方法论独创，定义见附录 A）、架构复用规定。Invariants 的作用是防止 AI 在自修复循环过程中，以修正当前测试失败为由越界触碰既有契约——例如删改历史通过的 AC 来规避测试，或引入与架构约束冲突的新依赖。**缺少 Invariants 的后果**：AI 有动机（且有能力）通过改动历史契约来消除红色 CI，而这种"作弊性修复"在没有不变量约束的情况下无法被机械检测出来。

三元组共同构成"完整机器可解析输入"的内部结构：Guides 确定方向，Sensors 判定成败，Invariants 守护边界。详见 §三 的完整条目类型表。

---

### §2.3 从三元组倒推：为何需要构造期

三元组不会凭空出现。`design.md` 里的接口契约、`ac-schedule.yaml` 里的验收条件、`acm-registry.yaml` 里的历史 AC 状态——这些结构化产物都需要在某个时间窗口内被人-AI 协同生产出来，然后以只读形式交给实施期消费。这个时间窗口就是**构造期**（Construction-phase，本方法论独创，定义见附录 A）。

构造期有三项核心活动，每一项对应三元组中的一个或多个维度：

**决策显式化（Decision Explicitation）**——规划层（`plan-author`）把"如何实现"的设计决策（技术选型、架构取舍、依赖引入）从规格层剥离出来，产出结构化 Plan。这些决策如果停留在对话中而不被显式记录，就无法成为 Guides 的一部分，AI 在实施期就得重新猜测一遍。

**契约翻译（Contract Translation）**——规格层（`spec-transformer`）把 Plan 中的决策与需求的 8 字段翻译为工程契约：先产出 9 节飞书 Spec（**Spec Stage 1**，本方法论独创，定义见附录 A），再由 **Spec Transformation Loop** 将其转化为 Spec Artifacts 四文件（**Spec Stage 2**，本方法论独创，定义见附录 A）。这一翻译步骤是"自然语言 → 机器可解析输入"的关键跨越，缺少它，三元组的 Guides 和 Sensors 两个维度都不完整。

**同步锚定（Synchronization Anchoring）**——`supersedes` 关联、`decision_id` 回溯、`req_id` 全链路穿透等锚点在构造期建立，保证实施期任何产物都可以追溯到产生它的原始决策或需求。这是 Invariants 维度在时间轴上的具体实现。

构造期结束的标志是 **Freeze Point**（本方法论独创，定义见附录 A）：由构造期状态机的 Hook 触发一次单向同步（飞书 Construction-phase SOT → GitHub Implementation-phase SOT），之后实施期只读消费其冻结态镜像，构造期产物不再可编辑。Freeze Point 是两段式时相的切换锚点，也是"AI 自驱实施闭环"得以启动的必要前置条件。

---

### §2.4 从构造期倒推：为何需要 Project 寿命层

构造期每个 REQ 的三元组生产活动，都依赖一批**跨 REQ 共享的项目级约束**：架构骨架（Architecture Snapshot）、技术栈声明、IM 集成配置、Known Constraint 集合、设计系统、CLAUDE.md 行为规则。这些条目不属于任何单个 REQ——它们是整个项目寿命内持续演化的共享资产，构成 **Project-level Context**（本方法论独创，定义见附录 A）。

如果没有 Project 寿命层，每个 REQ 的构造期都需要重新声明一遍项目级约束，且各 REQ 的声明之间无法保证一致性——Invariants 维度将在项目演化中迅速碎片化。

**Bootstrap**（本方法论独创，定义见附录 A）是 Project 寿命层的初始化流程，负责项目级约束的**首次创建**：建立飞书 ARCHITECTURE 文档（Architecture Snapshot 的 Construction-phase SOT）、初始化 CLAUDE.md、声明技术栈与 KC 集合。后续演化不通过 Bootstrap 重跑，而是由 REQ 驱动——具体而言，当某个 REQ 的 Plan 需要变更项目级架构或约束时，规划层通过 **Planning Approval Gate（D-PLAN-1）**（本方法论独创，定义见附录 A）获得技术负责人的显式授权，再将变更写回 Project-level Context。这一"首次 Bootstrap + 后续 REQ 驱动"的设计，使项目级约束始终有一个权威来源，不会因多 REQ 并行而产生分歧。

---

### §2.5 结论映射

上述四步倒推链产出两张核心结构，是 v3.0 全文剩余章节的骨架：

**条目类型表（§三）**——将三元组（Guides / Sensors / Invariants）× 寿命（Project-level / REQ-level）展开为约 17 条具体上下文条目，每条注明构造期介质、实施期介质、主产出责任方与生命周期动作。条目类型表是 v3.0 的共用字典，§五–§七 的每一层都从此表选取条目画矩阵增量。

**层结构矩阵（§四–§七）**——Project 寿命层（§五）+ 需求寿命层·构造期（§六）+ 需求寿命层·实施期（§七）组成两段式层结构；每层以 2×3 矩阵声明其在 Project-level / REQ-level × Guides / Sensors / Invariants 六个 cell 上的增量贡献，使各层职责在同一坐标系内可直接比较、不重叠、不遗漏。

**进入 §三**：在理解了"为什么是这些条目"之后，§三 将给出条目类型表的完整定义，并确立 Construction-phase SOT / Implementation-phase SOT / Freeze Point 的时相分段约定。

---

## §三 上下文条目类型表

本章是 v3.0 全文的**共用字典**。§五–§七 每一层的 2×3 矩阵均从本章条目类型表选取条目填写增量；任何在层章节中新增的上下文条目，都必须先在本章注册。

---

### §3.1 寿命二分：Project-level Context 与 REQ-level Context

上下文条目的第一切面是**寿命**。v3.0 将所有上下文条目按寿命划分为两类，二者并列构成"寿命二分"（本方法论独创，定义见附录 A）：

**Project-level Context**——跨 REQ 共享；在项目生命周期内持续存续；由 Project 寿命层（Bootstrap）完成首次创建，此后随 REQ 驱动演化（通过规划层 Planning Approval Gate 授权写回）。属于此类的条目不依附于任何单个 REQ 而存在，任何 REQ 均可读取但不得单方面修改。

**REQ-level Context**——per-REQ 存续；随 REQ 进入构造期而产生，随该 REQ 的交付闭环完成而不再演化（但其固化态作为 Invariants 持续被后续 REQ 引用）。属于此类的条目由特定 REQ 的构造期活动产出，生命周期与该 REQ 绑定。

两类寿命的区分是本方法论独创的核心切面，不与业界"冷/温/热上下文（Cold / Warm / Hot Context）"混用——后者描述注入策略（上下文以何种温度加载到 AI 窗口），前者描述所有权与演化归属。二者可以正交组合：同一条目既可以是 Project-level 也可以是 Hot Context（如 CLAUDE.md），具体注入策略见各层能力层绑定描述。

---

### §3.2 三元组定义：Guides / Sensors / Invariants

上下文条目的第二切面是**在 AI 自驱实施闭环中承担的角色**，即 §二 推导出的三元组。本节给出三元组的规范定义；§二 已从终态倒推角度论证其必要充分性，此处仅作定义性声明。

**Guides（约束集，前馈约束，Fowler 术语）**——在 AI 生成动作**发生之前**注入的设计契约，将解空间压缩到正确的子空间内。典型形式：接口定义、数据模型约定、架构接合点声明、技术选型决策、行为规则（CLAUDE.md）。Guides 类条目的核心属性是"前馈"：它们在 AI 看到任务之前已就位，使 AI 无需猜测设计意图。来源：Martin Fowler 控制论视角（"Control System Patterns"），本文取其原意。

**Sensors（偏离检测集，后馈反馈，Fowler 术语）**——在 AI 生成**之中或之后**检测偏离的机制，是"自修复实施循环"中"align → correct"两步得以自动化的前提。典型形式：AC oracle（`ac-schedule.yaml` 驱动的验收条件判定）、Harness 测试代码（P0 门）、视觉回归（Phase 2 UI 路径）。Sensors 类条目的核心属性是"后馈"：它们将 AI 产出与期望标准的偏离转化为结构化信号，CI oracle 据此驱动下一轮修正。来源：同 Fowler。

**Invariants（不变量）**——跨生成步骤保持不变的边界条件，防止 AI 以修正局部失败为由越界触碰既有契约。典型形式：历史 AC 的 `supersedes` 关系、Known Constraint（KC）集合、架构复用规定、ACM Registry 的累积记录。Invariants 类条目的核心属性是"不可变性"：它们在实施期只允许追加，不允许修改或删除既有记录。来源：CS/工程通用术语。

三元组是 AI 自驱实施闭环的必要充分条件——Guides 确定方向，Sensors 判定成败，Invariants 守护边界，缺一不可（详见 §2.2）。一个条目可以同时归属多个三元组维度（如 `design.md` 同时承担 Guides 和 Invariants 角色），此时以复合标注表示。

---

### §3.3 条目类型表

下表列出 v3.0 全方法论中所有已定义的上下文条目类型，共 17 条，按 Project-level 到 REQ-level 排列。每条包含寿命类别、三元组归属、构造期介质、实施期介质、主产出责任方。

| 类型名 | 寿命类别 | 三元组归属 | 构造期介质 | 实施期介质 | 主产出责任方 |
|---|---|---|---|---|---|
| Tech Stack Declaration | Project-level | Guides | ProjectConfig（Coordinator Service） | ProjectConfig 只读 | Bootstrap |
| CLAUDE.md 行为规则 | Project-level | Guides | GitHub 仓库文件 | GitHub 仓库文件（热加载） | Bootstrap + 人工维护 |
| Architecture Snapshot（组件 / 接口 / 数据模型） | Project-level | Guides | 飞书 ARCHITECTURE docx | `docs/ARCHITECTURE.md` | 规划层（plan-author + Planning Approval Gate） |
| Known Constraint（KC） | Project-level | Invariants | 飞书 ARCHITECTURE docx · known_constraints 节 | `docs/ARCHITECTURE.md` 同节 | 规划层 / 人工 |
| AI Integration Registration | Project-level | Guides | 飞书 ARCHITECTURE docx · ai_integrations 节 | `docs/ARCHITECTURE.md` 同节 | 规划层 |
| External Integration（IM / 第三方 API） | Project-level | Guides | 飞书 ARCHITECTURE docx · external_integrations 节 | `docs/ARCHITECTURE.md` 同节 | Bootstrap + 规划层 |
| Design System（Token / 组件 / 交互模式） | Project-level | Guides | 飞书设计系统文档 | `specs/design-system-snapshot.yaml` | 设计层（UI 两阶段，Phase 2 启用） |
| ACM Registry（acm-registry.yaml） | Project-level | Invariants | — | `acm-registry.yaml` | Checkpoint Handler |
| Requirement Doc（8 字段） | REQ-level | Guides | 飞书需求文档 | — | 需求层 |
| Plan（Decisions + 可选 project_context_change） | REQ-level | Guides | 飞书 Plan docx | `plans/<req_id>.md` | 规划层 |
| Design Artifact（UI 低保真 + 高保真） | REQ-level | Guides | 飞书 design docx | `docs/specs/REQ-*/design/` | 设计层 |
| Spec Stage 1（9 节飞书 Spec） | REQ-level | Guides | 飞书 9 节 Spec docx | `specs/<req_id>/spec.md` | 规格层（spec-author） |
| design.md（接口契约 + 数据模型 + 架构接合点 + supersedes） | REQ-level | Guides + Invariants | — | `docs/specs/REQ-*/design.md` | 规格层（spec-transformer） |
| tasks.md | REQ-level | Guides | — | `docs/specs/REQ-*/tasks.md` | 规格层（spec-transformer） |
| ac-schedule.yaml（本 REQ 的 AC 排班） | REQ-level | Sensors | — | `docs/specs/REQ-*/ac-schedule.yaml` | 规格层（spec-transformer） |
| Harness Test Code | REQ-level | Sensors | — | `harness/tests/REQ-*/` | Harness 层 |
| Impl PR | REQ-level | —（产物） | — | GitHub PR | 生成层 |

**字段语义说明**：

- **寿命类别**：`Project-level` = 跨 REQ 共享，项目生命周期内存续；`REQ-level` = per-REQ 产物，随该 REQ 交付闭环完成后不再演化。
- **三元组归属**：该条目在 AI 实施闭环中承担 Guides / Sensors / Invariants 中的哪一个（或复合角色）；`—（产物）` 表示该条目是实施活动的输出而非上下文输入。
- **构造期介质** / **实施期介质**：遵循时相分段约定（见 §3.5）；构造期介质为空表示该条目仅在实施期 AI 产出阶段产生，不经构造期固化。
- **主产出责任方**：负责条目首次产出及后续演化的层或角色；Project-level 条目的演化通道须经 Planning Approval Gate 授权。

---

### §3.4 2×3 矩阵总览

**矩阵定义**：以寿命类别（Project-level / REQ-level）为列，以三元组（Guides / Sensors / Invariants）为行，构成 2 列 × 3 行共 **6 个 cell** 的矩阵框架。§五–§七 的每一层都在此矩阵上声明本层的**增量贡献**——即本层新增、修改或冻结了哪些上下文条目。

**Cell 填写规范**：每个 cell 列出从 §3.3 条目类型表中选取的具体条目，附加一个**动作动词**，说明本层对该条目的操作类型：

- **create**：本层首次产出该条目（之前不存在）
- **amend**：本层在已有条目上追加或修改（须经对应授权机制）
- **freeze**：本层触发 Freeze Point，将该条目从构造期 SOT 同步至实施期 SOT，进入只读态
- **reference**：本层消费该条目但不修改（只读引用）
- **invalidate**：本层使该条目的某个版本失效（如 `supersedes` 关系建立时）

每个 cell 可以包含多个条目，每条一行，格式为 `条目名（动作）`。若某层对某个 cell 无贡献，显式标注 `N/A`，不得留空。

**矩阵模板**（§五–§七 各层在此基础上填写增量）：

```
                  │ Project-level        │ REQ-level
─────────────────┼──────────────────────┼──────────────────────
Guides（约束集）  │ [本层新增/修改的      │ [本层新增/修改的
                  │  项目级约束条目]      │  需求级约束条目]
─────────────────┼──────────────────────┼──────────────────────
Sensors（偏离    │ [本层新增/修改的      │ [本层新增/修改的
 检测集）         │  项目级反馈条目]      │  需求级反馈条目]
─────────────────┼──────────────────────┼──────────────────────
Invariants        │ [本层新增/修改的      │ [本层新增/修改的
（不变量）         │  项目级不变量条目]    │  需求级不变量条目]
─────────────────┴──────────────────────┴──────────────────────
```

**后续章节约定**：§五（Project 寿命层）、§六（需求寿命层·构造期，含 §6.1–§6.3 三层）、§七（需求寿命层·实施期，含 §7.1–§7.5 五层）的每个子层均将填写上述矩阵的增量版本，6 个 cell 必须全部显式声明（N/A 或具体条目），不得省略。这一机制保证各层职责在同一坐标系内可直接比较、不重叠、不遗漏。

---

### §3.5 时相分段约定

时相分段是 v3.0 解决"构造期 SOT 与实施期 SOT 共存"问题的核心机制（本方法论独创，定义见附录 A）。本节给出三概念的规范定义、受约束与不受约束的条目清单，以及四条关键原则。

#### 三概念定义

**Construction-phase SOT（构造期单一真相源）**——人类与 AI Agent 协同撰写、评审、固化上下文条目的时间窗口及其介质。构造期 SOT 的介质为**飞书文档**（ARCHITECTURE docx、Plan docx、9 节 Spec docx 等），支持在线协同编辑，直至 Freeze Point 触发前均可修改。构造期 SOT 的权威性体现在：飞书文档是该时相的唯一写入点，GitHub 侧此时仅有旧版镜像（若有），不具权威性。

**Implementation-phase SOT（实施期单一真相源）**——AI Coding Agent 只读消费上下文条目的时间窗口及其介质。实施期 SOT 的介质为 **GitHub 仓库**（`docs/ARCHITECTURE.md`、`plans/<req_id>.md`、`specs/<req_id>/spec.md` 及 Spec Artifacts 四文件等），AI 从仓库文件读取，不再回写飞书。实施期 SOT 是 Freeze Point 触发后产生的只读镜像，不支持原地修改——若发现错误须走 Cascading Reset 回退到构造期重新固化。

**Freeze Point（冻结点）**——由构造期状态机的 Hook 触发的单向同步事件（飞书 Construction-phase SOT → GitHub Implementation-phase SOT）。Freeze Point 触发后，对应条目进入只读态：飞书侧锁定不可编辑，GitHub 侧成为 AI 消费的权威镜像。不支持反向回流（GitHub → 飞书），也不支持局部解冻（只能整体 Cascading Reset 回退）。Freeze Point 是两段式时相切换的物理锚点，也是 AI 自驱实施闭环启动的必要前置条件。

#### 受时相分段约束的条目

以下条目在构造期以飞书为 SOT，在 Freeze Point 后以 GitHub 为 SOT，两个时相各有唯一权威介质：

- **Architecture Snapshot**（含 Known Constraint / AI Integration Registration / External Integration 各节）：飞书 ARCHITECTURE docx → `docs/ARCHITECTURE.md`
- **Plan**：飞书 Plan docx → `plans/<req_id>.md`
- **Spec Stage 1**（9 节飞书 Spec）：飞书 9 节 Spec docx → `specs/<req_id>/spec.md`
- **Design System**（Phase 2 启用后）：飞书设计系统文档 → `specs/design-system-snapshot.yaml`

#### 不受时相分段约束的条目

以下条目只存在于实施期（无构造期介质），或其 SOT 天然唯一、无需时相切换：

- **Design Artifact**（UI 低保真 / 高保真）：仅在实施期 `docs/specs/REQ-*/design/` 存在，无飞书 SOT 切换场景
- **Spec Artifacts（Stage 2）**（`design.md` / `tasks.md` / `ac-schedule.yaml`）：由 Spec Transformation Loop 在实施期直接产出，不经飞书中转
- **Harness Test Code**：由 Harness 层在实施期产出，始终以 GitHub 仓库为唯一 SOT
- **ACM Registry**（`acm-registry.yaml`）：始终以 GitHub 仓库根目录为唯一 SOT，由 Checkpoint Handler 追加，无飞书副本

#### 四条关键原则

1. **单一时相单一 SOT**：同一条目在任意给定时相内只能有一个权威真相源——构造期是飞书，实施期是 GitHub；不允许"飞书和 GitHub 都算数"的双权威状态同时存在。
2. **单向同步**：Freeze Point 触发的同步方向永远是飞书 → GitHub，不支持反向回流；若实施期发现构造期产物有误，必须通过 Cascading Reset 将状态回退到构造期，重新固化后再次 Freeze。
3. **Freeze 不可变**：Freeze Point 触发后，构造期 SOT（飞书文档）进入锁定状态，实施期 SOT（GitHub 文件）只允许 AI 读取，不允许任何方（包括人工）直接在 GitHub 侧修改已冻结的条目（CLAUDE.md、Tech Stack Declaration 等天然以 GitHub 为唯一介质的条目不在此限）。
4. **渲染契约保 AI 可解析**：所有同步到 GitHub 的条目必须以结构化格式渲染（Markdown 结构化节、YAML、代码块），确保 AI Coding Agent 在无需额外解析逻辑的情况下可直接消费；自然语言叙述仅作补充，结构化字段是机器消费的权威。

---

## §四 层结构与纵向工作流模板

### §4.1 两段式层结构总览

v3.0 以**寿命**为第一切面，将 9 个子层划分为两大寿命域：

- **Project 寿命层**（1 个子层）：贯穿整个项目生命周期的一次性初始化层（Bootstrap），负责建立全项目共享的 Project-level Context 基础。不随 REQ 重复执行；后续演化通过需求寿命层的授权机制驱动。
- **需求寿命层**（8 个子层）：每条 REQ 从提出到交付所经历的全链路，内部进一步分为两段：
  - **构造期**（3 个子层）：需求层 → 规划层 → 规格层。人-AI 协同在飞书 Construction-phase SOT 中生产三元组的原材料，以 Freeze Point 结束构造期。
  - **实施期**（5 个子层）：Harness 层 → 生成层 → 验证层 → 集成层 → 交付层。AI Coding Agent 以 GitHub Implementation-phase SOT 为只读输入驱动 AI 自驱实施闭环。

合计：1 + 3 + 5 = **9 个子层**。全部 9 个子层都必须按 §3.4 矩阵填写增量 cell；部分 cell 可显式标注 N/A，不得留空。

**ASCII 架构图**（横向为"人工协同轨 / 工程自动化轨"，纵向为"Project 寿命 → 构造期 → 实施期"）：

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              横向基础设施                                      │
│   人工协同轨（飞书 + OpenClaw）          ║   工程自动化轨（GitHub + CI）           │
╠══════════════════════════════════════════╬═════════════════════════════════════╣
│  【Project 寿命层（§五）】                                                      │
│  Bootstrap / Project 层                 ║  — （首次 Plan READY 触发 Freeze,    │
│  Coordinator Service 初始化              ║    GitHub 侧产出首份 ARCHITECTURE.md）│
│  飞书 ARCHITECTURE docx 创建             ║                                      │
╠══════════════════════════════════════════╬═════════════════════════════════════╣
│  【需求寿命层·构造期】                                                           │
│  §6.1 需求层                             ║  — （纯飞书侧；Bitable + 需求文档）    │
│  Coordinator + requirement-author/       ║                                      │
│  requirement-reviewer                    ║                                      │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  §6.2 规划层                             ║  — （Planning Approval Gate 授权后     │
│  Coordinator + plan-author +             ║    触发 project_context_change 写回    │
│  design-author（needs_ui=true）          ║    GitHub，Architecture Snapshot 更新）│
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  §6.3 规格层                             ║  Freeze Point 触发 →                 │
│  Coordinator + spec-author +             ║  飞书 9节Spec → specs/<req_id>/spec.md│
│  spec-reviewer + spec-transformer +      ║  Spec Artifacts → docs/specs/REQ-*/  │
│  spec-transformer-reviewer               ║  （Spec Transformation Loop）         │
╠══════════════════════════════════════════╬═════════════════════════════════════╣
│  【需求寿命层·实施期】                                                           │
│  §7.1 Harness 层                         ║  GitHub Actions → harness/tests/REQ-*│
│  （D-HARN-1 人工判定：卡片）              ║  Checkpoint 1b                        │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  §7.2 生成层                             ║  Claude Code CLI → Impl PR            │
│                                          ║  自修复实施循环                        │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  §7.3 验证层                             ║  CI 全量 + AI 失败分析 → Checkpoint 2  │
│  （D-VAL-1 人工判定：卡片）              ║                                        │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  §7.4 集成层                             ║  staging.yml → Staging + Smoke Test   │
│  （D-INT-1 人工判定：卡片）              ║  Checkpoint 3                          │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  §7.5 交付层                             ║  deploy.yml → 生产部署 + 健康检查      │
╚══════════════════════════════════════════╩═════════════════════════════════════╝
```

---

### §4.2 三层分离元原则

本方法论在实现层面严格执行三层分离，以保证 Workflow Service 的规则纯洁性与能力层的可替换性：

| 层 | 职责 | 关键性质 |
|---|---|---|
| **Workflow Service** | 状态机定义、状态转移规则、Hook 派发、状态持久化 | 纯规则、无 AI、无具体业务动作、项目无关 |
| **Hook 实现** | 状态转移动作的具体实现（`onEnter` / `onExit` 回调） | 业务逻辑所在地，调用能力层，可独立测试 |
| **能力层** | AI Agent / 人工 / 外部 API 等可插拔能力提供方 | 可替换、契约化、不持有状态 |

**三条不可违背性质**：

1. **Workflow Service 不 import 任何能力层 SDK**——状态机逻辑对具体 AI 模型、飞书 API、CI 平台零依赖。
2. **能力层替换零成本**——替换底层 AI 模型或 CI 平台只需修改能力层实现，不改 Workflow Service 或 Hook 接口。
3. **状态机与 Hook 实现可独立测试**——状态机单测不依赖真实 Agent 或网络调用；Hook 单测可用 stub 替换能力层。

本元原则在构造期与实施期以不同形态实例化，分别见 §4.3 / §4.4。

---

### §4.3 构造期工作流模板

构造期（需求层 / 规划层 / 规格层）的三层分离具象形态如下：

| 三层分离位置 | 构造期具象 |
|---|---|
| **Workflow Service** | **Coordinator Service**（本方法论独创，定义见附录 A）：持有 Requirement 状态机，以及 DesignStatus / PlanStatus / SpecStatus 三列 Parallel Sub-State Tracks |
| **Hook 触发介质** | `StateTransitionHooks.on_enter` / `on_exit` 注册点；每次状态转移后由 Coordinator Service 派发对应 Hook |
| **能力层** | **OpenClaw Agent**（`requirement-author` / `requirement-reviewer` / `plan-author` / `design-author` / `spec-author` / `spec-reviewer` / `spec-transformer` / `spec-transformer-reviewer`） |
| **人类决策点载体** | **飞书消息卡片**（按钮回调至 Coordinator Service 的 `/cards/<action>-<subject>` 端点） |
| **CLI 接入** | `/create project` / `/create req` / `/plan restart` / `/design restart` / `/spec restart` 等固化命令（见 §4.7） |

**每层声明模板**（§六 需求 / 规划 / 规格层统一套用本模板）：

```
① 状态集          [枚举本层状态机的所有状态]
② 事件集          [枚举触发状态转移的所有事件]
③ 状态转移图      [以表格或 ASCII 图表示从→至的转移规则]
④ Hook 清单       [onEnter / onExit：触发条件 + 调用能力层契约]
⑤ Agent 契约      [能力层 Agent 列表：入参格式 / 出参格式 / 失败返回]
⑥ 端点清单        [GET /queries/openclaw/<layer>-context（上下文拉取）
                    POST /openclaw/<agent>-callback（Agent 写回）
                    POST /cards/<action>-<subject>（卡片回调）]
```

---

### §4.4 实施期工作流模板

实施期（Harness 层 / 生成层 / 验证层 / 集成层 / 交付层）的三层分离具象形态如下：

| 三层分离位置 | 实施期具象 |
|---|---|
| **Workflow Service** | **Checkpoint Handler**（本方法论独创，定义见附录 A）：接收 GitHub Actions workflow 的 CI 回调、PR 事件，触发对应内部状态转移 |
| **Hook 触发介质** | **GitHub Actions workflow**（`.github/workflows/*.yml`）+ Checkpoint Handler 内部状态转移；CI 结果由 webhook 推回 Checkpoint Handler |
| **能力层** | **Claude Code CLI**（执行代码生成与自修复实施循环）+ **GitHub Actions 内置步骤**（CI / 部署脚本）+ **AI 失败分析脚本**（可选，Inferential signal 兜底） |
| **人类决策点载体** | 飞书消息卡片（按钮回调至 Checkpoint Handler） |
| **CLI 接入** | 主要通过 PR 分支 + commit 消息驱动；少量显式命令如 `/harness restart` |

**每层声明模板**（§七 Harness / 生成 / 验证 / 集成 / 交付层统一套用本模板）：

```
① 输入产物集合     [消费的 Guides / Sensors / Invariants 条目（from §3.3 条目类型表）]
② workflow 触发条件 [触发本层 GitHub Actions workflow 的事件（push / PR / workflow_run 等）]
③ 通过判定         [Computational（pytest / schema / lint，机械判定，优先）
                     vs Inferential（LLM judge / 人工 review，兜底）]
④ 人类决策点       [若有：决策点 ID（from §4.5 模板）/ 触发 state / 载体 / 判断权]
⑤ 失败路径         [CI 红线处理 / Cascading Reset 路径 / 人工介入触发条件]
```

---

### §4.5 人类决策点统一模板

全部 8 个决策点（D-REQ-1/2、D-PLAN-1/2、D-SPEC-1、D-HARN-1、D-VAL-1、D-INT-1）在 §六 / §七 各层的决策点清单子节中按以下模板填写。全部决策点合并索引见 §八.4。

**决策点模板**：

```
决策点 ID：[全局唯一编号，与 §八.4 总览表对齐]
名称：[简短可读名称]
触发 state：[状态机中哪个 state 的 onEnter 触发此决策]
载体：[飞书消息卡片 / CLI 命令 / Bitable 表单]
选项集：[如 "通过 / 驳回"，或 "通过 / 驳回 / 暂缓"]
落点：[决策结果写入哪个条目 / 状态字段 / Bitable 列]
失败路径：[驳回时的处理：Cascading Reset / 重试 / 终止 / 等待]
判断权：[具体角色，如 技术负责人 / 产品负责人 / Author]
```

**示例（D-REQ-1）**：

```
决策点 ID：D-REQ-1
名称：Requirement Dual Gate（AI Ready + Human Confirmed）
触发 state：HUMAN_CONFIRM（Requirement 状态机）
载体：飞书消息卡片（按钮："确认需求" / "退回修改"）
选项集：通过（Human Confirmed = true）/ 驳回（返回 DRAFTING）
落点：Bitable human_confirmed 字段；Coordinator Service Requirement 状态 → CONFIRMED
失败路径：驳回 → 需求状态回退至 DRAFTING；requirement-author 重新激活
判断权：Author（需求提出人）+ 项目干系人
```

> AI Ready 子判断（`ai_ready` 字段）由 requirement-reviewer 完成 Computational / Inferential 混合判定，Human Confirmed 子判断为纯人工。两个子判断都为 `true` 时 D-REQ-1 方视为通过。

---

### §4.6 REQ ID 全链路穿透

`REQ-{PROJECT}-{NNN}` 是贯穿全链路的唯一索引，任何工件都能通过 REQ ID 追溯到源头需求。格式约定：`PROJECT` 为项目缩写（全大写），`NNN` 为三位数字序号（001 起始）。

| 工件 | REQ ID 出现位置 |
|---|---|
| 飞书需求文档 | 文档标题前缀（如 `[REQ-PROJ-001] 需求名称`） |
| Bitable 追踪表 | 主键字段 `req_id` |
| GitHub 分支 | `spec/REQ-{PROJECT}-{NNN}`、`impl/REQ-{PROJECT}-{NNN}` |
| Spec / ACM 文件 | 文件 metadata 字段 `req_id`（`specs/<req_id>/spec.md`，`docs/specs/REQ-*/`） |
| Harness PR / Impl PR | PR 标题前缀 |
| 飞书决策卡片 | 卡片标题 + 消息体 |
| `acm-registry.yaml` | 条目的 `req_id` 字段 |
| 飞书 Plan docx | 文档 metadata 字段（`plans/<req_id>.md` 实施期镜像） |

REQ ID 的穿透使任意工件可以反向追溯到：该工件由哪条 REQ 产生、对应哪个构造期产物、关联哪些 AC。§六 / §七 各层在 2×3 矩阵增量中须确保本层产出的工件包含 `req_id` 字段。

---

### §4.7 卡片与 CLI 端点命名规范

端点与 CLI 命名遵循以下约定，目的是让 OpenClaw Agent 能从端点名直接推知该端点的层归属与用途，无需额外文档查阅：

**端点路径命名**：

| 类型 | 规范形式 | 示例 |
|---|---|---|
| 上下文拉取（GET） | `/queries/openclaw/<layer>-context` | `/queries/openclaw/requirement-context`、`/queries/openclaw/planning-context` |
| Agent 写回（POST） | `/openclaw/<agent>-callback` | `/openclaw/spec-transformer-callback`、`/openclaw/plan-author-callback` |
| 飞书卡片回调（POST） | `/cards/<action>-<subject>` | `/cards/approve-plan`、`/cards/reject-spec`、`/cards/confirm-requirement` |

**CLI 命名**：

| 类型 | 规范形式 | 示例 |
|---|---|---|
| 资源创建 | `/create <resource>` | `/create project`、`/create req` |
| 层级 Cascading Reset | `/<status-column> restart <req>` | `/plan restart REQ-PROJ-001`、`/spec restart REQ-PROJ-002` |

**命名原则**：
- `<layer>` 取各层 canonical 名（`requirement` / `planning` / `spec` / `harness` / `generation`）；
- `<agent>` 取 §5.4 所列 Agent canonical 名（`requirement-author` / `plan-author` / `spec-transformer` 等）；
- `<action>` 用 `approve` / `reject` / `confirm` / `restart`；`<subject>` 用层或工件名。
- CLI 中 `<status-column>` 对应 Coordinator Service 内部 Parallel Sub-State Tracks 的列名（`plan` / `design` / `spec`）。

---

<!-- §五 及后续章节由 Task 5–12 填写 -->
