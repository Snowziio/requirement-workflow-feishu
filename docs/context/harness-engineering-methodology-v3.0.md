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

## §五 Project 寿命层

> **层归属**：Project 寿命层——位于需求寿命层之前，承载项目从 0 到 1 的生命周期管理。

---

### §5.1 使命

Project 寿命层是 harness 方法论中**项目生命周期的起点**。其使命：通过一次显式、幂等、可审计的 **Bootstrap**（本方法论独创，定义见附录 A）事件，完成项目的首次创建——建立 GitHub 仓库骨架、飞书 ARCHITECTURE 文档（Architecture Snapshot 的 Construction-phase SOT）、飞书协作群，并写入 Project-level Guides 与 Invariants 的初始骨架。所有后续 REQ（Requirement / Planning / Spec 链路）必须挂靠在一个状态为 `PROVISIONED` 的 Project 上。项目级上下文的后续演化不通过 Bootstrap 重跑，而是由 REQ 驱动——经规划层 Planning Approval Gate 授权后写回。

---

### §5.2 输入

#### A. 上下文输入

无——Project 寿命层是整个方法论的起点，无上游层可继承上下文。

#### B. 人类决策点

| # | 决策点 | 触发载体 | 说明 |
|---|---|---|---|
| 1 | **项目创建启动** | `/create project <name> --category <c> --owner <uid>` CLI 命令 | 人类显式触发，无前置 gating；加入 bot 的飞书用户均可执行 |
| 2 | **项目元数据录入** | CLI 参数 | 名称（`^[a-z][a-z0-9-]{2,30}$`，全局唯一）、技术栈分类（`category`：`enterprise-app` / `enterprise-bot` / `miniprogram` / `public-web-site` / `saas-ai-automation`）、归属人（飞书 `open_id`） |

Bootstrap 过程本身无人工决策点——7 步全自动执行；失败时以固化卡片提示断点，人工执行 `/create project --resume <name>` 续跑。

---

### §5.3 2×3 矩阵增量（Project 寿命层产出）

| | Project-level | REQ-level |
|---|---|---|
| **Guides（约束集）** | **create**: Tech Stack Declaration（本方法论独创，定义见附录 A）/ CLAUDE.md 行为规则 / Architecture Snapshot 骨架（飞书 ARCHITECTURE docx）/ External Integration（本方法论独创，定义见附录 A）（IM 平台集成条目写入 ARCHITECTURE docx） | N/A |
| **Sensors（偏离检测集）** | N/A | N/A |
| **Invariants（不变量）** | **create**: Known Constraint（KC）初始集（若 category 模板预置；写入 ARCHITECTURE docx `known_constraints` 节） | N/A |

**说明**：
- Bootstrap 只负责**首次 create**——骨架占位，无需在 0 需求阶段做技术选型
- Architecture Snapshot 骨架建于飞书 ARCHITECTURE docx（Construction-phase SOT）；首份 GitHub `docs/ARCHITECTURE.md` 副本由首个 plan READY 同步产出，避免空镜像（见 §3.5 时相分段约定）
- Tech Stack Declaration 以 `ProjectConfig.tech_stack` 字段持久化于 Coordinator Service 存储；category 决定骨架内容
- Bootstrap 不产出任何 REQ-level 条目，REQ-level 列全为 N/A

---

### §5.4 状态机

#### 状态集

| 状态 | 含义 | 可挂 REQ | MVP 实现 |
|---|---|---|---|
| `UNBOOTSTRAPPED` | 逻辑态；`project_configs` 无行即视为此态（不持久化） | ❌ | ✅（隐式） |
| `BOOTSTRAPPING` | `/create project` 已触发，Bootstrap 7 步进行中 | ❌ | ✅ |
| `PROVISIONED` | Bootstrap 全部成功，项目可挂 REQ | ✅ | ✅ |
| `ARCHIVED` | 冻结；`project/req-registry.yaml` 只读；拒收新 REQ | ❌ | ❌（Phase 2） |
| `DECOMMISSIONED` | 退役终态；repo 物理删除 + 群解散 + Bitable 行软删 | ❌ | ❌（Phase 2） |

> **MVP 实现范围**：前三态（`UNBOOTSTRAPPED` / `BOOTSTRAPPING` / `PROVISIONED`）；`ARCHIVED` 和 `DECOMMISSIONED` 留 Phase 2。

#### 事件集与转移规则

| 当前状态 | 事件 | 目标状态 |
|---|---|---|
| `UNBOOTSTRAPPED` | `/create project` CLI 命令 | `BOOTSTRAPPING` |
| `BOOTSTRAPPING` | 7 步全部成功 | `PROVISIONED` |
| `BOOTSTRAPPING` | `/create project --resume <name>`（从断点续跑） | `BOOTSTRAPPING`（幂等重入） |
| `PROVISIONED` | `/archive project`（Phase 2） | `ARCHIVED` |
| `ARCHIVED` | `/decommission project`（Phase 2） | `DECOMMISSIONED` |

**无"回退"路径**：失败 = 保留已完成步骤状态，`--resume` 续跑；不回退到 `UNBOOTSTRAPPED`。超过 24 小时未推进到 `PROVISIONED` → 群内自动告警卡。

#### Bootstrap 7 步（每步幂等，`--resume` 可续跑）

| 步 | 标识符 | 动作 | 产出 / 幂等方式 |
|---|---|---|---|
| 1 | `VALIDATE` | 校验输入（name 正则 + 全局唯一性；category 合法；owner 非空） | 无副作用；纯检查；失败不写任何状态 |
| 2 | `UPSERT_CONFIG` | Upsert `project_configs` 行，`bootstrap_status=BOOTSTRAPPING` | 按 project 主键 upsert；已有行则更新，不报错 |
| 3 | `CREATE_REPO` | 从 Template 仓库生成 `Snowziio/{project}` GitHub repo | repo 已存在则跳过（`get_repo` 探测） |
| 4 | `POPULATE_MAIN` | 一次 commit 到 main，渲染并写入所有 per-project 文件（`docs/ARCHITECTURE.md` / `CLAUDE.md` / `SKILL.md` / `project/req-registry.yaml` / `project/environments.yaml` / `project/SECRETS-TODO.md` 等） | 按文件 SHA 对比，缺则补，已存在则跳过 |
| 5 | `CREATE_ARCHITECTURE_DOC` | 创建飞书 ARCHITECTURE docx（Construction-phase SOT），写入 category 渲染后的骨架内容；回写 `architecture_doc_id` / `architecture_doc_url` | 若 `architecture_doc_id` 已有则跳过 |
| 6 | `CREATE_FEISHU_GROUP` | 创建飞书协作群，拉入 owner + 机器人 | 若 `feishu_chat_id` 已有则跳过 |
| 7 | `FINALIZE` | `bootstrap_status=PROVISIONED`；群内发欢迎卡；进度卡更新为"全部绿" | 终态标记 |

每步执行后 append 一条 `bootstrap_log` 条目（`{step, ts, status, error_msg}`），支持断点可视化与续跑定位。

---

### §5.5 Hook 装配

Bootstrap 7 步以顺序过程式方式执行（非状态机 onEnter / onExit 分派），每步对应一个幂等 Hook 实现：

| 步骤 | Hook 实现 | 调用能力层 |
|---|---|---|
| VALIDATE | `bootstrap_hooks.validate_input(name, category, owner)` | 无（纯本地校验） |
| UPSERT_CONFIG | `bootstrap_hooks.upsert_project_config(project, category, owner)` | Coordinator Service 存储（Bitable `project_configs`） |
| CREATE_REPO | `bootstrap_hooks.create_repo_from_template(project)` | GitHub API（Template Generate `POST /repos/Snowziio/Template-repository/generate`） |
| POPULATE_MAIN | `bootstrap_hooks.populate_main_branch(project, category)` | GitHub API（`commit_files` primitive，单次 commit 到 main） |
| CREATE_ARCHITECTURE_DOC | `bootstrap_hooks.create_architecture_document(project, category)` | Feishu API（创建 docx + 写入渲染骨架） |
| CREATE_FEISHU_GROUP | `bootstrap_hooks.create_feishu_group(project, owner)` | Feishu API（建群 + 拉人 + 拉机器人） |
| FINALIZE | `bootstrap_hooks.finalize(project)` | Coordinator Service 存储（更新 `bootstrap_status=PROVISIONED`）+ Feishu API（发欢迎卡、更新进度卡） |

**Coordinator Service 在 Bootstrap 触发后**派发一个进度卡片，Bootstrap 推进时实时更新卡片状态；全部成功后卡片变绿，失败时卡片变红并显示断点步骤与 `--resume` 提示。

---

### §5.6 能力层绑定

| 能力层 | 角色 | 绑定环节 |
|---|---|---|
| **Coordinator Service** | Workflow Service；接收 `/create project` CLI 命令，解析参数，顺序编排 Bootstrap 7 步，持久化 `project_configs` 状态 | 全程驻留；Bootstrap 入口与 FINALIZE 均由 Coordinator Service 发起 |
| **Feishu API** | 外部 API；创建飞书 ARCHITECTURE docx（Step 5）+ 创建协作群并拉入成员（Step 6）+ 发送进度卡片与欢迎卡（Step 7） | Steps 5 / 6 / 7 |
| **GitHub API** | 外部 API；从 Template 仓库 Generate 新 repo（Step 3）+ 单次 commit populate per-project 文件（Step 4） | Steps 3 / 4 |

> Project 寿命层的 Bootstrap 不使用 OpenClaw Agent——Bootstrap 是纯编排性质的流程（validate + create），无需 AI 推理能力。后续项目级上下文的演化（如 ARCHITECTURE 更新）由规划层 plan-author Agent 经 Planning Approval Gate 授权后执行，见 §6.2。

---

### §5.7 完成标准 & 失败回退

#### 完成标准

Bootstrap 成功的判定条件（全部满足才视为 `PROVISIONED`）：

1. `bootstrap_status == PROVISIONED`（`project_configs` 行已写入）
2. `project_configs` 行已落地，含 `tech_stack` / `category` / `feishu_chat_id` / `architecture_doc_id` / `github_repo_url`
3. 飞书 ARCHITECTURE docx 已建（空骨架），`architecture_doc_id` / `architecture_doc_url` 已回写
4. GitHub repo（`Snowziio/{project}`）已从 Template 仓库生成，per-project 文件已 populate 到 main
5. 飞书协作群已建，owner + 机器人均已入群，`feishu_chat_id` 已回写

#### 失败回退

- 任一步失败 → `bootstrap_status` 保持 `BOOTSTRAPPING`（不推进、不回退）
- `bootstrap_log` 记录断点步骤 + 错误信息；进度卡片变红并显示断点
- 人工排查后执行 `/create project --resume <name>` → 从最后成功步+1 开始续跑（每步入口先做幂等检查）
- 24 小时内未推进到 `PROVISIONED` → 群内自动发告警卡
- 没有自动回退路径——已完成步骤的副作用（如已建 GitHub repo）通过幂等跳过保留，不尝试撤销

#### 演化说明

Bootstrap 只负责项目级上下文的**首次创建**。后续 Project-level 条目的演化（Architecture Snapshot / Known Constraint / External Integration 的增量变更）由规划层 Planning Approval Gate（D-PLAN-1）驱动，详见 §6.2。Bootstrap 不重跑，项目级资产的变更路径唯一：REQ → plan-author → `project_context_change` 信封 → Planning Approval Gate 授权 → 写回飞书 ARCHITECTURE docx。

---

## §六 需求寿命层 · 构造期

需求寿命层·构造期（§六）含三个子层：**§6.1 需求层**、**§6.2 规划层**、**§6.3 规格层**。三层按顺序承接客户输入、产出机器可解析规格，并在构造期以飞书为 SOT（单一可信源）——在 §6.3 的冻结点（freeze-point）才向 GitHub 单向同步（详见 §四）。

---

### §6.1 需求层（Requirement Layer）

#### §6.1.1 使命

将模糊的客户需求转化为经 **Requirement Dual Gate**（D-REQ-1）双路确认的结构化 **Requirement Doc**（8 字段固定格式），形成 REQ-level Guides 起点，并在正式审查（D-REQ-2）通过后以 `APPROVED` 状态移交规划层。全过程约 80 字概括：客户模糊描述 → author 多轮 IM 补全 → AI 审查 + 人工确认双路闸门 → 正式审查卡片 → APPROVED Requirement Doc。

#### §6.1.2 输入

**A. 上下文（只读，Project-level 全集）**

| 条目 | 类型 | 说明 |
|---|---|---|
| Tech Stack | Project-level Guide | 技术选型约束，供 author 字段补全参考 |
| Architecture Snapshot | Project-level Guide | 当前架构快照（飞书 ARCHITECTURE docx），需求层只读 |
| Known Constraints | Project-level Invariant | 不可逾越约束清单 |
| Design System | Project-level Guide | UI 组件规范，`needs_ui = true` 时 author 参考 |

**B. 决策点（本层触发）**

| ID | 名称 | 类型 | 说明 |
|---|---|---|---|
| **D-REQ-1** | **Requirement Dual Gate** | 复合决策点（AI Ready + Human Confirmed） | 两道独立准入门，分别记录、分别失败、分别追溯；任一门失败回 `DRAFTING`，双路全绿方可进入 `FINAL_REVIEW` |
| **D-REQ-2** | **Requirement Final Review** | 人工审查决策点 | 在项目群发正式审查卡片，项目干系人参与判断；通过 → `APPROVED`；打回 → 回 `DRAFTING` |

#### §6.1.3 2×3 矩阵增量

| | Project-level | REQ-level |
|---|---|---|
| Guides | N/A | **create**: Requirement Doc（8 字段） |
| Sensors | N/A | N/A |
| Invariants | N/A | N/A |

> **说明**：需求层仅消费 Project-level 条目（只读），不新增或修改 Project-level cell。REQ-level Guides 增量为本层首次创建的 Requirement Doc；Sensors（偏离检测集）与 Invariants 在本层均无新增条目。

#### §6.1.4 状态机

**6 态状态机**：

```
CREATED → DRAFTING → AI_REVIEW → HUMAN_CONFIRM → FINAL_REVIEW → APPROVED
                   ↑___________↙              ↑___________↙       ↑________↙
                （AI 退回）              （人工打回）        （审查打回，回 DRAFTING）
```

**状态说明**：

| 状态 | 含义 |
|---|---|
| `CREATED` | REQ 已创建，尚未开始起草 |
| `DRAFTING` | author Agent 正在 IM 多轮补全字段 |
| `AI_REVIEW` | reviewer Agent 执行 AI 审查；AI Ready 子位在此阶段写入 |
| `HUMAN_CONFIRM` | 人工确认阶段；Human Confirmed 子位在此阶段写入 |
| `FINAL_REVIEW` | 正式审查卡片已推送；需等待干系人通过 |
| `APPROVED` | 双路全绿且正式审查通过；Requirement Doc 冻结，移交规划层 |

**Requirement Dual Gate（D-REQ-1）细节**：AI Ready 与 Human Confirmed 两道门独立记录、独立失败、独立追溯。任意一道门失败均回退 `DRAFTING`，两道门之间不相互污染。双路全绿是进入 `FINAL_REVIEW` 的必要条件。

#### §6.1.5 Hook 装配

| 事件 | Hook | 动作 |
|---|---|---|
| `onEnter(DRAFTING)` | Coordinator Service | 派发 `requirement-author`（OpenClaw Skill），在 author 私聊中开始字段补全 IM 多轮 |
| `onEnter(AI_REVIEW)` | Coordinator Service | 派发 `requirement-reviewer`（OpenClaw Skill），执行 AI 审查并写回 `ai_ready` 标志位 |
| `onEnter(FINAL_REVIEW)` | Coordinator Service | 向项目群推送正式审查卡片，触发 D-REQ-2 人工决策流 |
| `onExit(FINAL_REVIEW)` | Checkpoint Handler | 将最终 `status`（`APPROVED` 或回退态）写回飞书 Bitable，更新 REQ 状态字段 |

#### §6.1.6 能力层绑定

**OpenClaw Skill**：

| Skill | 触发时机 | 职责 |
|---|---|---|
| `requirement-author` | `onEnter(DRAFTING)` | IM 多轮交互补全 Requirement Doc 8 字段；section-level 幂等写回飞书 docx |
| `requirement-reviewer` | `onEnter(AI_REVIEW)` | 审查 Requirement Doc 完整性与质量；写回 `ai_ready` 标志；判定失败时触发 DRAFTING 回退 |

**外部 API**：

| API | 用途 |
|---|---|
| 飞书 docx（section-level 幂等重写） | Requirement Doc 的 8 个 section 各自幂等更新，禁止全删重建 |
| 飞书 Bitable | REQ 状态字段写回（`onExit(FINAL_REVIEW)` 钩子驱动） |

#### §6.1.7 完成标准 & 失败回退

**完成标准**：

- `status == APPROVED`
- Requirement Dual Gate（D-REQ-1）双路全绿：`ai_ready = true` 且 `human_confirmed = true`
- Requirement Final Review（D-REQ-2）通过：正式审查卡片干系人确认

**失败回退**：

- D-REQ-1 任一路失败（AI 退回 或 人工打回）→ 状态回 `DRAFTING`；两路独立，不互相污染
- D-REQ-2 打回（正式审查未通过）→ 状态回 `DRAFTING`

**需求文档格式约束**：

- 8 个固定 section：问题描述 / 使用场景 / 输入 / 输出 / 边界 / 验收标准 / 非功能要求 / 技术范围声明
- 更新模式：section-level 幂等重写（禁止全删重建）
- 输入/输出字段规范：须到字段名 + 类型 + 约束粒度，不接受纯自然语言描述
- 验收标准格式：可测试断言（给定输入 → 期望输出 → 判断方式）

**UI 两阶段模型**（`needs_ui = true` 时）：

- **第一阶段（低保真线框）**：`onEnter(HUMAN_CONFIRM)` 时生成，辅助 author 判断 AI 是否理解需求方向
- **第二阶段（高保真可运行原型）**：归并至规划层 DesignStatus（详见 §6.2），在 REQ APPROVED 后、Spec 生成前独立执行；确认后设计决策 append 进项目设计系统文档

---

### §6.2 规划层（Planning Layer）

#### §6.2.1 使命

把「怎么做的决策」从规格层剥离，分两步完成：先由 `design-author` 在 IM 多轮交互中产出 UI/交互设计（`needs_ui = true` 时激活）；再由 `plan-author` 产出结构化 **Plan**（多决策 + 可选 **`project_context_change` 块**（本方法论独创，定义见附录 A）——`project_context_change` 是 plan.md 中承载项目级制品变更请求的信封字段，含 `changes[]` 数组与授权位）。规划层是 **Project-level Architecture Snapshot 演化的唯一主通道**——规格层只读消费架构，增量演化权限归属本层的 **Planning Approval Gate**（本方法论独创，定义见附录 A）授权闸门。构造期全程以飞书文档为 SOT，`PlanStatus → READY` 时单向同步至 GitHub（详见 §四）。

#### §6.2.2 输入

**A. 上下文（只读）**

| 条目 | 类型 | 说明 |
|---|---|---|
| Architecture Snapshot | Project-level Guide | 飞书 ARCHITECTURE docx（构造期 SOT）；判断是否需要 `project_context_change` 的基准 |
| Known Constraints | Project-level Invariant | 不可逾越约束清单 |
| Tech Stack | Project-level Guide | 技术选型约束 |
| Design System | Project-level Guide | UI 组件规范，`needs_ui = true` 时 design-author 参考 |
| Requirement Doc | REQ-level Guide | 8 字段结构化需求文档（§6.1 产出），只读 |
| Design Artifact | REQ-level Guide | 本 REQ 的 design 产物（archive 目录 + `github_revision` + pages 列表 + Brief doc URL）；`needs_ui=true` 且 `DesignStatus=READY` 时是 plan-author **决策识别的前提**，详见 §6.2.8 |

**B. 决策点（本层触发）**

| ID | 名称 | 类型 | 说明 |
|---|---|---|---|
| **D-PLAN-1** | **Planning Approval Gate**（同上，见附录 A） | 项目级上下文变更人工授权决策点 | 仅当 `plan.project_context_change != None` 时触发；授权人确认 before/after diff 后方可推进 `READY`；驳回则退回 `DRAFTING` |
| **D-PLAN-2** | **Plan Final Approval**（本方法论独创，定义见附录 A） | 人工定稿决策点 | plan-author 产出完整 plan 后推送定稿预览卡，干系人确认方可触发 `PLAN_SUBMIT`；驳回则继续 DRAFTING 多轮 |

#### §6.2.3 2×3 矩阵增量

| | Project-level | REQ-level |
|---|---|---|
| Guides | **amend**: Architecture Snapshot / AI Integration / External Integration（经 `project_context_change` 块授权后，`onEnter(PlanStatus.READY)` hook 原子同步） | **create**: Plan（结构化 Decisions）/ Design Artifact（`needs_ui = true` 时） |
| Sensors | N/A | N/A |
| Invariants | **amend**: Known Constraint（若 `project_context_change` 涉及约束变更） | N/A |

> **说明**：规划层是本方法论中**唯一允许修改 Project-level Guides 的构造期子层**。Project-level amend 须经 D-PLAN-1 Planning Approval Gate 授权，授权通过后由 `onEnter(PlanStatus.READY)` 钩子原子同步飞书 ARCHITECTURE 增量与 plan 到 GitHub 同一 commit；未涉及项目级变更时 `project_context_change == None`，PlanStatus 跳过 AUTH_PENDING 直达 READY。规划层 Sensors（偏离检测集）与 REQ-level Invariants 均无新增条目。

#### §6.2.4 状态机

**Parallel Sub-State Tracks**（本方法论独创，定义见附录 A）——三列状态（DesignStatus / PlanStatus / SpecStatus）在同一 REQ 内独立并行推进，列间由 Coordinator 前置条件检查阻塞，而非合并为单一状态机：

```
DesignStatus：null → DRAFTING → READY              （仅 needs_ui=true 时激活；DesignStatus 列独立推进，完成后作为 PlanStatus 启动前置条件，不在本层展开）
PlanStatus：  null → DRAFTING → [AUTH_PENDING →] READY
SpecStatus：  null → DRAFTING → TRANSFORMING → LOCKED
                     ↑ DesignStatus=READY 才进入   ↑ PlanStatus=READY 才进入
```

**PlanStatus 事件**：

| 事件 | 触发条件 | 状态转移 |
|---|---|---|
| `PLAN_START` | REQ APPROVED（`needs_ui=false`）或 DesignStatus=READY | null → DRAFTING |
| `PLAN_SUBMIT` | D-PLAN-2 定稿卡片干系人确认通过（plan-author 产出完整 plan 后推送） | DRAFTING → AUTH_PENDING（若 `project_context_change != None`）或直接 → READY |
| `PLAN_AUTHORIZE` | D-PLAN-1 人工授权通过 | AUTH_PENDING → READY |
| `PLAN_AUTHORIZATION_REJECT` | D-PLAN-1 人工驳回 | AUTH_PENDING → DRAFTING |
| `PLAN_RESTART` | `/plan restart` CLI 命令 | 任意 → null（级联 reset SpecStatus） |

`plan_phase` 字段（OUTLINE_PENDING / OUTLINE_CONFIRMED / DECISIONS_IN_PROGRESS / FINAL_REVIEW_PENDING / FINAL）是 DRAFTING 子状态的内部推进字段，由 plan-author 回调直接写入，**不走状态机 apply_event**。

#### §6.2.5 Hook 装配

| 事件 | Hook | 动作 |
|---|---|---|
| `onEnter(PlanStatus.DRAFTING)` | Coordinator Service | 派发 `plan-author`（OpenClaw Skill），在 author 私聊中启动骨架-深入-定稿三阶段 IM 交互 |
| `onEnter(PlanStatus.AUTH_PENDING)` | Coordinator Service | 向项目群推送 Planning Approval Gate 授权卡片（D-PLAN-1），展示 `project_context_change.changes[]` before/after diff；卡片按钮：**授权** / **驳回** |
| `onEnter(PlanStatus.READY)` | Checkpoint Handler | 原子同步：读取冻结飞书 plan docx → 渲染 `plans/<req_id>.md`；若 `project_context_change != None` 同时渲染更新后飞书 ARCHITECTURE docx → `docs/ARCHITECTURE.md`；二者共享同一 GitHub commit；任何一步失败抛 `ProjectRepoError(recoverable=True)`（Coordinator Service 内部可恢复错误类型；`recoverable=True` 表示人工可触发重试而非直接降级，见附录 A），退回 AUTH_PENDING 并推失败卡片 |
| `onExit(PlanStatus.READY)` | Coordinator Service | 解除 SpecStatus 前置锁：设置 `spec_precondition_met = true`，SpecStatus 进入 DRAFTING 可用 |

#### §6.2.6 能力层绑定

**OpenClaw Skill**：

| Skill | 触发时机 | 职责 |
|---|---|---|
| `plan-author` | `onEnter(PlanStatus.DRAFTING)` | 三阶段交互（骨架 → 深入 → 定稿）产出结构化 Plan；按 IM 交互实时写入飞书 plan docx；产出 `project_context_change` 块（若需架构演化） |
| `design-author` | `onEnter(DesignStatus.DRAFTING)`（`needs_ui=true`） | 多轮 IM 产出 UI/交互设计产物；落飞书 design 子目录；DesignStatus → READY 是 PlanStatus 启动的前置条件 |

> **实装状态**：`plan-author` 已实装；`design-author` 当前为 stub，待 claude design 能力落地后激活。

**外部 API**：

| API | 用途 |
|---|---|
| 飞书 docx（plan doc，per-REQ） | plan-author 三阶段实时写入；`onEnter(PlanStatus.READY)` hook 读取冻结版本渲染为 GitHub plan.md |
| 飞书 docx（ARCHITECTURE，Project-level） | 授权通过后 plan-author 按 `project_context_change.changes[]` 增量更新；`onEnter(PlanStatus.READY)` hook 读取冻结版同步到 GitHub |
| GitHub API | `onEnter(PlanStatus.READY)` hook 原子写入 `plans/<req_id>.md` + 可选 `docs/ARCHITECTURE.md`（同一 commit） |

#### §6.2.7 完成标准 & 失败回退

**完成标准**：

- `PlanStatus == READY`
- plan 飞书文档已冻结（内容固化，不再接受编辑）
- 若 `project_context_change != None`：D-PLAN-1 Planning Approval Gate 已通过（`authorized == true`，含授权人与时间）；飞书 ARCHITECTURE docx 已按 `changes[]` 增量更新；原子同步已完成（`plan_github_revision` + `architecture_github_revision` 均已写回审计字段）

**失败回退**：

- **Cascading Reset**（本方法论独创，定义见附录 A）——`/plan restart` → PlanStatus 重置为 null，**级联** SpecStatus → null；确认卡片列出将清理的下游产物
- `/design restart` → DesignStatus → null，**级联** PlanStatus → null，**级联** SpecStatus → null；确认卡片同上
- D-PLAN-1 驳回（`PLAN_AUTHORIZATION_REJECT`） → PlanStatus 退回 DRAFTING，`plan_phase = FINAL_REVIEW_PENDING`；plan-author 被重新拉起并带上驳回意见
- `onEnter(PlanStatus.READY)` 同步失败 → 钩子抛 `ProjectRepoError(recoverable=True)`，PlanStatus 退回 AUTH_PENDING，推送失败卡片让人决定重试 / 驳回 / restart

**Plan 文件格式**：YAML frontmatter + Decisions 正文（结构化多决策）+ 可选 `project_context_change` 块。完整 schema 见 `layers/planning-harness-layer.md §三`。

**三阶段交互模式**：骨架（OUTLINE）→ 深入（DECISIONS_IN_PROGRESS）→ 定稿（FINAL）。骨架阶段先对齐 decision 清单范围，避免直接写细节的浪费；深入阶段逐个 decision 多轮对话产出 alternatives + rationale；定稿阶段一次性产出完整 plan 供人 final approve（即 D-PLAN-2 Plan Final Approval）。

#### §6.2.8 Design → Plan 对齐契约

`needs_ui = true` 的 REQ 在进入规划层时，design 产物已在 §6.x（设计层）冻结至 GitHub。规划层**必须**把 design 产物作为决策识别与编排的输入，否则会出现**决策重复/冲突**（plan-author 提出设计师已经拍板的事，让人二次决策或造成永久漂移）与**决策遗漏**（真正需要 plan 级拍板的 UI-相关决策——数据源、路由、token→framework 映射——因为 plan-author 对 design 无感而从未被提出）。

**触发条件**：

- `needs_ui == true` AND `DesignStatus == READY`（未满足不触发本契约）

**Coordinator 义务（契约层）**：

Coordinator 在返回 plan-context 时，`design_artifact` 字段必须提供足以定位产物的指针，至少包含：

| 字段 | 含义 | 来源 |
|---|---|---|
| `archive_path` | 归档目录 repo-relative 路径 | `Requirement.design_archive_path` |
| `github_revision` | design 产物固化的具体 commit SHA（钉死版本） | `Requirement.design_github_revision` |
| `feishu_brief_url` | Design Brief 飞书文档 URL（人类阅读用） | `Requirement.design_doc_url` |
| `design_system_doc_url` | 项目级 Design System 飞书文档 URL | `ProjectConfig.design_system_doc_id` 渲染而来 |
| `pages` | 本 REQ 设计的页面清单（含 display_name 与 src_hint） | 从 archive 的 MANIFEST.md / PAGES.yaml 解析 |
| `design_status` | 冗余字段，便于 agent 幂等校验 | `Requirement.design_status` |

仅有 `archive_path` 不足以支撑 agent 行为——它需要知道**去哪个 commit 拉文件、哪些页面在这一轮里被设计、DS 在哪里**。

**plan-author 义务（技能层）**：

Phase A（骨架）开始前，若 `design_artifact.design_status == READY`，plan-author **必须**：

1. **读 archive**——至少读 `MANIFEST.md`（确认 pages_hint）与 `<archive_path>/extracted/*/src/*.jsx`（理解布局/交互意图）与 `<archive_path>/extracted/*/styles/tokens.css`（了解 token 约束），使用 `github_revision` 钉版本拉取
2. **读 Design System**——通过 `feishu_fetch_doc(design_system_doc_url)` 加载组件规范
3. **按下述规则识别决策**：
   - **design 已决定的事 → 不提**：layout、配色、排版、组件视觉、交互动效等设计师已拍板的事项不进入 plan outline。违反示例：❌"Dashboard 采用几列布局"（设计师已决，plan 不该回放）
   - **design 开放的事 → 必须提**：跨 design/plan 边界的决策必须在 plan outline 中覆盖，不得默认沉默。典型边界决策包括：
     - 页面数据源（mock / 真实 API / 混合）
     - 路由结构与导航策略
     - 前端框架 / 组件库选型（Vite+React / Next.js / shadcn/ui…）
     - token → framework 映射策略（tokens.css → Tailwind theme extend / CSS Variables / styled-components…）
     - 视觉参考 JSX 的"翻译口径"（按像素还原 / 按语义重搭 / 按组件库替换）

**追溯义务（产物层）**：

Plan-author 在 Phase C 组装 plan.md 时，YAML frontmatter **必须**声明：

```yaml
design_handoff_ref: "{archive_path}@{github_revision}"
```

这一行把 plan 与具体 design 冻结态绑定，后续实施期产物可通过 plan → design 链路追溯到原始视觉规范。缺失该字段的 `needs_ui=true` plan 视为 schema 违规，Coordinator 在 `plan_submit` 时校验并拒绝。

**Cascading Reset 语义扩展**：

`/design restart` 触发时级联清空 plan.md 中的 `design_handoff_ref`（连同 Plan/Spec 级联）；下一轮规划时 plan-author 按新的 design 冻结态重新建立 ref。

---

### §6.3 规格层（Spec Layer）

#### §6.3.1 使命

将「规划层已定决策」+「Requirement Doc」翻译为「让生成层能够自驱 coding 的 **Spec Artifacts**（本方法论独创，定义见附录 A）三元组」——即 `design.md`（Guides）/ `ac-schedule.yaml`（Sensors）/ `design.md` `supersedes` 节 + `acm-registry.yaml` patch（Invariants）。飞书 9 节 Spec（Stage 1）不是本层终端交付物，而是「人-AI 协作协议」；**Checkpoint 1a**（本方法论独创，定义见附录 A；即 D-SPEC-1 Design Gate，本层唯一人工决策点）通过后，Stage 2 的 Spec Artifacts 才是下游消费对象。规格层**不做决策**，只翻译决策——所有「怎么做」的决策由规划层（§6.2）的 Plan 承载，spec-author 的职责是引用 `decision_id` 并将其翻译为工程契约，而非重新推理。

> **关键架构说明**：v3.0 起规格层**不再演化 Architecture Snapshot**——演化主通道由规划层（§6.2）经 `project_context_change` 块 + Planning Approval Gate + `onEnter(PlanStatus.READY)` 钩子单向同步承担（见 §6.2.1 / §6.2.5）。规格层**只读消费** `docs/ARCHITECTURE.md`（实施期 GitHub SOT）。v2.6 的 `context_token + revision` 并发写回协议**整套退出**，由 §3.5 时相分段 Freeze Point 单向同步替代。

#### §6.3.2 输入

**A. 上下文（只读）**

| 条目 | 类型 | 说明 |
|---|---|---|
| Architecture Snapshot | Project-level Guide | 实施期只读：`docs/ARCHITECTURE.md`（GitHub SOT）；规格层不演化此制品，见 §6.3.1 关键架构说明 |
| ACM Registry | Project-level Invariant | `acm-registry.yaml`——全局 AC 注册表；Stage 2 读取 `acm_active_slice` 作为 Round 0 AC 认领基准 |
| Design System Snapshot | Project-level Guide | UI 组件规范快照；`needs_ui = true` 时 spec-author 参考 |
| Requirement Doc | REQ-level Guide | 8 字段结构化需求文档（§6.1 产出），只读 |
| Plan | REQ-level Guide | 构造期读飞书 Plan docx（Stage 1）；Stage 2 读 `plans/<req_id>.md`（GitHub SOT）；spec-author 以 `decision_id` 引用决策，不重新推理 |
| Design Artifact | REQ-level Guide | `needs_ui = true` 时由规划层 design-author 产出的高保真设计产物；SpecStatus 启动前置条件之一（见 §6.2.4） |

**B. 决策点（本层触发）**

| ID | 名称 | 类型 | 说明 |
|---|---|---|---|
| **D-SPEC-1** | **Checkpoint 1a · Design Gate** | 人工审查决策点（方案门） | 技术负责人在项目群卡片确认 9 节飞书 Spec 的设计方案、ACM 条目、`supersedes` 声明、架构接合点；通过 → 冻结飞书 Spec + 捕获 `spec_source_revision` + 进入 `SPEC_TRANSFORMING`；驳回 → `SPEC_REJECTED`（仅留档，不回退需求层） |

#### §6.3.3 2×3 矩阵增量

| | Project-level | REQ-level |
|---|---|---|
| Guides | N/A（**只读**消费，规格层不再演化 Architecture Snapshot，见 §6.3.1） | **create**: Spec Stage 1（飞书 9 节 Spec，构造期 SOT，Checkpoint 1a 冻结）→ Spec Artifacts（`design.md` / `tasks.md`，由 Spec Transformation Loop 产出） |
| Sensors | N/A | **create**: `ac-schedule.yaml`（本 REQ AC 排班，声明式 `expected` + harness 骨架组合构成可执行 Sensors） |
| Invariants | **amend**: ACM Registry（`acm-registry.yaml` patch，`SPEC_LOCKED` 时由 Coordinator 原子写入） | **create**: `design.md` `supersedes` 节（声明本 REQ 取代的历史 AC，防止生成层越界触碰既有契约） |

> **说明**：规格层在 Project-level 维度**仅修改 ACM Registry**（通过 Spec PR 原子 patch，不经 Planning Approval Gate）；Architecture Snapshot 演化权限属于规划层（§6.2），本层只读。Sensors（偏离检测集）仅在 REQ-level 新增 `ac-schedule.yaml`；Project-level Sensors 无新增条目。

#### §6.3.4 状态机（Spec 子状态机）

Spec 子状态机是需求层 6 态机的下挂子状态，仅在 `requirement.status == APPROVED` 时生效；与需求层正交，Spec 驳回或中止**不会**回写 `requirement.status`。三列 **Parallel Sub-State Tracks**（定义见附录 A；DesignStatus / PlanStatus / SpecStatus 同一 REQ 内独立并行推进）中，SpecStatus 须等待 `PlanStatus == READY` 才可从 null 进入 DRAFTING（见 §6.2.4）。

```
                 spec_start
      null ─────────────────────► SPEC_DRAFTING
       ▲                            │   ▲
       │                            │   │  ai_review_reject
       │                            │   └──────────────────── (留在 SPEC_DRAFTING)
       │                  ai_review_pass
       │                            ▼
       │                    （等待 Checkpoint 1a 卡片）
       │         checkpoint_1a_pass │     (捕获 spec_source_revision)
       │                            ▼
       │              SPEC_TRANSFORMING ◄───┐ transform_deadlock
       │                            │      │ （自循环：写人工工单，
       │                            │      │  不回退 SPEC_DRAFTING）
       │                            ├──────┘
       │                 transform_converged
       │                            ▼
       │                      SPEC_LOCKED ──► 进入 Harness 层（§7.1）
       │
       │         checkpoint_1a_reject / spec_abort
       └──────────────────── SPEC_REJECTED
                                 （仅作历史留档，不回退需求层状态；
                                  需人工决定是否重启 spec_start）
```

**`transform_deadlock`**（自循环事件）：当 **Spec Transformation Loop**（本方法论独创，定义见附录 A；指 `SPEC_TRANSFORMING` 内 spec-transformer → Computational gate → spec-transformer-reviewer 的多轮迭代机制）达到 `max_rounds` 上限仍未 converge 时触发；状态留在 `SPEC_TRANSFORMING` 自循环，并写入人工工单，不回退 `SPEC_DRAFTING`（Checkpoint 1a 已有人工决策，回退会使技术负责人的确认结论失效）。

**事件一览**：`spec_start` / `spec_submit` / `ai_review_pass` / `ai_review_reject` / `checkpoint_1a_pass` / `checkpoint_1a_reject` / `transform_converged` / `transform_deadlock` / `spec_abort` / `spec_restart`。

#### §6.3.5 Hook 装配

| 事件 | Hook | 动作 |
|---|---|---|
| `onEnter(SPEC_DRAFTING)` | Coordinator Service | 派发 `spec-author`（OpenClaw Skill）：创建飞书 9 节 Spec 文档、注入项目级上下文（Architecture Snapshot + ACM 切片 + 设计系统快照）、绑定 `req_id`，开始多轮 IM 撰写循环 |
| `onExit(SPEC_DRAFTING on ai_review_pass)` | Coordinator Service | 向项目群推送 Checkpoint 1a 卡片（D-SPEC-1），展示设计方案摘要、ACM 条目、`supersedes` 声明、架构接合点；按钮：**确认提交** / **返回修改** |
| `onEnter(SPEC_TRANSFORMING)` | Coordinator Service | 冻结飞书 Spec（捕获 `spec_source_revision`）→ 单向同步 9 节飞书文档至 `specs/<req_id>/spec.md`（GitHub）→ 捕获 `acm_active_slice` 作为 Round 0 基准 → 派发 `spec-transformer`（OpenClaw Skill）启动 Spec Transformation Loop |
| `onEnter(SPEC_LOCKED)` | Checkpoint Handler | 原子发布 Spec Artifacts PR（四文件 + `transform_trace.jsonl`，单次 Git Data API commit）→ patch `acm-registry.yaml` → 写回审计字段（`spec_pr_url` / `spec_source_revision` / `transform_trace_digest`）→ 触发 §7.1 Harness 层进入前置检查 |

#### §6.3.6 能力层绑定

**OpenClaw Skill**：

| Skill | 触发时机 | 阶段 | 职责 |
|---|---|---|---|
| `spec-author` | `onEnter(SPEC_DRAFTING)` | Stage 1 | 读飞书需求文档 + Plan + Architecture Snapshot + ACM 切片 → 以 `decision_id` 引用规划层决策 → 撰写飞书 9 节 Spec；幂等写回飞书 docx（section-level） |
| `spec-reviewer` | `onExit(SPEC_DRAFTING)` 内循环 | Stage 1 | 按 9 节质量清单审查（覆盖率 / API 入出参精度 / supersedes 依据 / AC 格式）；Inferential signal；`ai_review_pass` / `ai_review_reject` |
| `spec-transformer` | `onEnter(SPEC_TRANSFORMING)` | Stage 2 | Spec Transformation Loop 生成方：读 `specs/<req_id>/spec.md` + Plan + Architecture Snapshot → 产出四文件；每轮 payload 顶层附 `round_zero_ac_ids` 回显全部 AC |
| `spec-transformer-reviewer` | 每轮 Computational gate 通过后 | Stage 2 | Spec Transformation Loop 评审方：5 维度审查四文件质量；Inferential signal；`transform_converged` / `transform_deadlock`（达 `max_rounds`） |

> **凭据隔离**：所有 GitHub I/O 由 Coordinator Service 的 `GitHubGateway` 独占，Agent 只产文本；能力层替换零风险，凭据审计面收敛到单一进程。

**外部 API**：

| API | 用途 |
|---|---|
| 飞书 docx（9 节 Spec，per-REQ） | Stage 1：spec-author 幂等撰写；Checkpoint 1a 通过后冻结（只读） |
| GitHub API（Git Data API） | Stage 2：`onEnter(SPEC_LOCKED)` 单次原子 commit 发布 Spec Artifacts PR（四文件 + `transform_trace.jsonl`）+ `acm-registry.yaml` patch |

#### §6.3.7 完成标准 & 失败回退

**完成标准**：

- `SpecStatus == LOCKED`
- Spec Artifacts PR 已合入（`design.md` / `tasks.md` / `ac-schedule.yaml` / harness 骨架）
- `acm-registry.yaml` 已 patch（审计字段 `spec_pr_url` / `spec_source_revision` / `transform_trace_digest` 已写回）

**失败回退**：

- Stage 1 `ai_review_reject` → 留在 `SPEC_DRAFTING`，spec-author 迭代重写（人不感知）
- Checkpoint 1a reject（`checkpoint_1a_reject`）→ `SPEC_REJECTED`（仅留档，**不回退需求层**；`requirement.status` 保持 `APPROVED`）
- Stage 2 `max_rounds` 超限 → `transform_deadlock` 自循环 + 写人工工单（不回退 `SPEC_DRAFTING`；Checkpoint 1a 结论不失效）
- `/spec restart` → 重置 `SpecStatus` 为 null（**不级联上游** PlanStatus / `requirement.status`）

**四道工程闸门**（每道实现细节见 [`layers/spec-harness-layer.md §六`](layers/spec-harness-layer.md)）：

| 闸门 | 位置 | 性质 | 作用 |
|---|---|---|---|
| **Round 0 AC 认领** | Spec Transformation Loop 起点（首轮前置） | 机械 | spec-transformer 必须逐条回显全部 AC-K（`round_zero_ac_ids`），堵住"漏 AC" |
| **Computational gate** | 每轮 transformer → reviewer 之间 | 机械 | 预检 schema / tasks 正则 / supersedes / 路径一致性，节约 Inferential 预算 |
| **transform_trace** | Spec Transformation Loop 全程 | 可观测性 | 每轮事件写入 `transform_trace.jsonl`，支撑 deadlock 诊断与回溯；`SPEC_LOCKED` 时 `sha256[:12]` 摘要落审计字段 |
| **Regression scan** | `SPEC_LOCKED` 前 | 机械 | 扫描 `acm-registry` 有效 AC 是否全部被新骨架绑定，防止旧 AC 遗弃 |

**闸门哲学**：Inferential signals 只用于 spec-reviewer（Stage 1）+ spec-transformer-reviewer（Stage 2）；Computational signals 前置所有 schema / 正则 / 路径一致性 / 回归扫描；Human signal 只保留 Checkpoint 1a（D-SPEC-1）。

---

<!-- §七 及后续章节由 Task 9–12 填写 -->
