# Methodology v3.0 Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-04-21-methodology-v3-restructure-design.md`（下称 **meta-spec**）规定的 7 项决策，产出 Harness Engineering 方法论 v3.0 主文 + 两份关键衍生文档同步改写 + 4 份 layers 文档迁移 banner + v2.6 归档。

**Architecture:** 单分支顺序执行；不开 worktree（纯文档工作，影响面可控）。主文按章节增量撰写，分 4 次 commit；衍生文档每份独立 commit；迁移 banner + 归档各一 commit。术语与锚点一致性作为每阶段收尾的必过闸门。

**Tech Stack:** Markdown；字段引用飞书 docx / GitHub 路径；无构建/测试管道；验证手段=`grep` + 目录/锚点 spot-check。

**关键输入文件**：
- `docs/superpowers/specs/2026-04-21-methodology-v3-restructure-design.md`（meta-spec，本 plan 全程参照）
- `docs/context/harness-engineering-methodology-v2.0.md`（v2.6 实际内容，v3.0 的内容原料源）
- `docs/context/layers/*.md`（4 份细节文档）
- `docs/context/infra/context-chain-principle.md`、`docs/context/infra/project-context.md`（2 份关键衍生文档）

**写作规范（全 plan 硬约束）**：
1. 术语 canonical 来自 meta-spec §五；禁止使用退役词（边界锚 / 博弈 / 前馈/反馈等）
2. 同一概念全文口径一致
3. 首次出现的关键术语必有内联定义或附录 A 引用
4. 不造新词（独创概念除外，须标 "本方法论独创"）
5. 锚点命名 `§N.M` 与 `#NM-标题` 保持一致；交叉引用不能引向已删除章节

---

## File Structure

v3.0 主文件：`docs/context/harness-engineering-methodology-v3.0.md`（新建）

章节—任务映射（12 个 Task 产出主文）：

| 章节 | Task | 字数目标 |
|---|---|---|
| 序 + §一 核心目标与设计哲学 | Task 1 | ~600 |
| §二 终态倒推章 | Task 2 | ~1000 |
| §三 条目类型表 + 2×3 矩阵 + 时相分段 | Task 3 | ~900 |
| §四 层结构 + 两套工作流模板 + 决策点模板 + REQ ID | Task 4 | ~900 |
| §五 Project 寿命层 | Task 5 | ~500 |
| §六.1 需求层 | Task 6 | ~500 |
| §六.2 规划层 | Task 7 | ~700 |
| §六.3 规格层 | Task 8 | ~900 |
| §七.1 Harness 层 | Task 9 | ~400 |
| §七.2-7.4 生成/验证/集成层 + §七.5 交付层 | Task 10 | ~600 |
| §八 横向基础设施 + §九 实施路线图 | Task 11 | ~600 |
| 附录 A/B/C + 全文审查 | Task 12 | ~500 |

衍生文档：
- `docs/context/infra/context-chain-principle.md`（Task 13 · 改写）
- `docs/context/infra/project-context.md`（Task 14 · 改写）
- `docs/context/layers/requirement-layer.md`（Task 15 · 顶部 banner）
- `docs/context/layers/planning-harness-layer.md`（Task 15 · 顶部 banner）
- `docs/context/layers/spec-harness-layer.md`（Task 15 · 顶部 banner）
- `docs/context/layers/generation-delivery-layers.md`（Task 15 · 顶部 banner）

归档与交叉引用：
- `docs/context/harness-engineering-methodology-v2.0.md` → `docs/archive/harness-engineering-methodology-v2.6.md`（Task 16）
- v2.0 文件名在 4 份 layers 文档中作为 `../harness-engineering-methodology-v2.0.md` 被引用 → 迁移 banner 时一并指向 v3.0（Task 15 内完成）

**提交节奏**：
- Commit 1：Tasks 1-4 结构骨架 + 条目类型字典 + 工作流模板（"骨架 commit"）
- Commit 2：Tasks 5-8 Project + 构造期 3 子层（"构造期 commit"）
- Commit 3：Tasks 9-10 实施期 5 子层（"实施期 commit"）
- Commit 4：Tasks 11-12 基础设施 + 路线图 + 附录 + 审查（"主文完工 commit"）
- Commit 5：Task 13 context-chain-principle 改写
- Commit 6：Task 14 project-context 改写
- Commit 7：Task 15 layers banner + 交叉引用更新
- Commit 8：Task 16 v2.6 归档

---

## Task 1: 序 + §一 核心目标与设计哲学

**Files:**
- Create: `docs/context/harness-engineering-methodology-v3.0.md`

- [ ] **Step 1: 写入文件头 + 序章**

内容：
- 标题行 `# Harness Engineering 全自动开发工作流：方法论 v3.0`
- 版本注 `> v3.0 | 2026-04-XX | 完整重构：双主语言 + 终态倒推 + 两段式层结构`
- 序章内容（~200 字）：
  - 引述 meta-spec §1.1-1.2 的重构目标
  - 明确 v3.0 与 v2.6 的关系：v3.0 是彻底重写，v2.6 归档至 archive；本文为唯一权威
  - 阅读路径提示（先读 §二 终态倒推，再读 §三 条目类型表，其余可按需跳读）
- **序·写作规范**子节（meta-spec §三 5 条规范精简叙述，~150 字）：术语统一 / 业界优先 / 首次必定义 / 不造新词 / 引用规范

- [ ] **Step 2: 写入 §一 核心目标与设计哲学**

对应 meta-spec §1.3 "不变项"：

- §1.1 适用范围声明 —— 原样搬运 v2.6 §1.0（含技术形态 / 价值交付节奏 / 企业集成 / AI 能力 / 团队规模 / 用户规模 / 需求迭代频率 / 代码库规模 8 个维度表 + 范围内/超出范围产品形态说明）
- §1.2 核心目标 —— 原样搬运 v2.6 §1.1（4 点目标），末尾**加一句**："方法论 v3.0 明确以 **AI 自驱实施闭环** 为终态北极星，上游层的一切产出职责由此倒推得出，详见 §二。"
- §1.3 五条设计哲学 —— 原样搬运 v2.6 §1.2（规则化优先 / 约定优于协商 / 结构化产物驱动自动化 / 防漂移是基础设施问题 / 人工介入集中在判断）
- §1.4 业界对齐概述 —— 搬运 v2.6 §2.1 "业界术语对齐" 表；对齐术语规范化 meta-spec §5.1（如"三元组 = Guides / Sensors / Invariants"；"博弈 = Generator-Evaluator Loop"）

- [ ] **Step 3: 验证 Step 1-2 无退役词**

Run：
```bash
grep -n -E "边界锚|博弈|前馈|反馈" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 无命中，或仅出现在 Fowler 控制论术语对齐的**业界原词**位置

- [ ] **Step 4: 不 commit**（并入 Task 4 末尾一起提交）

---

## Task 2: §二 终态倒推章（End-State Backward Derivation）

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §二）

Content source：meta-spec §六 推理链草稿（4 步 + 结论映射）。

- [ ] **Step 1: 写入 §二 章节首段**

开场（~100 字）：明确本章回答"为什么 v3.0 的层结构 / 条目表 / 矩阵是这个样子"；声明本章是 v3.0 所有后续章节的理论推导源。

- [ ] **Step 2: 写入 §2.1 终态定义**

~150 字。对应 meta-spec §6.1：
- AI 自驱实施闭环的准入条件（`SPEC_LOCKED` 之后）
- 三要素：完整机器可解析输入 / 自修复 implement→align→correct 循环 / CI oracle 推进

- [ ] **Step 3: 写入 §2.2 从终态倒推三元组**

~300 字。对应 meta-spec §6.2：
- Guides（前馈约束，Fowler 术语）——接口契约 / 数据模型 / 架构接合点
- Sensors（后馈反馈，Fowler 术语）——AC oracle / 测试代码 / 视觉回归
- Invariants（不变量）——历史 AC supersedes / 项目级硬约束（KC）/ 架构复用规定
- 论证每一项缺失的后果（无根据猜测 / 无法自判 / 越界触碰）

- [ ] **Step 4: 写入 §2.3 从三元组倒推构造期**

~250 字。对应 meta-spec §6.3：
- 三元组不会凭空出现，在构造期被人-AI 协同产生
- 构造期三项核心活动：决策显式化 / 契约翻译 / 同步锚定
- Freeze Point 作为时相切换点

- [ ] **Step 5: 写入 §2.4 从构造期倒推 Project 层**

~150 字。对应 meta-spec §6.4：
- 构造期需跨 REQ 共享项目级约束
- Bootstrap 承载首次创建
- 后续演化通过 REQ 驱动（Planning Approval Gate）

- [ ] **Step 6: 写入 §2.5 结论映射**

~100 字。对应 meta-spec §6.5：
- 倒推结果产出两张核心结构：条目类型表（§三）+ 层结构矩阵（§四-§七）
- 引导读者进入 §三

- [ ] **Step 7: 锚点验证**

Run：
```bash
grep -n "§三\|§四" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 所有引用 §三/§四 的位置都指向本文件后续将创建的章节

- [ ] **Step 8: 不 commit**（并入 Task 4 末尾一起提交）

---

## Task 3: §三 上下文条目类型表 + 2×3 矩阵 + 时相分段

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §三）

Content source：meta-spec §七（条目类型表 17 行 + 2×3 矩阵模板 + 时相分段约定）。

- [ ] **Step 1: 写入 §3.1 寿命二分定义**

~150 字：
- **Project-level Context**：跨 REQ 共享；项目生命周期内存续；由 Project 寿命层与后续 REQ 驱动演化的条目构成
- **REQ-level Context**：per-REQ 存续；随 REQ 创建而生、交付闭环完成后不再演化
- 标注二分是本方法论独创切面

- [ ] **Step 2: 写入 §3.2 三元组定义**

~200 字：
- **Guides（约束集 · 前馈）**——Fowler 术语；生成之前注入的约束
- **Sensors（反馈集 · 后馈）**——Fowler 术语；生成之中或之后检测偏离
- **Invariants（不变量）**——跨生成步骤保持不变的边界条件；CS/工程通用术语
- 说明三元组是 AI 自驱闭环的必要充分条件（缺一不可）

- [ ] **Step 3: 写入 §3.3 条目类型表**

照搬 meta-spec §7.1 的 17 行表格，字段列：`类型名 / 寿命类别 / 三元组归属 / 构造期介质 / 实施期介质 / 主产出责任方`。

表下方添加字段语义说明（meta-spec §7.1 末尾 4 行说明）。

- [ ] **Step 4: 写入 §3.4 2×3 矩阵总览**

~200 字 + ASCII 矩阵图：
- 矩阵定义（2 列：Project-level / REQ-level；3 行：Guides / Sensors / Invariants；共 6 个 cell）
- 每个 cell 的填写规范：从 §3.3 条目类型表选取条目 + 动作（create / amend / freeze / reference / invalidate）
- 搬运 meta-spec §7.2 的 ASCII 矩阵图
- 声明后续 §五-§七 每层都将填写此矩阵

- [ ] **Step 5: 写入 §3.5 时相分段约定**

~250 字。对应 meta-spec §7.3：
- Construction-phase SOT / Implementation-phase SOT / Freeze Point 三概念定义（本方法论独创，标注）
- 受时相分段约束的条目清单
- 不受约束的条目清单（设计 Artifact / Spec Artifacts Stage 2 / Harness / ACM Registry）
- 关键原则：单一时相单一 SOT；单向同步；Freeze 不可变；渲染契约保 AI 可解析

- [ ] **Step 6: 验证表格内容自洽**

Run：
```bash
grep -n -c "Project-level\|REQ-level" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 条目类型表 17 行中每行恰好在 `Project-level` 或 `REQ-level` 中出现 1 次

- [ ] **Step 7: 不 commit**（并入 Task 4 末尾）

---

## Task 4: §四 层结构 + 两套纵向工作流模板 + 决策点统一模板 + REQ ID

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §四 + Commit 1）

Content source：meta-spec §八 两套工作流模板 + 人类决策点统一模板。

- [ ] **Step 1: 写入 §4.1 两段式层结构总览**

~200 字 + 架构图：
- 寿命二分：Project 寿命层（一次性 Bootstrap）+ 需求寿命层（per-REQ 全链路）
- 需求寿命层内部两段：构造期（需求/规划/规格 3 子层）+ 实施期（Harness/生成/验证/集成/交付 5 子层）
- 合计：1 + 3 + 5 = **9 个子层**
- ASCII 架构图（基于 v2.6 §三 重绘，横向保持"人工协同轨 / 工程自动化轨"不变，纵向改为两段式分组）
- 核心声明：全部 9 个子层**都必须**按 §3.4 矩阵填写增量 cell；部分 cell 可为 N/A

- [ ] **Step 2: 写入 §4.2 三层分离元原则**

照搬 meta-spec §8.1 内容（沿用 v2.6 §4.1 核心）：
- 表格：Workflow Service / Hook 实现 / 能力层 三层职责
- 三条不可违背性质

末尾加一句："本元原则在构造期与实施期以不同形态实例化，分别见 §4.3 / §4.4。"

- [ ] **Step 3: 写入 §4.3 构造期工作流模板**

对应 meta-spec §8.2。内容：
- 具象化表格：Workflow Service = Coordinator Service；Hook = `StateTransitionHooks`；能力层 = OpenClaw Agent；决策载体 = 飞书卡片；CLI = `/create project` 等
- 每层声明模板清单（状态集 / 事件集 / 转移图 / onEnter/onExit Hook / Agent 契约 / 端点清单）
- 引导读者：本模板在 §六 需求/规划/规格层统一套用

- [ ] **Step 4: 写入 §4.4 实施期工作流模板**

对应 meta-spec §8.3。内容：
- 具象化表格：Workflow Service = Checkpoint Handler；Hook 触发介质 = GitHub Actions workflow + Checkpoint Handler 内部转移；能力层 = Claude Code CLI + CI + AI 失败分析脚本
- 每层声明模板清单（输入产物 / workflow 触发条件 / 通过判定 Computational vs Inferential / 人类决策点 / 失败路径）
- 引导读者：本模板在 §七 Harness/生成/验证/集成/交付层统一套用

- [ ] **Step 5: 写入 §4.5 人类决策点统一模板**

对应 meta-spec §8.4。直接贴模板（决策点 ID / 名称 / 触发 state / 载体 / 选项集 / 落点 / 失败路径 / 判断权），末尾声明：全部决策点在 §八.4 合并索引。

- [ ] **Step 6: 写入 §4.6 REQ ID 全链路穿透**

照搬 v2.6 §4.3 表格（REQ-{PROJECT}-{NNN} 在 8 类工件中的出现位置）。

- [ ] **Step 7: 写入 §4.7 卡片与 CLI 端点命名规范**

~150 字：
- 端点路径命名：`/queries/openclaw/<layer>-context`、`/openclaw/<agent>-callback`、`/cards/<action>-<subject>`
- CLI 命名：`/create <resource>`、`/<status-column> restart <req>`
- 规范目的：让 Agent 能从端点名推知用途

- [ ] **Step 8: 术语一致性扫描（主文当前已写 §序–§四）**

Run：
```bash
grep -n -E "边界锚|转化博弈|前馈|反馈集" docs/context/harness-engineering-methodology-v3.0.md | grep -v "Sensors\|Guides\|Fowler\|非正式"
```
Expected: 无命中（若有 "反馈集" 作为 Sensors 的中文说明则允许，需与 "Sensors（反馈集）" 配对出现）

Run：
```bash
grep -n "九层\|七层" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 无命中（v3.0 用 "9 个子层"）

- [ ] **Step 9: Commit 1（骨架 commit）**

```bash
git add docs/context/harness-engineering-methodology-v3.0.md
git commit -m "$(cat <<'EOF'
docs(methodology): v3.0 skeleton — purpose, backward derivation, type table, layer templates

Sections §序–§四:
- Writing discipline inlined in §序
- End-state backward derivation as dedicated §二
- Unified context item type table + 2x3 matrix + time-phased SOT in §三
- Two-layer structure with construction/implementation workflow templates in §四

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: §五 Project 寿命层

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §五）

Content source：v2.6 §5.0 Project 层描述 + meta-spec §六层规范模板。

- [ ] **Step 1: 写入 §五 章节框架**

按 §六/§七 子层统一模板（7 小节）：
1. 使命
2. 输入（A. 上下文 / B. 决策点）
3. 2×3 矩阵增量
4. 状态机（states + events + 转移图）
5. Hook 装配（onEnter / onExit 列表）
6. 能力层绑定（Agent + 外部 API）
7. 完成标准 & 失败回退

- [ ] **Step 2: 填 §5.1 使命**

~80 字。使命：项目生命周期的首次创建；为后续 REQ 准备 Project-level Guides 与 Invariants 的初始骨架。

- [ ] **Step 3: 填 §5.2 输入**

**A. 上下文输入**：无（Project 层是起点）
**B. 人类决策点**：
- `/create project <slug>` CLI 命令触发（人类启动）
- 项目元数据录入（名称、技术栈分类、归属组）

- [ ] **Step 4: 填 §5.3 2×3 矩阵增量（Project 层产出）**

| | Project-level | REQ-level |
|---|---|---|
| Guides | **create**: Tech Stack Declaration / CLAUDE.md / Architecture Snapshot 骨架 / External Integration（IM 平台集成） | N/A |
| Sensors | N/A | N/A |
| Invariants | **create**: Known Constraint 初始集（若类目模板预置） | N/A |

- [ ] **Step 5: 填 §5.4 状态机**

搬运 v2.6 §5.0 状态机：
- 状态：`UNBOOTSTRAPPED → BOOTSTRAPPING → PROVISIONED → ARCHIVED → DECOMMISSIONED`
- MVP 只实现前三态
- Bootstrap 7 步（每步幂等，`--resume` 可续跑）

- [ ] **Step 6: 填 §5.5 Hook 装配**

列出 7 步对应的 hook 绑定（参考 v2.6 或 `2026-04-20-project-layer-design.md`）。

- [ ] **Step 7: 填 §5.6 能力层绑定**

Coordinator Service + Feishu API（建 docx / 建群）+ GitHub API（从 Template 仓库创建 repo）。

- [ ] **Step 8: 填 §5.7 完成标准 & 失败回退**

- 完成：`bootstrap_status == PROVISIONED`；`project_configs` 行已写；ARCHITECTURE 飞书 docx 已建（空骨架）；首份 GitHub repo 已建；飞书群已建
- 失败回退：任一步失败 → 保留已完成步骤 state，等人修复后 `--resume`
- **演化说明**：后续 Project-level 条目的演化由规划层 Planning Approval Gate 驱动，详见 §6.2

- [ ] **Step 9: 不 commit**（并入 Task 8 末尾）

---

## Task 6: §六.1 需求层

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §六.1）

Content source：v2.6 §5.1 + meta-spec §六层模板。

- [ ] **Step 1: 章节头**

`### 6.1 需求层（Requirement Layer）`

- [ ] **Step 2: 填 §6.1.1 使命**

~80 字：把模糊客户需求转化为经双门确认的结构化 **Requirement Doc**（8 字段，REQ-level Guides 起点）。

- [ ] **Step 3: 填 §6.1.2 输入**

**A. 上下文**：Project-level 全集（只读：Tech Stack / Architecture Snapshot / Known Constraints / Design System）
**B. 决策点**：
- **D-REQ-1 Requirement Dual Gate**（AI Ready + Human Confirmed，复合决策点）
- **D-REQ-2 Requirement Final Review**

- [ ] **Step 4: 填 §6.1.3 2×3 矩阵增量**

| | Project-level | REQ-level |
|---|---|---|
| Guides | N/A | **create**: Requirement Doc（8 字段） |
| Sensors | N/A | N/A |
| Invariants | N/A | N/A |

- [ ] **Step 5: 填 §6.1.4 状态机**

搬运 v2.6 §5.1 的 6 态机（`CREATED → DRAFTING → AI_REVIEW → HUMAN_CONFIRM → FINAL_REVIEW → APPROVED`）+ 失败回退箭头。术语规范化：双闸门 → **Requirement Dual Gate**。

- [ ] **Step 6: 填 §6.1.5 Hook 装配**

onEnter(DRAFTING) → 派发 requirement-author；onEnter(AI_REVIEW) → 派发 requirement-reviewer；onEnter(FINAL_REVIEW) → 推正式审查卡片；onExit(FINAL_REVIEW) → Bitable 状态写回。

- [ ] **Step 7: 填 §6.1.6 能力层绑定**

OpenClaw Skill：`requirement-author` / `requirement-reviewer`
外部 API：飞书 docx（section-level 幂等重写）+ Bitable

- [ ] **Step 8: 填 §6.1.7 完成标准 & 失败回退**

- 完成：`status == APPROVED`；Requirement Dual Gate 双路全绿；FINAL_REVIEW 通过
- 失败：双门任一路失败回 DRAFTING；FINAL_REVIEW 打回回 DRAFTING
- 需求文档格式：8 section + section-level 幂等重写；输入/输出字段名+类型+约束粒度；验收标准为可测试断言
- UI 两阶段模型：`needs_ui=true` 时，第一阶段（低保真线框）在 `onEnter(HUMAN_CONFIRM)` 触发；第二阶段（高保真可运行原型）归并至规划层 DesignStatus（见 §6.2）

- [ ] **Step 9: 不 commit**

---

## Task 7: §六.2 规划层

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §六.2）

Content source：v2.6 §5.2 + `docs/context/layers/planning-harness-layer.md` + meta-spec §六层模板。

- [ ] **Step 1: 章节头**

`### 6.2 规划层（Planning Layer）`

- [ ] **Step 2: 填 §6.2.1 使命**

~100 字：把"怎么做的决策"从规格层剥离；分两步—先 design-author 产出 UI/交互设计（needs_ui=true 时），再 plan-author 产出结构化 **Plan**（多决策 + 可选 project_context_change 块）。规划层是 **Project-level Architecture Snapshot 演化的唯一主通道**。

- [ ] **Step 3: 填 §6.2.2 输入**

**A. 上下文**：
- Project-level：Architecture Snapshot / Known Constraints / Tech Stack / Design System（全集，只读）
- REQ-level：Requirement Doc（8 字段，只读）
**B. 决策点**：
- **D-PLAN-1 Planning Approval Gate**（项目级上下文变更授权）
- **D-PLAN-2 Plan Final Approval**

- [ ] **Step 4: 填 §6.2.3 2×3 矩阵增量**

| | Project-level | REQ-level |
|---|---|---|
| Guides | **amend**: Architecture Snapshot / AI Integration / External Integration（`project_context_change` 块授权后原子同步） | **create**: Plan（Decisions）/ Design Artifact（needs_ui=true 时） |
| Sensors | N/A | N/A |
| Invariants | **amend**: Known Constraint（若 project_context_change 涉及） | N/A |

- [ ] **Step 5: 填 §6.2.4 状态机（三列并行 · Parallel Sub-State Tracks）**

```
DesignStatus：null → DRAFTING → READY              （仅 needs_ui=true 时激活）
PlanStatus：  null → DRAFTING → [AUTH_PENDING →] READY
SpecStatus：  null → DRAFTING → TRANSFORMING → LOCKED
```
Events：`PLAN_START / PLAN_SUBMIT / PLAN_AUTHORIZE / PLAN_AUTHORIZATION_REJECT / PLAN_RESTART`；对应 Design 列。
`plan_phase`：OUTLINE_PENDING / OUTLINE_CONFIRMED / DECISIONS_IN_PROGRESS / FINAL_REVIEW_PENDING / FINAL（DRAFTING 子状态字段，非状态机事件）。

- [ ] **Step 6: 填 §6.2.5 Hook 装配**

列出：
- onEnter(PlanStatus.DRAFTING) → 派发 plan-author
- onEnter(PlanStatus.AUTH_PENDING) → 推 Planning Approval Gate 卡片
- onEnter(PlanStatus.READY) → 原子同步 Plan + 可选 Architecture Snapshot 至 GitHub（飞书 → GitHub 单向同步）
- onExit(PlanStatus.READY) → 解除 SpecStatus 前置锁

- [ ] **Step 7: 填 §6.2.6 能力层绑定**

OpenClaw Skill：`plan-author`（已实装）/ `design-author`（stub，等 claude design 能力落地）
外部 API：飞书 docx（Plan + ARCHITECTURE 读写）+ GitHub API（READY hook 同步）

- [ ] **Step 8: 填 §6.2.7 完成标准 & 失败回退**

- 完成：`PlanStatus == READY`；Plan 飞书文档冻结；若 `project_context_change != None` 则授权已通过 + 原子同步完成
- 失败：
  - `/plan restart` → Cascading Reset（同时 reset SpecStatus）
  - `/design restart` → Cascading Reset（同时 reset PlanStatus + SpecStatus）
  - AUTH_PENDING 驳回 → 退回 DRAFTING，`plan_phase = FINAL_REVIEW_PENDING`
  - 同步失败 → 钩子抛 `ProjectRepoError`，退回 AUTH_PENDING 推失败卡片

**Plan 文件格式**：引用 `layers/planning-harness-layer.md §三` 获取完整 YAML schema（YAML frontmatter + Decisions[] + 可选 `project_context_change`）。

**三阶段交互模式**：骨架（OUTLINE）→ 深入（DECISIONS_IN_PROGRESS）→ 定稿（FINAL）。

- [ ] **Step 9: 不 commit**

---

## Task 8: §六.3 规格层

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §六.3 + Commit 2）

Content source：v2.6 §5.3 + `docs/context/layers/spec-harness-layer.md`。

- [ ] **Step 1: 章节头**

`### 6.3 规格层（Spec Layer）`

- [ ] **Step 2: 填 §6.3.1 使命**

~100 字：把"规划层已定决策 + Requirement Doc"翻译为"生成层能够自驱 coding 的 Spec Artifacts 三元组"。飞书 9 节 Spec（Stage 1）不是本层终端交付物，而是"人-AI 协作协议"；卡点 1a 通过后 Stage 2 的 Spec Artifacts 才是下游消费对象。规格层**不做决策**，只翻译决策。

- [ ] **Step 3: 填 §6.3.2 输入**

**A. 上下文**：
- Project-level：Architecture Snapshot（实施期只读，即 `docs/ARCHITECTURE.md`）/ ACM Registry / Design System Snapshot
- REQ-level：Requirement Doc（只读）/ Plan（构造期读飞书 Plan docx；Stage 2 读 `plans/<req_id>.md`）/ Design Artifact（needs_ui=true 时）
**B. 决策点**：
- **D-SPEC-1 Checkpoint 1a · Design Gate**（方案门）

- [ ] **Step 4: 填 §6.3.3 2×3 矩阵增量**

| | Project-level | REQ-level |
|---|---|---|
| Guides | N/A（**只读**消费，不再演化） | **create**: Spec Stage 1（9 节飞书 Spec）→ Spec Artifacts（design.md / tasks.md） |
| Sensors | N/A | **create**: `ac-schedule.yaml`（本 REQ AC 排班） |
| Invariants | **amend**: ACM Registry（`acm-registry.yaml` patch） | **create**: design.md `supersedes` 节 |

- [ ] **Step 5: 填 §6.3.4 状态机（Spec 子状态机）**

搬运 v2.6 §5.3 子状态机图：
```
null ─spec_start→ SPEC_DRAFTING ⇌ ai_review_pass/reject
                   │
                   ▼ checkpoint_1a_pass (捕获 spec_source_revision)
               SPEC_TRANSFORMING ⇌ transform_deadlock（自循环）
                   │
                   ▼ transform_converged
               SPEC_LOCKED → 进入 Harness 层
                   │
                   ▼ checkpoint_1a_reject / spec_abort
               SPEC_REJECTED（仅留档）
```

术语规范化：**Spec Transformation Loop** 替代 "转化博弈"；**Parallel Sub-State Tracks** 替代 "三产物列并行"。

- [ ] **Step 6: 填 §6.3.5 Hook 装配**

- onEnter(SPEC_DRAFTING) → 派发 spec-author
- onExit(SPEC_DRAFTING on ai_review_pass) → 推 Checkpoint 1a 卡片
- onEnter(SPEC_TRANSFORMING) → 同步 Spec Stage 1 至 `specs/<req_id>/spec.md`；派发 spec-transformer
- onEnter(SPEC_LOCKED) → 发布 Spec Artifacts PR；patch `acm-registry.yaml`

- [ ] **Step 7: 填 §6.3.6 能力层绑定**

OpenClaw Skill：`spec-author` / `spec-reviewer`（Stage 1）+ `spec-transformer` / `spec-transformer-reviewer`（Stage 2 博弈循环）
外部 API：飞书 docx（Stage 1 读写）+ GitHub API（Stage 2 PR + ACM patch）
能力层替换零风险：所有 GitHub I/O 由 Coordinator 的 GitHubGateway 独占，Agent 只产文本

- [ ] **Step 8: 填 §6.3.7 完成标准 & 失败回退**

- 完成：`SpecStatus == LOCKED`；Spec Artifacts PR 合入；`acm-registry.yaml` 已 patch
- 失败：
  - Stage 1 ai_review_reject → 留在 SPEC_DRAFTING
  - Checkpoint 1a reject → SPEC_REJECTED（仅留档，不回退需求层）
  - Stage 2 max_rounds 超限 → transform_deadlock 自循环 + 写人工工单（不回退 SPEC_DRAFTING）
  - `/spec restart` → 重置 SpecStatus（不级联上游）

**四道工程闸门**：Round 0 AC 认领 / Computational gate / transform_trace / Regression scan（定义见 `layers/spec-harness-layer.md §六`）。

**闸门哲学**：Inferential signals 只用于 spec-reviewer + spec-transformer-reviewer；Computational signals 前置所有 schema/正则/路径一致性/回归扫描；Human signal 只保留 Checkpoint 1a。

**关键架构说明**：v3.0 起规格层**不再演化** Architecture Snapshot（演化主通道由规划层承担，见 §6.2）；规格层**只读消费** `docs/ARCHITECTURE.md`。v2.6 的 `context_token + revision` 并发写回协议 **整套退出**（由 §3.5 时相分段替代）。

- [ ] **Step 9: 锚点校验（§六 三子层）**

Run：
```bash
grep -n -E "§6\.[1-3]\.[1-7]" docs/context/harness-engineering-methodology-v3.0.md | wc -l
```
Expected: 21（3 子层 × 7 子节）

- [ ] **Step 10: Commit 2（构造期 commit）**

```bash
git add docs/context/harness-engineering-methodology-v3.0.md
git commit -m "$(cat <<'EOF'
docs(methodology): v3.0 project layer + construction phase (§五–§六)

- §五 Project lifetime layer (Bootstrap 7 steps + 2x3 matrix)
- §六.1 Requirement layer with Dual Gate as D-REQ-1/2
- §六.2 Planning layer as sole Architecture Snapshot evolution channel
- §六.3 Spec layer as decision-translator only (no more architecture
  evolution responsibility); context_token+revision protocol retired

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: §七.1 Harness 层

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §七.1）

Content source：v2.6 §5.4。

- [ ] **Step 1: 章节头**

`### 7.1 Harness 层（Harness Layer）`

- [ ] **Step 2: 填 §7.1.1 使命**

~80 字：把 Spec Artifacts 的 harness 骨架填充为可执行测试代码；产出 Impl PR 的合并硬门槛（P0 Harness + 视觉回归）。

- [ ] **Step 3: 填 §7.1.2 输入**

**A. 上下文**：
- Project-level：ACM Registry（历史回归 AC 列表）/ Design System Snapshot
- REQ-level：Spec Artifacts 四文件（只读，锁定的 ac-schedule.yaml + design.md + tasks.md + harness 骨架）/ 项目历史 Harness 代码（去重参考）
**B. 决策点**：
- **D-HARN-1 Checkpoint 1b · Harness Gate**（Harness 门）

- [ ] **Step 4: 填 §7.1.3 2×3 矩阵增量**

| | Project-level | REQ-level |
|---|---|---|
| Guides | N/A | N/A |
| Sensors | N/A | **create**: Harness Test Code（`harness/tests/REQ-*/`，每 AC 一测试） + 覆盖率矩阵 |
| Invariants | **amend**: ACM Registry（status → finalized，回填 test_file / test_function） | N/A |

- [ ] **Step 5: 填 §7.1.4 状态机**

（简化；Harness 层实施期，无 Coordinator 子状态机，用 PR 生命周期描述）
- 状态：`GENERATING → PENDING_REVIEW → FINALIZED / REJECTED`
- 触发：Spec PR 合入 → `spec-to-harness.yml` workflow 自动触发 → 生成 Harness PR → Checkpoint Handler 推 Checkpoint 1b 卡片

- [ ] **Step 6: 填 §7.1.5 Hook 装配**

GitHub Actions workflow：`spec-to-harness.yml`（生成）+ Checkpoint Handler 回调（卡片按钮 → 合并 Harness PR → ACM patch finalized）

- [ ] **Step 7: 填 §7.1.6 能力层绑定**

Claude Code CLI（填充 Harness 代码）+ GitHub Actions + Playwright（视觉回归，needs_ui=true）

- [ ] **Step 8: 填 §7.1.7 完成标准 & 失败回退**

- 完成：Harness PR 合入；P0 测试全绿；历史回归全绿；ACM Registry patch finalized
- 失败：Harness 生成失败 → 推人工卡片；Checkpoint 1b reject → 补测试回 GENERATING
- 关键约束：
  - ACM 是唯一权威输入（given/input/expected 直接对应测试 fixture/assertion）
  - P0 是 Impl PR 硬门槛
  - 历史 Harness 目录只读（单调累积）
  - 视觉回归基于 Playwright 对 `design-ui.md` 定义的关键视图做截图比对

- [ ] **Step 9: 不 commit**（并入 Task 10 末尾）

---

## Task 10: §七.2-7.5 生成/验证/集成/交付层

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §七.2-7.5 + Commit 3）

Content source：v2.6 §5.5-5.8 + `docs/context/layers/generation-delivery-layers.md`。

由于生成/验证/集成/交付层在 v2.6 仍为概念阶段，内容薄；每层按 7 子节填写，但矩阵增量多为 N/A。

- [ ] **Step 1: 写 §7.2 生成层**

- §7.2.1 使命（~60 字）：AI 基于锁定 Spec Artifacts + Harness 自主生成实现代码，直到所有 P0 Harness 通过
- §7.2.2 输入：
  - 上下文：Project-level（Architecture Snapshot / Design System Snapshot / ACM Registry / CLAUDE.md 热加载）；REQ-level（Spec Artifacts + Harness Test Code 只读）
  - 决策点：**无**（全自动，max 3 轮自修复循环后暂停才请人）
- §7.2.3 2×3 矩阵：
  - Project-level Guides: **amend**（可能更新 ARCHITECTURE，在 Impl PR 内部）
  - REQ-level: **create** Impl PR（非三元组产物，但纳入跟踪）
- §7.2.4 状态机：Impl PR 生命周期（DRAFTING → CI_RUNNING → READY）
- §7.2.5 Hook：`harness-confirmed.yml` workflow 触发 Claude Code CLI
- §7.2.6 能力层：Claude Code CLI + GitHub Actions
- §7.2.7 完成 / 失败：P0 全绿进验证层；3 轮自修复未收敛 → 暂停请人；禁止改 `harness/tests/` 和 `docs/specs/`

- [ ] **Step 2: 写 §7.3 验证层**

- §7.3.1 使命：全量跑 Harness，给明确通过/失败信号，触发 Checkpoint 2
- §7.3.2 输入：
  - 上下文：Impl PR diff / Harness Test Code / 视觉回归基线 / ACM Registry（历史回归 AC）
  - 决策点：**D-VAL-1 Checkpoint 2 · Quality Gate**
- §7.3.3 2×3 矩阵：
  - REQ-level Sensors: **run**（执行既有 Sensors，不产新）
- §7.3.4 状态机：CI 状态（PENDING → RUNNING → PASS/FAIL）
- §7.3.5 Hook：CI 完成回调 → AI 失败分析脚本调用 Claude API → 失败摘要写入 PR 评论
- §7.3.6 能力层：GitHub Actions CI + AI 分析脚本
- §7.3.7 完成：P0 + 历史 ACM 全绿 → Checkpoint 2 卡片；人工合并 PR

- [ ] **Step 3: 写 §7.4 集成层**

- §7.4.1 使命：合并后自动部署 Staging，Smoke Test，触发 Checkpoint 3
- §7.4.2 输入：
  - 上下文：合并到 staging 分支的代码 / design.md 接合点声明 / `docs/ARCHITECTURE.md`
  - 决策点：**D-INT-1 Checkpoint 3 · Release Gate**
- §7.4.3 2×3 矩阵：
  - Project-level Guides: **amend**（合并后 `docs/ARCHITECTURE.md` 接合点生效）
  - Project-level Invariants: **amend**（ACM Registry status → integrated）
- §7.4.4 状态机：Staging 部署状态（DEPLOYING → READY / FAILED）
- §7.4.5 Hook：`staging.yml` workflow
- §7.4.6 能力层：GitHub Actions + 部署脚本
- §7.4.7 完成：Staging 可访问 + Smoke Test 通过 → Checkpoint 3 卡片；失败 → 回滚 Staging
- Smoke Test 原则：仅验证核心路径可用性，不追求完整覆盖

- [ ] **Step 4: 写 §7.5 交付层**

- §7.5.1 使命：参数化部署客户环境，自动健康检查，失败自动回滚
- §7.5.2 输入：
  - 上下文：Checkpoint 3 通过信号 / 客户配置文件（`.env` 隔离）
  - 决策点：**无**（全自动 + 健康检查 gate）
- §7.5.3 2×3 矩阵：
  - Project-level Invariants: **amend**（ACM Registry status → released）
- §7.5.4 状态机：部署状态（DEPLOYING → HEALTHY / ROLLBACK）
- §7.5.5 Hook：`deploy.yml` workflow + 健康检查回调
- §7.5.6 能力层：GitHub Actions + 客户部署脚本
- §7.5.7 完成：客户环境响应正常；健康检查通过；客户隔离原则（每客户独立 .env）

- [ ] **Step 5: 锚点 + 子层计数校验**

Run：
```bash
grep -n -E "§7\.[1-5]\.[1-7]" docs/context/harness-engineering-methodology-v3.0.md | wc -l
```
Expected: 35（5 子层 × 7 子节）

Run：
```bash
grep -nE "D-(HARN|VAL|INT)-1" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 至少 3 条（D-HARN-1 / D-VAL-1 / D-INT-1 各被引用）

- [ ] **Step 6: Commit 3（实施期 commit）**

```bash
git add docs/context/harness-engineering-methodology-v3.0.md
git commit -m "$(cat <<'EOF'
docs(methodology): v3.0 implementation phase (§七)

- §7.1 Harness layer (Checkpoint 1b · Harness Gate)
- §7.2 Generation layer (fully automated, self-repair up to 3 rounds)
- §7.3 Validation layer (Checkpoint 2 · Quality Gate)
- §7.4 Integration layer (Checkpoint 3 · Release Gate, Staging)
- §7.5 Delivery layer (parameterized client deploy)

Each sub-layer fills 2x3 matrix increments; CI-driven layers use the
implementation-phase workflow template (§4.4).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: §八 横向基础设施 + §九 实施路线图

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加 §八 + §九）

Content source：v2.6 §六（人工协同轨 + 工程自动化轨）+ v2.6 §七（Phase 0-5 表）+ meta-spec §8.5 决策点总览表。

- [ ] **Step 1: 写 §八.1 人工协同轨（飞书 + OpenClaw）**

搬运 v2.6 §6.1：
- Coordinator Service + OpenClaw 角色
- OpenClaw 在三层架构中的定位（能力层）
- 人工协同轨回答五类问题（真/发生/决策/下一步/知识沉淀）的表格

- [ ] **Step 2: 写 §八.2 工程自动化轨（GitHub + CI）**

搬运 v2.6 §6.2：
- Checkpoint Handler + GitHub Actions 角色
- 工程自动化轨核心约束（harness/tests/ 只读；docs/specs/ 锁定；CLAUDE.md 唯一行为规则；所有状态变更走 Checkpoint Handler）

- [ ] **Step 3: 写 §八.3 两轨协作接口**

搬运 v2.6 §6.3 事件表（REQ APPROVED / 卡点 1a/1b / CI 通过/失败 / Staging 就绪 / 卡点 3 等），术语规范化（卡点 1a → Checkpoint 1a）。

- [ ] **Step 4: 写 §八.4 决策点总览表**

照搬 meta-spec §8.5 的 8 行表格（D-REQ-1/2、D-PLAN-1/2、D-SPEC-1、D-HARN-1、D-VAL-1、D-INT-1），字段：`ID / 名称 / 所在层 / 触发 state / 判断权`。

表下方加一句："Checkpoint 1a/1b/2/3 是四个传统'人工卡点'；v3.0 显式扩展为 8 个决策点以覆盖需求层双门、Final Review、Planning Approval Gate、Plan Final Approval 等全部人-AI 交互判断点。"

- [ ] **Step 5: 写 §九 实施路线图**

搬运 v2.6 §七 的 Phase 0-5 表，术语规范化 + 更新 Phase 2 最新状态：
- Phase 0: 工程自动化轨地基（完成）
- Phase 1: 需求层上线（完成）
- Pre-Phase-2: 需求层稳固 + ARCHITECTURE 归属澄清（完成）
- Phase 2: 需求层→规格层桥接 + 规划层落地（v3.0 起 Phase 2 明确包含规划层 Plan Approval Gate 实施）
- Phase 3: Harness 层 → 生成层自动化
- Phase 4: 首个真实项目端到端
- Phase 5: 飞轮运转

末尾保留 "副作用职责边界" 小节（Coordinator 所有 GitHub 写入走 hook；状态机保持纯函数）。

- [ ] **Step 6: 不 commit**（并入 Task 12）

---

## Task 12: 附录 A/B/C + 全文审查 + Commit 4

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v3.0.md`（追加附录 + Commit 4）

- [ ] **Step 1: 写附录 A · 术语表（A-Z 索引）**

**三栏**：`术语 / 含义 / 类别`。类别分：业界对齐 / 本方法论独创 / alias（退役词）。

最少条目：
- Agent = Model + Harness（业界）
- ACM / Acceptance Criteria Matrix（业界）
- ac-schedule.yaml（本方法论独创 artifact 名）
- acm-registry.yaml（本方法论独创 artifact 名）
- Architecture Snapshot（本方法论独创，替代 ARCHITECTURE 模糊叫法）
- Cascading Reset（业界对齐，替代"级联 restart"）
- Checkpoint Handler（本方法论独创服务名）
- Checkpoint 1a / 1b / 2 / 3（本方法论独创编号）
- Cold / Warm / Hot Context（业界对齐，Codified Context 论文）
- Computational signal / Inferential signal（业界对齐，Fowler）
- Construction-phase SOT / Implementation-phase SOT（本方法论独创）
- Coordinator Service（本方法论独创服务名）
- Drift Prevention（业界对齐）
- Externalized memory（业界对齐）
- Freeze Point（本方法论独创）
- Generator-Evaluator Loop（业界对齐，Anthropic）
- Guides / Sensors / Invariants（业界对齐，三元组）
- Harness engineering（业界对齐）
- Known Constraint（KC）（本方法论独创）
- OpenClaw / OpenClaw Skill（本方法论独创能力层名）
- Parallel Sub-State Tracks（业界对齐）
- Planning Approval Gate（业界对齐 HITL 术语）
- Project-level Context / REQ-level Context（本方法论独创）
- REQ ID（本方法论独创 ID 格式）
- Requirement Dual Gate（业界对齐）
- Spec Stage 1 / Spec Artifacts（本方法论独创）
- Spec Transformation Loop（业界对齐，替代"博弈"）
- Spec-Driven Development (SDD)（业界对齐）
- supersedes（业界对齐 YAML 字段）
- tasks.md（业界对齐 artifact 名）

**退役词 alias**（标注"→ 迁至 X"）：
- 边界锚 → Invariants
- 博弈 / 转化博弈 → Spec Transformation Loop
- 前馈 / 反馈（Fowler 外）→ 输入约束 / 产出反馈
- 三产物列并行 → Parallel Sub-State Tracks
- 级联 restart → Cascading Reset
- 防漂移 → Drift Prevention
- 双闸门 → Requirement Dual Gate
- 方案门 / Harness 门 / 质量门 / 发布门 → Checkpoint 1a / 1b / 2 / 3
- 架构授权闸门 → Planning Approval Gate
- acceptance.yaml → ac-schedule.yaml
- spec/registry/consolidated.yaml → acm-registry.yaml
- ARCHITECTURE.yaml → docs/ARCHITECTURE.md

- [ ] **Step 2: 写附录 B · v2.6 → v3.0 语义变更结论索引**

直接搬运 meta-spec §九 的"v2.6 → v3.0 矛盾归结清单"表（v2.6 矛盾 / v3.0 归结 / 影响章节）。

前置一句："本附录仅列结论，不做考古；如需 v2.6 原文请查 `docs/archive/harness-engineering-methodology-v2.6.md`。"

- [ ] **Step 3: 写附录 C · 衍生文档导航**

三栏表：`文档路径 / 对齐状态 / 说明`。

| 文档 | 对齐状态 | 说明 |
|---|---|---|
| `docs/context/infra/context-chain-principle.md` | v3.0 对齐 | §七 并发写回契约已删除；§八 Callback 唯一真相保留 |
| `docs/context/infra/project-context.md` | v3.0 对齐 | 文件名/路径统一；ARCHITECTURE 演化责任方更新 |
| `docs/context/infra/state-machine-hook-pattern.md` | v3.0 对齐 | v3.0 §4.2 引用 |
| `docs/context/infra/harness-engineering-industry-alignment-2026-04-16.md` | v3.0 对齐 | v3.0 §1.4 引用 |
| `docs/context/infra/tooling.md` | 保留 | 自研工具清单 |
| `docs/context/infra/feishu-setup.md` | 保留 | 飞书配置 |
| `docs/context/infra/github-structure.md` | 保留 | GitHub 仓库结构 |
| `docs/context/layers/requirement-layer.md` | v2.x 待重构 | 见顶部 banner，对应 v3.0 §6.1 |
| `docs/context/layers/planning-harness-layer.md` | v2.x 待重构 | 见顶部 banner，对应 v3.0 §6.2 |
| `docs/context/layers/spec-harness-layer.md` | v2.x 待重构 | 见顶部 banner，对应 v3.0 §6.3 |
| `docs/context/layers/generation-delivery-layers.md` | v2.x 待重构 | 见顶部 banner，对应 v3.0 §7.2-7.5 |
| `docs/agents/*/SKILL.md` | v2.x，分 issue 对齐 | 随 OpenClaw 仓库 PR 推进 |
| `docs/archive/harness-engineering-methodology-v2.6.md` | 归档史料 | 仅供对照 |

- [ ] **Step 4: 全文一致性审查（硬闸门）**

A. 术语退役词扫描：
```bash
grep -nE "边界锚|转化博弈|三产物列|级联 restart|架构授权闸门|acceptance\.yaml|ARCHITECTURE\.yaml|双闸门(?!.*Dual Gate)" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 无命中（"双闸门" 如与 "Requirement Dual Gate" 配对出现在术语表 alias 映射则允许，但正文中不应独立出现）

B. 层计数扫描：
```bash
grep -nE "七层|八层" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 无命中

C. 卡点数扫描：
```bash
grep -nE "四卡点|五卡点|六卡点" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 无命中（v3.0 统一为 "8 个决策点"，其中 Checkpoint 1a/1b/2/3 是传统"四卡点"子集）

D. 锚点完整性：
```bash
grep -nE "§[一-九]|§[0-9]" docs/context/harness-engineering-methodology-v3.0.md | grep -oE "§[0-9]+\.[0-9]+" | sort -u
```
Expected: 所有引用的 §N.M 都能在文档中找到对应标题

E. context_token 残留扫描：
```bash
grep -n "context_token\|revision round-trip" docs/context/harness-engineering-methodology-v3.0.md
```
Expected: 最多只出现在附录 B 的 v2.6 归结索引 + 可能的 "已退出" 说明句

- [ ] **Step 5: 写版本签名 footer**

追加至文件末尾：
```
---
*v3.0 | 2026-04-21 | 完整重构：双主语言 + 终态倒推 + 两段式层结构；本文是唯一权威，v2.6 归档于 docs/archive/。*
```

- [ ] **Step 6: Commit 4（主文完工 commit）**

```bash
git add docs/context/harness-engineering-methodology-v3.0.md
git commit -m "$(cat <<'EOF'
docs(methodology): v3.0 infrastructure + roadmap + appendices (§八–附录C)

- §八 horizontal infra (Feishu+OpenClaw / GitHub+CI + two-track interface)
- §八.4 unified 8-decision-point index (D-REQ-1/2, D-PLAN-1/2,
  D-SPEC-1, D-HARN-1, D-VAL-1, D-INT-1)
- §九 implementation roadmap updated for Phase 2 planning layer
- Appendix A: A-Z glossary with aliases
- Appendix B: v2.6 → v3.0 semantic change index
- Appendix C: derivative doc alignment navigation

Full-text consistency audit passes (term/anchor/cardinality scans).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: 改写 `context-chain-principle.md`

**Files:**
- Modify: `docs/context/infra/context-chain-principle.md`

Content source：当前 `context-chain-principle.md` + meta-spec §10.1。

- [ ] **Step 1: 读取当前文件**

Read：`docs/context/infra/context-chain-principle.md`（248 行）

- [ ] **Step 2: 改写顶部"本文是方法论的补充原则文档"引用**

原：`> 本文是方法论 [harness-engineering-methodology-v2.0.md](...) 的补充原则文档。`
新：`> 本文是方法论 v3.0 [harness-engineering-methodology-v3.0.md](../harness-engineering-methodology-v3.0.md) 的补充原则文档，承担"设计文档审查清单"职责。`

- [ ] **Step 3: 降级 §一 "核心原则"**

保留"五个问题"表格（消费/如何消费/产出/如何传递/防漂移），但改写开头声明：
原：`**在每层设计时，必须显式回答以下五个问题。这不是可选的补充说明，而是每层设计文档的强制组成部分。**`
新：`**在每层设计文档 / Agent SKILL.md 审查时，以下五个问题作为必过清单；其与方法论 v3.0 §三 2×3 矩阵配合使用——2×3 矩阵是首要工具，本清单是对应文档评审时的 checklist。**`

- [ ] **Step 4: 保留 §二-§六**

基本保留不动；执行术语规范化：
- 搜索替换所有"前馈/反馈"→ 结合上下文改为 "Guides/Sensors" 或 "输入约束/产出反馈"
- "防漂移" → "Drift Prevention"（中文解说保留为"漂移预防"）
- "双闸门" → "Requirement Dual Gate"
- "卡点" → "Checkpoint" 或 "决策点"

- [ ] **Step 5: 整节删除 §七 "并发写回契约"**

完整删除从 `## 七、并发写回契约` 到 `## 八、` 之前的所有内容（约 35 行）。

原因：时相分段模型已取代 `context_token + revision` 握手协议；ARCHITECTURE 的并发写回场景不再存在（实施期 SOT 是 GitHub 只读副本）。

- [ ] **Step 6: 保留 §八 "Callback 作为状态机唯一真相"**

**不删除**。Callback 即状态机唯一真相的约束在 v3.0 仍完全适用，所有 Agent SKILL.md 强制要求"本次会话最终动作必须是 callback"。

将原 §八 改编号为 §七（填补删除后的空缺）。

- [ ] **Step 7: 添加顶部版本说明 banner**

在 `> 本文是...` 之后加一行：
```
> **v3.0 对齐 · 2026-04-21**：§七 并发写回契约（context_token + revision round-trip）在 v3.0 整节删除，由方法论 §3.5 时相分段模型替代；原 §八 Callback 唯一真相重编号为 §七，约束保持不变。
```

- [ ] **Step 8: 验证**

Run：
```bash
grep -nE "context_token|revision round-trip|并发写回" docs/context/infra/context-chain-principle.md
```
Expected: 仅顶部 banner 一处命中（说明已退出）

Run：
```bash
grep -c "^## " docs/context/infra/context-chain-principle.md
```
Expected: 7（降到 7 个顶级小节：§一-§七）

- [ ] **Step 9: Commit 5**

```bash
git add docs/context/infra/context-chain-principle.md
git commit -m "$(cat <<'EOF'
docs(infra): align context-chain-principle to methodology v3.0

- Remove §七 concurrent-write protocol (context_token + revision
  round-trip); replaced by time-phased SOT model in methodology §3.5
- Rename §八 Callback Sole Truth to §七 (constraint unchanged)
- Demote five-question template to design/SKILL-review checklist;
  2x3 matrix in methodology §三 is the primary tool
- Term normalization per methodology v3.0 §五 (前馈/反馈 → Guides/Sensors)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: 改写 `project-context.md`

**Files:**
- Modify: `docs/context/infra/project-context.md`

Content source：当前 `project-context.md` + meta-spec §10.1。

- [ ] **Step 1: 读取当前文件**

Read：`docs/context/infra/project-context.md`（377 行）

- [ ] **Step 2: 改写顶部 ARCHITECTURE 定位声明**

原（约 line 8-10）：
```
> **定位**（Pre-Phase-2 校准）：ARCHITECTURE 是 **Spec 层的核心产出物之一**...
```

新：
```
> **定位**（v3.0 对齐）：Architecture Snapshot 是 **Project-level Guides**，由 Project 寿命层（Bootstrap）首次创建，由**规划层（Planning Approval Gate）**作为唯一演化主通道。规格层只读消费，不再负责演化。GitHub 侧 `docs/ARCHITECTURE.md` 是实施期只读镜像，由 Plan READY hook 单向同步产出。
```

- [ ] **Step 3: 改写 §一 诞生时机**

原：`**诞生**：项目**首条 REQ 进入 Spec 阶段**（APPROVED → SPEC_DRAFTING 过渡）时，Coordinator 以类目模板（template_version）为骨架创建飞书文档`

新：`**诞生**：项目 Bootstrap 的 `CREATE_ARCHITECTURE_DOC` 步骤（§5.0 Project 层）首次创建飞书 ARCHITECTURE docx（空骨架）。首份 GitHub `docs/ARCHITECTURE.md` 由首次 Plan READY 同步触发产出，避免空镜像。`

- [ ] **Step 4: 改写 §一 演化描述**

原：`spec-author Agent 通过 /queries/openclaw/spec-context 端点获取当前 revision 与 context_token → feishu_fetch_doc 读取当前 YAML → 基于本次 Spec 决策做增量合并 → feishu_update_doc 覆盖写回 → 再次拉 revision → 在 spec-submit callback 回传 context_token 与写后 revision`

新：`plan-author Agent 通过 /queries/openclaw/plan-context 端点获取当前 Architecture Snapshot → 基于本次 Plan 的 `project_context_change` 增量做合并 → 经 Planning Approval Gate（D-PLAN-1）人工授权后，由 `on_enter(PlanStatus.READY)` 钩子原子同步至 GitHub `docs/ARCHITECTURE.md`（与 Plan 同一 commit）。详见方法论 §6.2。`

- [ ] **Step 5: 改写 §一 更新责任边界表**

`spec-author Agent` 相关行改为 `plan-author Agent`；`spec-reviewer` 的校核职责保留但加说明"引用当前 Architecture Snapshot"。

- [ ] **Step 6: 删除 §一 "并发安全"小节**

原小节内容：`ARCHITECTURE 是唯一跨 REQ 共享的项目级飞书产出物，并发保护走 context_token + revision round-trip 握手...`
直接删除整段；加一行替代：
```
**并发安全**：时相分段模型下，构造期只有一个 plan-author 会话持有 ARCHITECTURE 编辑权（Plan 生命周期单作者），写回后 Plan READY hook 原子同步至 GitHub，无并发竞争。详见方法论 §3.5。
```

- [ ] **Step 7: 改写 §二 ACM 注册表**

- 文件路径：`spec/registry/consolidated.yaml` → 根级 `acm-registry.yaml`
- 字段 `spec_path: "spec/REQ-PROJECT-001/acceptance.yaml"` → `spec_path: "docs/specs/REQ-PROJECT-001/ac-schedule.yaml"`
- 全文 `acceptance.yaml` → `ac-schedule.yaml`

- [ ] **Step 8: 改写 §五 事件驱动更新表**

更新行：
- 原："首条 REQ 进入 SPEC_DRAFTING | ARCHITECTURE 项目级飞书文档（骨架创建） | Coordinator | 一次性 create"
- 新："项目 Bootstrap（Project 层 §5.0） | Architecture Snapshot 飞书骨架（空） | Coordinator (CREATE_ARCHITECTURE_DOC 步骤) | 一次性 create"

- 原："Spec 撰写（每条 REQ） | ARCHITECTURE 项目级飞书文档（增量演化） | spec-author Agent | 覆盖写；走 context_token + revision 握手"
- 新："Plan 撰写（每条 REQ，若 `project_context_change != None`） | Architecture Snapshot 飞书文档（增量演化） | plan-author Agent + Planning Approval Gate | 覆盖写；授权通过后 Plan READY hook 单向同步至 GitHub"

删除 context_token + revision 相关所有残留语句。

- [ ] **Step 9: 术语规范化**

搜索替换：
- `ARCHITECTURE.yaml`（GitHub 侧提及）→ `docs/ARCHITECTURE.md`
- `acceptance.yaml` → `ac-schedule.yaml`
- `spec/registry/consolidated.yaml` → `acm-registry.yaml`
- `卡点 1a / 1b / 2 / 3` → `Checkpoint 1a / 1b / 2 / 3`

- [ ] **Step 10: 添加顶部 v3.0 对齐 banner**

在文档最顶部加：
```
> **v3.0 对齐 · 2026-04-21**：Architecture Snapshot 演化主通道回迁至规划层（Planning Approval Gate / D-PLAN-1）；`context_token + revision` 协议整套退出；文件名/路径统一（`acm-registry.yaml` / `docs/ARCHITECTURE.md` / `ac-schedule.yaml`）。
```

- [ ] **Step 11: 验证**

Run：
```bash
grep -nE "spec-author\s+Agent.*ARCHITECTURE|spec/registry/consolidated|acceptance\.yaml|ARCHITECTURE\.yaml|context_token" docs/context/infra/project-context.md
```
Expected: 无命中（context_token 如残留仅允许在 v3.0 banner 的"已退出"声明句）

- [ ] **Step 12: Commit 6**

```bash
git add docs/context/infra/project-context.md
git commit -m "$(cat <<'EOF'
docs(infra): align project-context to methodology v3.0

- Architecture Snapshot: birth at Bootstrap (not first SPEC_DRAFTING);
  evolution channel retired from spec-author to plan-author under
  Planning Approval Gate (D-PLAN-1)
- context_token + revision protocol removed (time-phased SOT supersedes)
- Path/filename normalization: acm-registry.yaml (root), ac-schedule.yaml,
  docs/ARCHITECTURE.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: `layers/*` 顶部迁移 banner + 交叉引用更新

**Files:**
- Modify: `docs/context/layers/requirement-layer.md`
- Modify: `docs/context/layers/planning-harness-layer.md`
- Modify: `docs/context/layers/spec-harness-layer.md`
- Modify: `docs/context/layers/generation-delivery-layers.md`

- [ ] **Step 1: 在 `requirement-layer.md` 顶部加 banner**

在第一行 `#` 标题之后、正文之前插入：
```
> **v3.0 对齐 · 2026-04-21**：本文反映 v2.x 模型；与方法论 v3.0 对应的章节是 [§6.1 需求层](../harness-engineering-methodology-v3.0.md#61-需求层)。文件内的交叉引用链接如指向 `harness-engineering-methodology-v2.0.md`，请自行切换到 v3.0。本文将在后续 PR 中对齐改写。
```

并更新文件内指向 v2.0 主文的链接（如果存在）为 v3.0：
Run: `grep -n "harness-engineering-methodology-v2.0" docs/context/layers/requirement-layer.md`
如有命中：逐一 Edit 替换为 `harness-engineering-methodology-v3.0.md`，并同步锚点（如 `#41-层间工作流服务三层分离` → `#42-三层分离元原则`）。

- [ ] **Step 2: `planning-harness-layer.md` 同上**

banner：
```
> **v3.0 对齐 · 2026-04-21**：本文反映 v2.x 模型；与方法论 v3.0 对应的章节是 [§6.2 规划层](../harness-engineering-methodology-v3.0.md#62-规划层)。文件内 schema 与状态机描述在 v3.0 主文中表述更简；本文作为实施细节留档。
```

更新文件内 `harness-engineering-methodology-v2.0.md` 链接。

- [ ] **Step 3: `spec-harness-layer.md` 同上**

banner：
```
> **v3.0 对齐 · 2026-04-21**：本文反映 v2.x 模型；与方法论 v3.0 对应的章节是 [§6.3 规格层](../harness-engineering-methodology-v3.0.md#63-规格层) + [§7.1 Harness 层](../harness-engineering-methodology-v3.0.md#71-harness-层)。v3.0 起规格层**不再演化** Architecture Snapshot（演化主通道 → 规划层）；`context_token + revision` 协议整套退出。本文将在后续 PR 中对齐改写。
```

更新文件内 `harness-engineering-methodology-v2.0.md` 链接。

- [ ] **Step 4: `generation-delivery-layers.md` 同上**

banner：
```
> **v3.0 对齐 · 2026-04-21**：本文反映 v2.x 模型；与方法论 v3.0 对应的章节是 [§7.2–7.5 生成/验证/集成/交付层](../harness-engineering-methodology-v3.0.md#72-生成层)。本文将在后续 PR 中对齐改写。
```

更新文件内 `harness-engineering-methodology-v2.0.md` 链接。

- [ ] **Step 5: 验证**

Run：
```bash
grep -l "v3.0 对齐" docs/context/layers/*.md
```
Expected: 4 个文件全命中

Run：
```bash
grep -rn "harness-engineering-methodology-v2\.0" docs/context/layers/
```
Expected: 无命中（除非在 banner 里显式引用历史版本作为说明）

- [ ] **Step 6: Commit 7**

```bash
git add docs/context/layers/requirement-layer.md docs/context/layers/planning-harness-layer.md docs/context/layers/spec-harness-layer.md docs/context/layers/generation-delivery-layers.md
git commit -m "$(cat <<'EOF'
docs(layers): add v3.0 alignment banners to layer detail docs

All four layer detail docs now carry a v3.0 banner linking to the
corresponding v3.0 main-text section. Internal cross-references to
methodology-v2.0.md updated to methodology-v3.0.md. Content itself
remains v2.x; full rewrite deferred.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: 归档 v2.6 + 最终交叉引用扫描

**Files:**
- Rename: `docs/context/harness-engineering-methodology-v2.0.md` → `docs/archive/harness-engineering-methodology-v2.6.md`

- [ ] **Step 1: 检查 v2.0 文件在其他位置的引用**

Run：
```bash
grep -rn "harness-engineering-methodology-v2\.0" docs/
```
Expected 命中位置：
- `docs/context/layers/*.md`（Task 15 应已处理）
- `docs/context/infra/*.md`（Task 13-14 应已处理）
- 可能残留：`docs/superpowers/specs/*.md`、`docs/superpowers/plans/*.md`、`docs/agents/*/SKILL.md`

记录所有命中，决定：
- 若在 specs/plans（历史快照文档）：**保留不改**（历史快照指向当时版本是合理的）
- 若在 infra/layers：应已改（Task 13-15）；如有遗漏当场 Edit 修正
- 若在 agents/SKILL.md：**保留不改**（归入"跟随 OpenClaw 仓库 PR 对齐"）

- [ ] **Step 2: 使用 git mv 重命名文件**

```bash
git mv docs/context/harness-engineering-methodology-v2.0.md docs/archive/harness-engineering-methodology-v2.6.md
```

- [ ] **Step 3: 在归档文件顶部加归档说明**

Edit `docs/archive/harness-engineering-methodology-v2.6.md`，在第一行标题之后插入：
```
> **已归档 · 2026-04-21**：本文件是方法论 v2.6（最后补丁 2026-04-21 时相分段模型），已被 [v3.0](../context/harness-engineering-methodology-v3.0.md) 全量替代。保留仅供对照。v3.0 的设计变更结论索引见 v3.0 附录 B。
```

- [ ] **Step 4: 更新 `docs/archive/` 内历史链接**

归档文件内部如有指向 `layers/` 或 `infra/` 的相对链接，需要调整 `../context/layers/...`（因为从 `docs/archive/` 到 `docs/context/layers/` 的相对路径多一层）。

Run：
```bash
grep -nE "\]\(layers/|\]\(infra/" docs/archive/harness-engineering-methodology-v2.6.md
```
如有命中：Edit 改为 `../context/layers/` 和 `../context/infra/`。

- [ ] **Step 5: 验证最终状态**

Run：
```bash
ls docs/context/harness-engineering-methodology-*.md docs/archive/harness-engineering-methodology-*.md
```
Expected:
```
docs/archive/harness-engineering-methodology-v1.3.md
docs/archive/harness-engineering-methodology-v2.6.md
docs/context/harness-engineering-methodology-v3.0.md
```

Run：
```bash
grep -rn "harness-engineering-methodology-v2\.0" docs/context/ docs/superpowers/plans/2026-04-21-methodology-v3-restructure-plan.md
```
Expected: 无命中

- [ ] **Step 6: Commit 8（归档 commit）**

```bash
git add -u docs/context/harness-engineering-methodology-v2.0.md docs/archive/harness-engineering-methodology-v2.6.md
git commit -m "$(cat <<'EOF'
docs(archive): retire methodology v2.6 in favor of v3.0

Move docs/context/harness-engineering-methodology-v2.0.md (which
contained v2.6 content after 2026-04-21 patches) to
docs/archive/harness-engineering-methodology-v2.6.md. v3.0 is now
the sole authoritative methodology doc.

Archived copy carries a banner pointing to v3.0 and its appendix B
(v2.6 → v3.0 semantic change index) for comparison.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

以下按 writing-plans skill 要求自审。

**1. Spec 覆盖**：

| meta-spec 章节 | 对应 plan task |
|---|---|
| §一 背景目标 | 内嵌于各 task 动机 |
| §二 7 项决策锁定 | 全 plan 所有 task 遵守 |
| §三 写作规范 | Task 1 Step 1 内嵌 §序；全 plan 所有 Step 4-5/7-8 术语扫描 |
| §四 v3.0 章节骨架 | Task 1-12 完整覆盖 序 + §一~§九 + 附录 A/B/C |
| §五 术语规范化表 | Task 12 Step 1 附录 A 展开；全文扫描（Task 4 Step 8, Task 12 Step 4） |
| §六 §二 推理链 | Task 2 全部 6 个 Step |
| §七 条目类型表 + 矩阵 + 时相 | Task 3 全部 7 个 Step |
| §八 工作流模板 + 决策点总览 | Task 4（模板）+ Task 11 Step 4（决策点表） |
| §九 矛盾归结 | Task 12 Step 2 附录 B |
| §十 衍生文档联动 | Task 13（context-chain-principle）+ Task 14（project-context）+ Task 15（layers banner）+ Task 16（归档） |
| §十一 交付清单 | plan 总体交付物 |
| §十二 未决项 | Plan 不涉及（v3.0 撰写阶段自然处理） |

无缺口。

**2. Placeholder 扫描**：

- Plan 内所有 "Expected" 给出具体数值或 "无命中"
- 所有 commit message 完整书写（无 `<TBD>`）
- 所有 bash 命令可直接复制运行
- §七.2-7.5 每层 7 子节内容均在 Task 10 内展开，未用 "同 Task 9"

唯一"references"处：Task 7 Step 8 "引用 `layers/planning-harness-layer.md §三` 获取完整 YAML schema"——这是允许的，因为 Plan schema 过长不宜整张搬，指向实施细节文档合理。

**3. 类型一致性**：

- 术语 canonical 在全 plan 所有 commit message 与 step 描述中一致（如 "Planning Approval Gate" 不与 "架构授权闸门" 混用）
- 决策点 ID 命名（D-REQ-1/2、D-PLAN-1/2、D-SPEC-1、D-HARN-1、D-VAL-1、D-INT-1）在 Task 6-10 + Task 11 Step 4 + Task 12 Step 1 一致
- 文件名 canonical（`acm-registry.yaml` / `ac-schedule.yaml` / `docs/ARCHITECTURE.md`）在 Task 13-14 全 plan 一致
- Commit 节奏（4 主文 + 1 context-chain + 1 project-context + 1 layers banner + 1 archive = 8 commit）与 File Structure 声明一致

无不一致。

**4. 锚点一致性**：

- v3.0 内部锚点 `§六.1` 等在 Task 6-10 与 Task 15 banner 引用时保持一致格式（如 `#61-需求层`）
- v2.6 → v3.0 章节映射在 Task 15 banner 中显式给出
- 附录 C（Task 12 Step 3）列出的"对齐状态"与 Task 13-15 实际动作一致

无不一致。

Self-review 通过。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-methodology-v3-restructure-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 每个 task 派发全新 subagent 执行，task 间 review；适合 16 个离散任务的大型 plan

**2. Inline Execution** - 当前 session 内批处理执行，checkpoint 中途 review；适合快速推进 + 密切观察

Which approach?
