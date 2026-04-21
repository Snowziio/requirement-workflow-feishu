# Harness Engineering 方法论 v3.0 重构设计

> 本 spec 是方法论 v3.0 重写工作的 **设计蓝图（meta-spec）**。它描述：
> - v3.0 的章节骨架、写作规范、术语规范化表
> - v2.6 → v3.0 的迁移策略、衍生文档联动计划
> - v2.6 体系性矛盾的 v3.0 归结方式
>
> 本文不是 v3.0 方法论本身。v3.0 方法论的撰写是本 spec 的下游实施项（由 writing-plans 接续）。

---

## 一、背景与目标

### 1.1 问题陈述

当前方法论主文 `docs/context/harness-engineering-methodology-v2.0.md`（实际内容为 v2.6，2026-04-21 补丁后）经过多轮增量修订，已显露以下**体系性问题**：

1. **分类切面混乱**——同一事物被三至四套切面描述（"项目级上下文五层" / "三元组" / "冷热温" / "时相分段" / "五个契约问题"），彼此不正交
2. **北极星哲学叙事断裂**——§4.5 点出 "AI 自驱实施闭环为北极星"，但这条主线只贯穿规格层，其余层仍以"做了什么"为叙事主轴
3. **层数矛盾**——§三 "八层"、§2.2 "七层"、实际 9 层（含 Project 层）；卡点数同有"四/五/六"三种说法
4. **历史遗留与新模型并存**——§七 并发写回契约（context_token + revision）与 §4.5 时相分段模型同时存在，前者已被后者取代但未删除
5. **归属责任前后冲突**——ARCHITECTURE 的诞生时机、演化责任方在不同小节中给出了相互矛盾的声明
6. **术语与路径漂移**——`acceptance.yaml` / `ac-schedule.yaml`、`acm-registry.yaml` / `spec/registry/consolidated.yaml`、`ARCHITECTURE.yaml` / `ARCHITECTURE.md` 等多处混用
7. **下游五层契约稀薄**——Harness/生成/验证/集成/交付层仅有"目标+关键约束"，缺少统一的上下文契约描述
8. **"需求级上下文"概念缺位**——当前只显式化了"项目级上下文"，但 per-REQ 产物本质上构成"需求级上下文"这一半，未命名亦未设计

### 1.2 重构目标

产出方法论 v3.0，满足：

1. **北极星驱动**——以 "AI 自驱实施闭环（automated coding & delivery）" 为唯一终态，倒推上游每层的上下文贡献职责
2. **双主语言骨架**——"项目级 / 需求级上下文" × "约束 / 反馈 / 不变量（Invariants）" 组成 2×3 矩阵，贯穿每层
3. **三层分离制度化**——Workflow Service / Hook / 能力层的分离作为元原则，**构造期 / 实施期两套具象工作流模板**
4. **矛盾归零**——体系性矛盾一次性消除；局部字段名/路径矛盾在衍生文档对齐阶段处理
5. **术语规范化**——业界已有术语优先，本方法论独创内容才保留自造词；同一概念全文口径一致

### 1.3 不变项（与 v2.6 保持一致）

- 核心目标：让 AI 成为主要开发执行者，人只在关键决策点介入
- 五条设计哲学（规则化优先 / 约定优于协商 / 结构化产物驱动自动化 / 防漂移是基础设施问题 / 人工介入集中在判断）
- 适用范围声明（企业内部中小型应用，嵌入 IM 平台，功能交付为核心）
- REQ ID 全链路穿透
- 核心角色：Coordinator Service / Checkpoint Handler / OpenClaw

---

## 二、七项已锁定决策

本节记录 2026-04-21 brainstorm 过程中对齐的核心设计决策。**后续 v3.0 撰写以此为不可变前提。**

| 决策 # | 主题 | 锁定选项 |
|---|---|---|
| D1 | 主骨架语言 | **2×3 矩阵**：项目级/需求级 × 约束集/反馈集/Invariants（双主语言 C 方案） |
| D2 | 层结构 | **两段式**：Project 寿命层 + 需求寿命层 {构造期 / 实施期}（结构 B 方案） |
| D3 | 矩阵单元颗粒度 | **按条目类型 + artifact 列**；前置**上下文条目类型表**作为全方法论共用字典（颗粒度 B 方案） |
| D4 | 人类决策位置 | **每层独立"决策点清单"子章节**作为输入；决策结果落点字段连回 2×3 矩阵（决策 A 方案） |
| D5 | 纵向工作流模板 | **构造期 / 实施期两套模板**，共享三层分离元原则；不强求同一模板（模板 B 方案） |
| D6 | 叙事主骨架 | **独立顶层"终态倒推章"**（End-State Backward Derivation）一次讲透；后续各层前向展开（叙事 A 方案） |
| D7 | 操作策略 | v3.0 新文件 / 关键衍生文档同步 / 主文解体系性矛盾（见 §七、§八） |

---

## 三、写作规范（§序·Writing Discipline）

v3.0 §序 将内嵌以下写作规范，对全文所有章节强制生效：

1. **口径统一**：同一概念在 v3.0 全文**只使用唯一 canonical 名称**；替代说法退出正文，仅在附录 A 标注为 alias
2. **规范术语优先**：业界已有成熟表达的概念，使用业界术语；见 §五 术语规范化表
3. **必有定义**：任何关键术语在首次出现处必须给出定义（inline 或引用附录 A 条目）
4. **不造新词原则**：
   - **独创性内容**——本方法论特有设计（如"构造期/实施期 SOT 时相分段"、"项目级/需求级上下文二分"），必要时可保留自造术语，但必须在附录 A 显式标注 "本方法论独创"
   - **非独创内容**——禁止为已有业界概念另造新词；若 v2.6 存在自造词，v3.0 一律替换为业界术语
5. **引用规范**：引用业界文献（Fowler / Anthropic / OpenAI / Codified Context 等）时标注来源；引用本方法论内其他章节时使用 §X.Y 锚点

---

## 四、v3.0 章节骨架（锁定）

```
序 | 文档定位与阅读路径 + 写作规范（§三 本 meta-spec 内容内嵌）

§一 核心目标与设计哲学
  1.1 适用范围声明（沿用 v2.6 §1.0）
  1.2 核心目标（沿用 v2.6 §1.1，加北极星声明）
  1.3 五条设计哲学（沿用 v2.6 §1.2）
  1.4 业界对齐概述（合并 v2.6 §2.1 业界术语表）

§二 终态倒推（End-State Backward Derivation）【新·核心章节】
  2.1 终态定义：AI 自驱实施闭环的准入条件
  2.2 从终态倒推：实施期为何需要三元组（Guides / Sensors / Invariants）
  2.3 从三元组倒推：构造期为何需要"决策显式化 + 契约翻译 + 同步锚定"
  2.4 从构造期倒推：为何需要 Project 寿命层承载跨 REQ 共享约束
  2.5 倒推结论映射到 §三 条目类型表 + §四 层结构

§三 上下文条目类型表【新·共用字典】
  3.1 寿命二分：Project-level Context / REQ-level Context 定义
  3.2 三元组定义：Guides（约束集）/ Sensors（反馈集）/ Invariants（不变量）
  3.3 条目类型表（约 15–20 行）：类型名 / 寿命类别 / 三元组归属 / 构造期介质 / 实施期介质 / 生命周期动作 / 产出责任方
  3.4 2×3 矩阵总览（每层在此矩阵上画增量）
  3.5 时相分段约定（Construction-phase SOT / Implementation-phase SOT / Freeze Point）

§四 层结构与纵向工作流模板
  4.1 两段式层结构（Project 寿命层 / 需求寿命层{构造期 + 实施期}）
  4.2 三层分离元原则（Workflow Service / Hook / 能力层）
  4.3 构造期工作流模板（Coordinator Service + Agent）
  4.4 实施期工作流模板（GitHub Actions + Checkpoint Handler + CLI）
  4.5 人类决策点统一模板（触发 state / 载体 / 选项集 / 决策结果落点 / 失败路径）
  4.6 REQ ID 全链路穿透（沿用 v2.6 §4.3）
  4.7 卡片与 CLI 端点命名规范

§五 Project 寿命层
  5.0 Project 层（Bootstrap 7 步状态机 + 2×3 矩阵增量 + 决策点清单）

§六 需求寿命层·构造期
  6.1 需求层
  6.2 规划层
  6.3 规格层
  每节统一子节结构：
    ① 使命
    ② 输入（A. 消费的上下文条目 / B. 本层人类决策点）
    ③ 2×3 矩阵增量（Project-level × 3 + REQ-level × 3 共 6 个 cell）
    ④ 状态机（状态 + 事件 + 转移图）
    ⑤ Hook 装配（onEnter / onExit）
    ⑥ 能力层绑定（Agent + 外部 API）
    ⑦ 完成标准 & 失败回退

§七 需求寿命层·实施期
  7.1 Harness 层
  7.2 生成层
  7.3 验证层
  7.4 集成层
  7.5 交付层
  每节统一子节结构同 §六；能力层换为 CI / CLI

§八 横向基础设施
  8.1 人工协同轨（飞书 + OpenClaw）
  8.2 工程自动化轨（GitHub + CI）
  8.3 两轨协作接口
  8.4 人类决策点总览表（§五–§七 所有决策点统一编号 + 合并索引）

§九 实施路线图（沿用并更新 Phase 0–5 表）

附录 A | 术语表（A-Z 索引 + 独创标注 + alias 映射）
附录 B | v2.6 → v3.0 语义变更结论索引（不考古，只列结论）
附录 C | 衍生文档导航与对齐状态
```

### 4.1 与 v2.6 的主要差异

| 差异 | 说明 |
|---|---|
| §二 为全新章节 | 终态倒推一次讲透；v2.6 无对应 |
| §三 为全新章节 | 合并 v2.6 的"五层内容结构 / 三元组 / 冷热温 / 时相分段"四套切面 |
| §四 为升级章节 | v2.6 §4.1 的抽象原则升级为**两套可直接套用的工作流模板** |
| §五–§七 为重写章节 | 层结构两段式分组；每层 7 子节统一模板 |
| v2.6 §2（术语与产出物地图）被拆分 | 业界术语 → §一；产出物 → §三；跨层概念 → 附录 A |
| v2.6 §六（横向基础设施）成为 §八 | 排序下移，前置各层矩阵描述更集中 |
| **v2.6 §七并发写回契约整章删除** | 由 §三 时相分段约定替代；`context_token + revision` 协议在 ARCHITECTURE 场景下已失效 |

---

## 五、术语规范化表（v3.0 canonical）

### 5.1 业界已有对应，v2.6 自造词退役

| v2.6 用词 | v3.0 canonical | 业界依据 |
|---|---|---|
| 边界锚 | **Invariants（不变量）** | CS/工程通用术语 |
| 转化博弈 / SPEC_TRANSFORMING 循环 | **Spec Transformation Loop（规格翻译闭环）** | Anthropic Generator-Evaluator Loop |
| 前馈 / 反馈（Fowler 控制论语境外） | **输入约束 / 产出反馈** | — |
| 三产物列并行 | **Parallel Sub-State Tracks** | 业界并行子状态机术语 |
| 级联 restart | **Cascading Reset** | 业界通用 |
| 防漂移 | **Drift Prevention**（含 architectural / visual / functional drift 三类） | 业界 architectural drift 通用 |
| 架构授权闸门 / 规划授权 | **Planning Approval Gate** | 业界 HITL Approval Gate |
| 双闸门（AI Ready + Human Confirmed） | **Requirement Dual Gate** | — |
| 冷 / 温 / 热内存 | **Cold / Warm / Hot Context** | Codified Context 论文 |
| 博弈 | **Transformation Loop**（按上下文替换） | — |

### 5.2 本方法论独创，保留并定义

附录 A 必须显式标注 "本方法论独创术语 · Own Term"。

| 独创术语 | v3.0 canonical | 说明 |
|---|---|---|
| 项目级上下文 / 需求级上下文 | **Project-level Context / REQ-level Context** | 寿命二分是本方法论独有切面 |
| 构造期 SOT / 实施期 SOT | **Construction-phase SOT / Implementation-phase SOT** | 时相分段是本方法论独有设计 |
| Freeze Point | **Freeze Point** | 时相分段的同步触发点 |
| 北极星倒推 | §二 正式章节名为 **End-State Backward Derivation（终态倒推）**；"北极星" 仅作非正式称呼保留在哲学叙述 | — |

### 5.3 文件/路径口径统一

| 场景 | v3.0 规范 |
|---|---|
| AC 排班表文件名 | 统一 `ac-schedule.yaml`；`acceptance.yaml` 退出，标为 deprecated alias |
| AC 注册表路径 | 统一根级 `acm-registry.yaml`；`spec/registry/consolidated.yaml` 退出 |
| 架构文档（构造期） | 飞书 ARCHITECTURE 文档（`architecture_doc_id`） |
| 架构文档（实施期） | `docs/ARCHITECTURE.md`（md 格式；`ARCHITECTURE.yaml` 退出 GitHub 侧） |
| 规格层两阶段产物 | **Stage 1**：9 节飞书 Spec（`document_id`）；**Stage 2**：Spec Artifacts（`docs/specs/REQ-*/` 四文件） |
| Plan 文档 | 构造期：飞书 Plan docx（`plan_doc_id`）；实施期：`plans/<req_id>.md` |
| 9 节 Spec 同步到 GitHub | `specs/<req_id>/spec.md` |

### 5.4 角色与服务名

| 角色 | v3.0 canonical |
|---|---|
| Coordinator Service | **Coordinator Service**（需求 + 规划 + 规格层的 Workflow Service） |
| checkpoint-handler | **Checkpoint Handler**（Harness → 交付层的 Workflow Service） |
| OpenClaw Skill | **OpenClaw Skill（SKILL.md）** |
| AI Agent 命名 | `requirement-author` / `requirement-reviewer` / `plan-author` / `design-author` / `spec-author` / `spec-reviewer` / `spec-transformer` / `spec-transformer-reviewer` |

---

## 六、§二 终态倒推章 · 推理链草稿

> 本节是 §二 内容骨架；v3.0 撰写阶段在此基础上展开至约 800-1200 字叙事。

### 6.1 终态定义（§2.1）

AI 自驱实施闭环的准入条件（从 `SPEC_LOCKED` 进入之后，到部署上线之前）：

- 给 AI Coding Agent 的输入**足够完整、明确、机器可解析**
- 让 AI 无需人工介入即可完成：实现（implement）→ 对齐（align）→ 纠正（correct）的自修复循环
- 产出物经 CI 反馈 oracle 验证通过即可推进到下一阶段

### 6.2 从终态倒推：三元组（§2.2）

AI Coding Agent 的输入必须同时具备：

- **Guides（约束集，前馈）**——生成之前注入的设计契约：接口 / 数据模型 / 架构接合点（source: Fowler 控制论视角）
- **Sensors（反馈集，后馈）**——生成之后或过程中检测偏离的机制：AC oracle / 测试代码 / 视觉回归（source: Fowler）
- **Invariants（不变量）**——跨生成步骤保持不变的边界条件：历史 AC supersedes / 项目级硬约束（KC）/ 架构复用规定

任一缺失，AI 要么无根据猜测（缺 Guides）、要么无法自判成败（缺 Sensors）、要么越界触碰既有契约（缺 Invariants）。

### 6.3 从三元组倒推：构造期职责（§2.3）

三元组不会凭空出现，它们在**构造期**被人-AI 协同产生，并在 **freeze point** 固化后进入实施期只读消费。构造期的核心活动：

- **决策显式化**——规划层把"怎么做的决策"（选型 / 取舍）从 spec-author 剥离，由 plan-author 产出结构化 Plan
- **契约翻译**——规格层把 Decision + 需求 8 字段翻译为工程契约（Stage 1 的 9 节飞书 Spec → Stage 2 的 Spec Artifacts 四文件）
- **同步锚定**——`supersedes` / `decision_id` / `req_id` 等锚点在构造期建立，保证实施期可追溯

### 6.4 从构造期倒推：Project 寿命层（§2.4）

构造期需要跨 REQ 共享的**项目级约束**——架构骨架 / 技术栈 / IM 集成 / 项目级硬约束（KC）/ 设计系统 / CLAUDE.md——这些都不属于任何单个 REQ，而是项目生命周期内持续演化的资产。Project 寿命层（Bootstrap）承载它们的**首次创建**；后续演化通过 REQ 驱动（规划层 Planning Approval Gate）。

### 6.5 结论映射（§2.5）

倒推结果自然产出两张核心结构：

- **上下文条目类型表**（§三）：罗列三元组在项目级 / 需求级两个寿命维度下的所有具体条目类型
- **层结构 + 2×3 矩阵**（§四-§七）：每层声明其在 2×3 矩阵上的增量贡献

---

## 七、§三 上下文条目类型表 · 初稿

> 本节是 §三 的条目类型表首个草案。v3.0 撰写阶段补齐介质 / 生命周期动作 / 产出责任方字段。

### 7.1 条目类型表（初稿 · 17 条）

| 类型名 | 寿命类别 | 三元组归属 | 构造期介质 | 实施期介质 | 主产出责任方 |
|---|---|---|---|---|---|
| Tech Stack Declaration | Project-level | Guides | ProjectConfig（Coordinator） | ProjectConfig 只读 | Bootstrap |
| CLAUDE.md 行为规则 | Project-level | Guides | GitHub 仓库文件 | GitHub 仓库文件（热加载） | Bootstrap + 人工维护 |
| Architecture Snapshot（组件 / 接口 / 数据模型） | Project-level | Guides | 飞书 ARCHITECTURE docx | `docs/ARCHITECTURE.md` | 规划层（plan-author + Planning Approval Gate） |
| Known Constraint（KC） | Project-level | Invariants | 飞书 ARCHITECTURE docx · known_constraints 节 | `docs/ARCHITECTURE.md` 同节 | 规划层 / 人工 |
| AI Integration Registration | Project-level | Guides | 飞书 ARCHITECTURE docx · ai_integrations 节 | `docs/ARCHITECTURE.md` 同节 | 规划层 |
| External Integration（IM / 第三方 API） | Project-level | Guides | 飞书 ARCHITECTURE docx · external_integrations 节 | `docs/ARCHITECTURE.md` 同节 | Bootstrap + 规划层 |
| Design System（Token / 组件 / 交互模式） | Project-level | Guides | 飞书设计系统文档 | `specs/design-system-snapshot.yaml` | 设计层（UI 两阶段） |
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

**说明**：
- "寿命类别"：Project-level = 跨 REQ 共享；REQ-level = per-REQ 产物
- "三元组归属"：该条目在 AI 实施闭环中承担 Guides / Sensors / Invariants 中的哪一个（或复合角色）
- "构造期介质" / "实施期介质"：时相分段约定；构造期为空表示该条目在 AI 产出阶段才存在
- "主产出责任方"：负责条目首次产出/后续演化的层或角色

### 7.2 2×3 矩阵模板

每层在下述矩阵上画增量 cell：

```
                  │ Project-level        │ REQ-level
─────────────────┼──────────────────────┼──────────────────────
Guides（约束集）  │ [Cell: 本层新增/修改  │ [Cell: 本层新增/修改
                  │  的项目级约束条目]    │  的需求级约束条目]
─────────────────┼──────────────────────┼──────────────────────
Sensors（反馈集） │ [Cell: 本层新增/修改  │ [Cell: 本层新增/修改
                  │  的项目级反馈条目]    │  的需求级反馈条目]
─────────────────┼──────────────────────┼──────────────────────
Invariants        │ [Cell: 本层新增/修改  │ [Cell: 本层新增/修改
（不变量）         │  的项目级不变量条目]  │  的需求级不变量条目]
─────────────────┴──────────────────────┴──────────────────────
```

每个 cell 内列具体条目（从 §7.1 条目类型表选取）+ 动作（create / amend / freeze / reference / invalidate）。

### 7.3 时相分段约定（§3.5）

重述 v2.6 §4.5 内容（精简 + 术语规范化）：

- **Construction-phase SOT**：人类 + Agent 协同撰写、评审、固化；介质为飞书文档；可编辑直至 Freeze Point
- **Implementation-phase SOT**：AI 自驱只读消费；介质为 GitHub 仓库；Freeze 后不可变
- **Freeze Point**：由构造期状态机 hook 触发单向同步（飞书 → GitHub），不支持反向回流
- **受此约束的条目**：Architecture Snapshot（含 KC / AI Integration / External Integration 节）/ Plan / Spec Stage 1；Design System 在 Phase 2 启用后同步
- **不受此约束的条目**：Design Artifact、Spec Artifacts（Stage 2 四文件）、Harness、ACM Registry—— 这些只存在于实施期

---

## 八、§四 纵向工作流模板 · 两套形态

### 8.1 三层分离元原则（§4.2，沿用 v2.6 §4.1 核心）

| 层 | 职责 | 关键性质 |
|---|---|---|
| Workflow Service | 状态机定义、状态转移、hook 派发、状态持久化 | 纯规则、无 AI、无具体业务动作、项目无关 |
| Hook 实现 | 状态转移动作的具体实现（onEnter / onExit 回调） | 业务逻辑所在地，调用能力层，可独立测试 |
| 能力层 | AI Agent / 人工 / 外部 API 等可插拔能力 | 可替换、契约化、不持有状态 |

**三条不可违背性质**（沿用 v2.6）：
1. Workflow Service 不 import 任何能力层 SDK
2. 能力层替换零成本
3. 状态机与 Hook 实现可独立测试

### 8.2 构造期工作流模板（§4.3）

| 位置 | 具象 |
|---|---|
| Workflow Service | **Coordinator Service**（持有 Requirement 状态机 + DesignStatus / PlanStatus / SpecStatus 三列 parallel sub-state tracks） |
| Hook 触发介质 | `StateTransitionHooks.on_enter / on_exit` 注册点 |
| 能力层 | **OpenClaw Agent**（requirement-author / requirement-reviewer / plan-author / design-author / spec-author / spec-reviewer / spec-transformer / spec-transformer-reviewer） |
| 人类决策点载体 | **飞书消息卡片**（按钮回调至 Coordinator） |
| CLI 接入 | `/create project` / `/create req` / `/plan restart` / `/design restart` / `/spec restart` 等固化命令 |

**每层声明模板**：状态集 / 事件集 / 状态转移图 / Hook 清单（onEnter / onExit）/ Agent 契约 / 端点清单（GET 上下文 / POST callback / POST 卡片回调）。

### 8.3 实施期工作流模板（§4.4）

| 位置 | 具象 |
|---|---|
| Workflow Service | **Checkpoint Handler**（Harness / 生成 / 验证 / 集成 / 交付层的 GitHub PR / CI 回调接收方） |
| Hook 触发介质 | **GitHub Actions workflow**（`.github/workflows/*.yml`）+ Checkpoint Handler 内部状态转移 |
| 能力层 | **Claude Code CLI**（执行生成）+ **GitHub Actions 内置步骤**（CI / 部署脚本）+ **AI 失败分析脚本**（可选） |
| 人类决策点载体 | 飞书消息卡片（按钮回调至 Checkpoint Handler） |
| CLI 接入 | 主要通过 PR 分支 + commit 消息驱动，少量 `/harness restart` 之类 |

**每层声明模板**：输入产物集合 / CI workflow 触发条件 / 通过判定（Computational vs Inferential signal） / 人类决策点（如有）/ 失败路径。

### 8.4 人类决策点统一模板（§4.5）

每层"决策点清单"子章节按以下模板填写：

```
决策点 ID：[全局唯一编号，与 §8.4 总览表对齐]
名称：
触发 state：[状态机中哪个 state 的 onEnter 触发]
载体：[飞书卡片 / CLI 命令 / Bitable 表单]
决策选项集：[如 "通过 / 驳回"，或多选]
决策结果落点：[结果写入哪个条目 / 状态字段 / Bitable 字段]
失败路径：[驳回/重试/终止/级联重置 等]
判断权：[角色]
```

全部决策点在 §八.4 合并索引。

### 8.5 决策点总览表（§8.4）草案

| ID | 名称 | 所在层 | 触发 state | 判断权 |
|---|---|---|---|---|
| D-REQ-1 | Requirement Dual Gate（AI Ready + Human Confirmed） | 需求层 | `HUMAN_CONFIRM` | Author + 项目干系人 |
| D-REQ-2 | Requirement Final Review | 需求层 | `FINAL_REVIEW` | 技术负责人 |
| D-PLAN-1 | Planning Approval Gate（项目级上下文变更授权） | 规划层 | `PlanStatus.AUTH_PENDING` | 技术负责人 |
| D-PLAN-2 | Plan Final Approval | 规划层 | `plan_phase = FINAL_REVIEW_PENDING` | 技术负责人 |
| D-SPEC-1 | Checkpoint 1a · Design Gate（方案门） | 规格层 | Spec 子状态机 待卡点 1a | 技术负责人 |
| D-HARN-1 | Checkpoint 1b · Harness Gate（Harness 门） | Harness 层 | Harness 完成 CI | 技术负责人 |
| D-VAL-1 | Checkpoint 2 · Quality Gate（质量门） | 验证层 | Impl PR CI 全绿 | 技术负责人 |
| D-INT-1 | Checkpoint 3 · Release Gate（发布门） | 集成层 | Staging 就绪 | 产品 / 客户负责人 |

**说明**：v3.0 把"双门"显式列为 D-REQ-1（一个复合决策点，包含 AI Ready 自动判定 + Human Confirmed 人工判定两个子判断）；需求层 FINAL_REVIEW 作为独立的 D-REQ-2。卡点总数 **8 个决策点**，其中 Checkpoint 1a-3 为传统意义上的"人工卡点"。

---

## 九、v2.6 → v3.0 矛盾归结清单

> v3.0 主文**不做考古**，直接给结论；本节作为 meta-spec 的迁移映射表。

| v2.6 矛盾/模糊 | v3.0 归结 | 影响章节 |
|---|---|---|
| 层数矛盾（七 / 八 / 九） | **9 个子层**（1 Project + 3 构造期 + 5 实施期），三维框架图重绘 | §四 4.1 |
| 卡点数矛盾（四 / 五） | **8 个决策点**（D-REQ-1/2、D-PLAN-1/2、D-SPEC-1、D-HARN-1、D-VAL-1、D-INT-1）；传统"四卡点"特指 Checkpoint 1a/1b/2/3 | §8.4 |
| ARCHITECTURE 诞生时机冲突（首条 REQ / Bootstrap） | **Bootstrap 建飞书 SOT 骨架**（`CREATE_ARCHITECTURE_DOC` 步骤）；首份 GitHub 副本由首次 Plan READY 同步产出 | §五 + §六.2 |
| ARCHITECTURE 演化责任方冲突（spec-author / plan-author） | **规划层（plan-author + Planning Approval Gate）是唯一演化主通道**；规格层只读消费 | §六.2 + §六.3 |
| 分类切面混乱（五层 / 三元组 / 冷热温 / 五问） | **合成为 §三 条目类型表 + 2×3 矩阵**；冷热温降为条目注入策略属性；五问模板降为附录 C 衍生文档审查清单 | §三 |
| context_token + revision 并发写回协议 | **整章删除**；由时相分段（§3.5）替代；协议标记 deprecated | v3.0 无对应节；context-chain-principle.md 同步改写 |
| AC 文件名（`acceptance.yaml` / `ac-schedule.yaml`） | **统一 `ac-schedule.yaml`**；旧名退出 | §5.3 + §三条目类型表 |
| ACM 路径（`acm-registry.yaml` / `spec/registry/consolidated.yaml`） | **统一根级 `acm-registry.yaml`** | §5.3 + §三 |
| ARCHITECTURE 文件格式（yaml / md） | **统一 `docs/ARCHITECTURE.md`**（md 格式） | §5.3 + §三 |
| "需求级上下文"概念缺位 | **§三.1 显式引入 REQ-level Context 定义**；与 Project-level 并列为寿命二分 | §三 |
| 下游五层契约稀薄 | **§七 5 个子层均填 2×3 矩阵 + 决策点清单**；即使部分 cell 为空也显式标 "N/A" | §七 |
| 北极星哲学断裂 | **§二 独立章节一次倒推到底**；§五–§七 以矩阵增量方式承接 | §二 + §五–§七 |
| design-author 位置不清（规划层子阶段 vs 独立层） | **规划层内的 parallel sub-state track**（DesignStatus 与 PlanStatus 并行，needs_ui=true 时激活）；v3.0 明确 design-author 属于规划层能力层 | §六.2 |
| 术语自造词（边界锚 / 博弈 / 三产物列并行等） | 全部替换为业界规范术语（见 §五） | 全文 + 附录 A |

---

## 十、衍生文档联动计划

### 10.1 同步改写（v3.0 主文发布前必须改写）

| 文件 | 改写内容 |
|---|---|
| `docs/context/infra/context-chain-principle.md` | §一 五问模板：降为"设计文档审查清单"（非方法论主干）；§七 并发写回契约整章删除（由时相分段替代）；§八 Callback 唯一真相保留（仍适用）；全文术语对齐 |
| `docs/context/infra/project-context.md` | §一 更新责任方：`plan-author` 替代 `spec-author`；诞生时机：Bootstrap；§二 ACM 文件名统一 `ac-schedule.yaml`、路径统一 `acm-registry.yaml`；§三 设计系统格式保留；§五 事件驱动表重绘 |

### 10.2 加迁移标签（不立即改写）

| 文件 | 标签内容 |
|---|---|
| `docs/context/layers/requirement-layer.md` | 顶部 banner："本文反映 v2.x 模型；v3.0 对齐的章节请参见 [方法论 v3.0 §六.1]" |
| `docs/context/layers/planning-harness-layer.md` | 同上，指向 §六.2 |
| `docs/context/layers/spec-harness-layer.md` | 同上，指向 §六.3 |
| `docs/context/layers/generation-delivery-layers.md` | 同上，指向 §七 |
| `docs/superpowers/specs/2026-04-*.md`（各层设计 spec） | 保留不动，在各自 meta 头部加 "本 spec 对应 v2.x 层模型" 声明 |
| `docs/context/infra/harness-engineering-industry-alignment-2026-04-16.md` | 保留；v3.0 §一.4 从此文引用业界术语 |
| `docs/context/infra/state-machine-hook-pattern.md` | 保留；v3.0 §四.2 引用 |

### 10.3 归档

| 文件 | 动作 |
|---|---|
| `docs/context/harness-engineering-methodology-v2.0.md`（实际 v2.6） | 移入 `docs/archive/harness-engineering-methodology-v2.6.md` |
| `docs/archive/harness-engineering-methodology-v1.3.md` | 保留不动 |

### 10.4 不改动

- `docs/agents/*/SKILL.md`——跟随 issue/PR 逐步对齐（OpenClaw 仓库同步约束见 memory `reference_openclaw_skill_dual_sync.md`）
- `docs/superpowers/plans/*`——实施计划文档；对齐阶段按需更新

---

## 十一、交付清单

本 spec 批准后，v3.0 重构工作的交付物：

1. 新文件 `docs/context/harness-engineering-methodology-v3.0.md`（主文）
2. 改写 `docs/context/infra/context-chain-principle.md`（移除 §七、对齐术语）
3. 改写 `docs/context/infra/project-context.md`（对齐演化责任方 + 文件名/路径）
4. `docs/context/layers/*.md` 顶部加迁移 banner（共 4 个文件）
5. 移动 `docs/context/harness-engineering-methodology-v2.0.md` → `docs/archive/harness-engineering-methodology-v2.6.md`
6. 更新 `docs/context/layers/planning-harness-layer.md` 等交叉引用链接（指向 v3.0 锚点）

**不包含**：
- `docs/agents/*/SKILL.md` 对齐（延后）
- `docs/superpowers/specs/*` 对齐（延后）
- 代码变更（v3.0 是文档重构，不触发代码改动）
- `acm-registry.yaml` / `ARCHITECTURE.md` 等生产文件迁移（各项目自行对齐）

---

## 十二、未决项 / 延后决策

- **UI 两阶段模型的新位置**：v2.6 §5.1 末尾的"UI 两阶段"描述，在 v3.0 里应该归入规划层（design-author）还是独立一节？**暂定**：作为规划层 DesignStatus 子状态的内部流程，不独立成节。v3.0 撰写时若发现描述密度不足，可独立一小节。
- **acm-registry.yaml schema 演化**：v3.0 主文只描述 `acm-registry.yaml` 作为 Project-level Invariants 的定位；具体 schema 版本演化仍由 `project-context.md` 承载。
- **IM 平台泛化**：v2.6 多处混用"飞书"与"IM 平台"；v3.0 在涉及具体实现时用"飞书"，在涉及通用接口时用"IM 平台"。若未来接入企业微信/钉钉，本规范不变。
- **附录 C 衍生文档导航的维护责任**：v3.0 发布后如何保持附录 C 与实际文件状态一致？暂定：每次衍生文档迁移对齐时同步更新附录 C；不引入自动化脚本。

---

## 十三、后续动作（spec 批准后）

1. 本 spec 提交 commit
2. 用户 review 本 spec；通过后进入下一阶段
3. 以本 spec 为输入，invoke writing-plans skill 产出 v3.0 主文 + 同步衍生文档的实施计划
4. 按实施计划执行（分批提交 PR / commit）
5. v3.0 发布后本 spec 归档

---

*2026-04-21 | Methodology v3.0 Restructure Design | 基于 2026-04-21 brainstorm 对齐的 7 项决策 + 术语规范化清单*
