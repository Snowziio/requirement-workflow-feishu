# Harness Engineering 全自动开发工作流：完整方法论
## v1.2 | 2026-04-08

> ⚠️ **已过期**：当前方法论版本为 v1.3（2026-04-10）。
> 本文件仅作历史参考，请使用 `harness-engineering-methodology-v1.3.md`。

> **贯穿本文的参考案例**
> 客户需求：在租赁业务平台中，使用大模型自动解读申请人的营业执照与征信信息，生成面向租赁场景的格式化风控报告。
> 本文所有流程设计均以此案例为锚点进行说明。

> **v1.2 变更摘要**
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
│ OpenClaw  ║Spec  ║Harness║      ║      ║      ║                  │
│  驱动     ║      ║       ║      ║      ║      ║                  │
├───────────╨─────────────╨─────╨──────╨──────╨────────────────────┤
│                  层内子流程（AI自主处理）                           │
└──────────────────────────────────────────────────────────────────┘

REQ ID（REQ-{PROJECT}-{NNN}）穿透全链路：飞书文档 → Bitable → GitHub branch → PR → ACM

四个人工卡点：
  ⚡1a 方案门（Spec + ACM 确认）
  ⚡1b Harness门（测试覆盖确认）
  ⚡2  质量门（CI通过，合并确认）
  ⚡3  发布门（Staging验收）

需求层内部四阶段（OpenClaw 驱动，飞书内闭环）：
  创建 → 讨论 → UI设计(可选) → 审查
```

**纵向流程**：从需求到交付的七层流水线（规格层拆分为A/B两个子层），定义"做什么"。
**横向基础设施**：贯穿所有层的共用基础设施，分为人工协同和工程自动化两轨。
**层内子流程**：每层内部的AI自主循环，人不感知，由CLAUDE.md约束。
**工作流编排器**：OpenClaw Agent 驻扎在飞书群，驱动需求层全流程，跨层状态同步。

**核心原则**：人只在四个卡点做判断，其余全部由AI或自动化完成。

---

## 二、纵向流程详解

### 2.1 需求层（OpenClaw 驱动，飞书内闭环）

**目标**：将模糊的客户需求转化为经过审查的结构化需求文档 + UI 设计稿。

| 项目 | 内容 |
|---|---|
| 输入 | 客户描述（口头/文字/会议记录） |
| 输出 | 经审查的需求文档 + UI 设计稿（可选），存于飞书文档 |
| 人的工作 | 与 OpenClaw 交互完善需求，审查确认 |
| AI 的工作 | 引导式需求编写、UI 设计生成、需求审查 |
| 自动化 | OpenClaw 全流程驱动，Bitable 状态机自动流转 |
| 索引 | REQ ID（`REQ-{PROJECT}-{NNN}`），跨层唯一标识 |

**需求层在飞书内完全闭环**，不接触 GitHub。输出的需求文档是规格层-A 的输入。

#### 参考基线：OpenClaw 多 Agent 架构

> 说明：以下内容是方法论 v1.2 的原始基线表达。
> 在本仓库对应的当前实现方向中，主协调能力已进一步下沉为独立的 `Coordinator Service`，
> OpenClaw 只承接需求撰写、UI 设计、需求审查等智能角色。

```
Coordinator Service（独立飞书应用后台）
  ├── 监听飞书事件 / 卡片回调 / Workflow 触发
  ├── 维护 Bitable 状态机与工作流卡点
  └── 接收 OpenClaw 智能角色的流程事件
        ├── 需求撰写 Agent ── 私聊驱动需求文档撰写
        ├── UI 设计 Agent ─── 调用 design.md/UIUX ProMax 生成可还原设计稿
        └── 需求审查 Agent ── review 结论生成与流程事件通知
```

#### 需求层内部四阶段子流程

##### 2.1.1 需求创建

```
人: @OpenClaw 创建需求 "需求名称" "需求简述"

OpenClaw 执行:
  1. 生成 REQ ID: REQ-{PROJECT}-{NNN}（Bitable 自增）
  2. Bitable: 新增行（状态=CREATED, 创建人, 时间戳）
  3. 飞书文档: 从需求模板创建文档
     → 路径: 项目空间/{项目名}/REQ-{PROJECT}-{NNN}/需求文档
     → 模板预填: 需求名称、简述、创建人、日期
     → 注入历史约束摘要（只读参考区，从 GitHub 历史 ACM 拉取）
  4. 回复群消息:
     "需求 REQ-XXX-001 已创建
      📄 需求文档: [链接]
      📊 追踪状态: [Bitable 链接]
      @OpenClaw 开始讨论 进入需求细化"
  5. Bitable 状态: CREATED → DISCUSSING
```

##### 2.1.2 需求讨论（需求撰写 Agent）

```
人: @OpenClaw 开始讨论

OpenClaw → 调用需求撰写 Agent:
  → 按需求模板逐项引导（群聊对话式）:
    1. 问题描述 → 2. 使用场景 → 3. 输入数据 → 4. 输出定义
    → 5. 边界排除 → 6. 验收标准 → 7. 非功能要求
  → 每项确认后自动写入飞书文档
  → 持续检查完整度，提示缺失项和歧义点

完成后回复:
  "需求文档完整度检查:
   ✅ 问题描述
   ✅ 使用场景
   ✅ 输入（N项）
   ✅ 输出（N项）
   ✅ 边界
   ⚠️ 验收标准: 第2条量化指标不明确
   ✅ 非功能要求
   📄 查看完整文档: [链接]
   @OpenClaw UI设计 → 进入 UI 设计
   @OpenClaw 进入审查 → 跳过 UI，直接审查"
```

**需求文档模板结构**（飞书文档模板）：

```markdown
# REQ-{ID} {需求名称}
> 创建人: {人员} | 创建时间: {日期} | 状态: {状态}

## 历史约束参考（只读，系统注入）
[AI 从 GitHub 历史 ACM 拉取，列出可能受影响的历史验收标准]

## 问题描述
这个功能解决什么业务问题？

## 使用场景
用户在什么情况下触发，期望得到什么结果？

## 输入
明确列出所有输入数据及其格式。

## 输出
明确列出输出内容、格式、交付方式。

## 边界（不包含什么）
明确排除的功能范围。

## 验收标准（不可省略，每条必须可量化验证）
- [ ] 标准1
- [ ] 标准2

## 非功能要求
性能、安全、合规等约束。
```

##### 2.1.3 UI 设计（可选，UI 设计 Agent）

```
人: @OpenClaw UI设计

OpenClaw → 调用 UI 设计 Agent:
  → Bitable 状态: → UI_DESIGNING
  → 读取需求文档内容（飞书 API）
  → 使用 design.md / UIUX ProMax 生成 UI 设计稿
  → 产物格式: 可被 Coding Agent 直接代码还原的结构化描述
    （组件树 + 样式规范 + 交互逻辑 + 线框图/截图）
  → 写入飞书文档: 项目空间/{项目名}/REQ-{ID}/UI设计稿
  → 通知:
    "UI 设计稿已生成: [链接]
     包含: N 个页面, M 个组件
     @OpenClaw 确认UI → 进入审查
     @OpenClaw 修改UI [修改意见] → 迭代修改"

人: @OpenClaw 修改UI "报告页面增加导出PDF按钮"
  → Agent 迭代修改 → 更新飞书文档 → 再次请求确认

人: @OpenClaw 确认UI
  → Bitable: 更新 UI 设计稿链接
```

##### 2.1.4 需求审查（需求审查 Agent）

```
人: @OpenClaw 进入审查

OpenClaw → 调用需求审查 Agent:
  → Bitable 状态: → REVIEWING
  → 读取: 需求文档 + UI 设计稿（如有）
  → 审查维度:
    1. 完整性: 模板字段是否全部填写
    2. 一致性: 输入/输出/验收标准之间是否矛盾
    3. 可测试性: 每条验收标准是否可量化验证（为 ACM 转化做准备）
    4. 历史冲突: 与 Bitable 中其他需求的边界是否重叠
    5. UI-需求对齐: UI 设计稿是否覆盖了所有使用场景（如有 UI）
  → 生成审查报告 → 写入飞书文档
  → 飞书卡片:
    "[需求审查] REQ-XXX-001 {需求名称}

     ✅ 完整性: 通过
     ✅ 一致性: 通过
     ⚠️ 可测试性: 建议明确 AC-002 的测量起止点
     ✅ 历史冲突: 无冲突
     ✅ UI对齐: 通过（或 N/A）

     📄 审查报告: [链接]

     [通过，进入规格层] [需要修改]"

人: 点击 [通过，进入规格层]
  → Bitable 状态: → REQ_APPROVED
  → 飞书文档: 追加版本标记 "v1 — 需求审查通过 {日期}"
  → 飞书群消息:
    "REQ-XXX-001 已通过需求审查 ✅
     下一步: 创建 Spec 分支，进入规格层-A
     建议分支名: spec/REQ-XXX-001
     📄 需求文档: [链接]
     📄 UI设计稿: [链接]（如有）"
```

#### Bitable 需求追踪表（全生命周期状态机）

| 字段 | 类型 | 说明 |
|------|------|------|
| req_id | 文本（主键） | REQ-RISK-001 |
| 名称 | 文本 | 需求名称 |
| 项目 | 单选 | 项目代号 |
| 状态 | 单选 | CREATED / DISCUSSING / UI_DESIGNING / REVIEWING / REQ_APPROVED / SPEC_DRAFTING / SPEC_LOCKED / HARNESS_GENERATING / HARNESS_READY / IMPLEMENTING / CI_PENDING / STAGING / DEPLOYED |
| 创建人 | 人员 | |
| 创建时间 | 日期 | |
| 需求文档 | 链接 | 飞书文档 URL |
| UI 设计稿 | 链接 | 飞书文档 URL（可选） |
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

#### REQ ID 跨层穿透映射

| 层 | 载体 | REQ ID 出现位置 |
|---|---|---|
| 需求层 | 飞书 Bitable | 主键字段 |
| 需求层 | 飞书文档 | 文档标题前缀 |
| 规格层-A | GitHub branch | `spec/REQ-{PROJECT}-{NNN}` |
| 规格层-A | Spec/ACM 文件 | `metadata.req_id` 字段 |
| 规格层-B | Harness PR | PR title 包含 REQ ID |
| 生成层 | GitHub branch | `impl/REQ-{PROJECT}-{NNN}` |
| 所有卡点 | 飞书卡片 | 卡片标题包含 REQ ID |

#### 飞书文档目录结构（项目→需求映射）

```
飞书文档空间/
├── {项目名-A}/
│   ├── REQ-PRJA-001 {需求名称}/
│   │   ├── 需求文档              ← OpenClaw 创建+引导填写
│   │   ├── UI设计稿（可选）       ← UI 设计 Agent 生成
│   │   └── 审查报告              ← 需求审查 Agent 生成
│   ├── REQ-PRJA-002 {需求名称}/
│   │   └── ...
│   └── ...
├── {项目名-B}/
│   └── ...
└── _模板/
    ├── 需求文档模板
    └── UI设计简报模板
```

#### 需求版本管理

| 操作 | 处理方式 |
|------|----------|
| 新需求 | @OpenClaw 创建需求 → 生成新 REQ ID |
| 需求修改（审查前） | 直接在文档中修改，状态不变 |
| 需求变更（审查后） | @OpenClaw 变更需求 REQ-XXX-001 → 复制文档为 v2 → 重新走讨论→审查 |
| Bug 修复（已上线） | 不走需求层，直接在 GitHub 开 PR |

---

### 2.2 规格层-A（Spec 子层）—— 需求层→GitHub 桥接

**目标**：将飞书中经审查的需求文档转化为 GitHub 中锁定的结构化 Spec + ACM。

> **设计原理：单向转化门**
>
> 需求写作（发散、频繁交互、飞书原生）和后续自动化（确定性、事件驱动、GitHub 管道）需要不同的工具。
> 强行统一会让写作阶段僵硬，或让自动化管道不可靠。
>
> 解决方案：飞书和 GitHub 不需要天然匹配，只需要一个**单向转化门**：
> - 飞书 = 需求空间（自由、发散、OpenClaw 驱动协作）
> - GitHub = 锁定空间（结构化、确定性、自动化管道）
> - 转化门 = 卡点1a，由人工桥接或半自动完成
> - 转化后 GitHub 是唯一权威，飞书需求文档添加版本标记但不再更新

| 项目 | 内容 |
|---|---|
| 输入 | 经审查的飞书需求文档 + UI 设计稿（状态 = REQ_APPROVED） |
| 输出 | 结构化 Spec（Markdown）+ ACM（YAML）+ API 契约（YAML，如有） |
| 人的工作 | 创建 spec 分支 → 将需求文档作为上下文 → 审核 AI 转化结果 |
| AI 的工作 | 将需求文档转化为结构化 Spec + ACM + 兼容性检查报告 |
| 自动化 | 卡点1a 确认后自动提交 GitHub |
| 索引 | 分支名: `spec/REQ-{PROJECT}-{NNN}`，Spec/ACM metadata 含 `req_id` |

#### 桥接流程（人工桥接 → 半自动化演进）

**Phase 1：人工桥接（当前实施）**

```
1. OpenClaw 通知: "REQ-XXX-001 需求审查通过，可进入规格层"
2. 开发者:
   → git checkout -b spec/REQ-XXX-001
   → 从飞书文档复制需求内容
   → 使用 Claude Code / AI 工具转化为:
     · docs/specs/{feature}-v{N}.md（结构化 Spec，metadata 含 req_id）
     · docs/specs/{feature}-v{N}-acceptance.yaml（ACM）
     · docs/specs/{feature}-v{N}-api.yaml（API 契约，如有）
   → git push → 创建 PR
3. 开发者通知: @OpenClaw spec已提交 REQ-XXX-001 PR#{N}
   → OpenClaw: Bitable 状态 → SPEC_DRAFTING，记录 PR 链接
   → 触发卡点1a 飞书卡片
```

**Phase 2：半自动化（后续实施）**

```
1. 人: @OpenClaw 创建Spec REQ-XXX-001
2. OpenClaw:
   → GitHub API: 创建分支 spec/REQ-XXX-001
   → 飞书 API: 读取需求文档 + UI 设计稿内容
   → 调用 Spec 转化 Agent: 需求文档 → Spec + ACM + API 契约
   → 读取 GitHub 历史 ACM → 兼容性检查报告
   → GitHub API: commit files + 创建 PR
   → Bitable: 状态 → SPEC_DRAFTING，记录 PR 链接
   → 触发卡点1a 飞书卡片
```

#### Spec 产物清单

规格层-A 产出以下文件，全部提交到 GitHub `docs/specs/`：

| 产物 | 文件名 | 用途 |
|------|--------|------|
| 结构化 Spec | `{feature}-v{N}.md` | 自然语言业务描述，解释"为什么和如何" |
| ACM（验收标准矩阵） | `{feature}-v{N}-acceptance.yaml` | 机器可读的验收标准，Harness 生成的直接输入 |
| API 契约 | `{feature}-v{N}-api.yaml` | OpenAPI 接口定义（如涉及接口） |

#### Spec 模板结构（`docs/specs/{feature}-v{N}.md`）

```markdown
## 问题描述
这个功能解决什么业务问题？

## 使用场景
用户在什么情况下触发，期望得到什么结果？

## 输入
明确列出所有输入数据及其格式。

## 输出
明确列出输出内容、格式、交付方式。

## 边界（不包含什么）
明确排除的功能范围。

## 验收标准（人工填写，不可省略）
- [ ] 标准1
- [ ] 标准2
（注：此处的文字版验收标准会由 AI 转化为 ACM YAML，两者必须一致）

## 非功能要求
性能、安全、合规等约束。

## 版本信息
- 版本：v{N}
- 基于版本：v{N-1}（如适用）
- Breaking Changes：无 / 列表
```

#### ACM（验收标准矩阵）完整 Schema

ACM 是连接"自然语言 Spec"和"可执行 Harness 测试"的结构化桥梁。它解决三个问题：
1. **消除歧义**：自然语言验收标准 → 机器可读的量化指标
2. **追溯链**：每个验收标准 ↔ 每个测试函数，一一对应
3. **版本兼容**：明确记录历史 AC 的继承和变更

```yaml
# docs/specs/{feature}-v{N}-acceptance.yaml

feature: risk-report           # 功能标识
version: 1                     # Spec 版本号
created_at: 2026-04-08         # 创建时间
locked_at: 2026-04-09          # 卡点1a 确认时自动填充

# ===== 核心验收标准 =====
acceptance_criteria:
  - id: AC-001                 # 全局唯一编号，跨版本不变
    title: "营业执照字段识别准确率"
    description: |
      系统应能从营业执照图片中准确提取以下字段：
      公司名称、注册号、成立日期。
      准确率 = 正确提取数 / 总字段数。

    # 量化标准（必须机器可验证）
    acceptance_metric: "准确率 >= 95%"
    measurement_unit: "percentage"
    baseline: 95               # 数字化通过线，Harness 生成 assert 的依据

    # 分类（用于 Harness 生成和 CI 调度）
    type: accuracy             # accuracy / performance / functional / security
    test_category: unit        # unit / integration / e2e
    environment: standard      # standard / production-like
    ci_enabled: true           # 是否在轻量 CI 中运行

    # 优先级和依赖
    priority: P0               # P0(必须) / P1(重要) / P2(次要)
    depends_on: []             # 依赖其他 AC，如 ["AC-002"]

    # 历史兼容性标记
    source_version: 1          # 本 AC 首次出现在哪个版本
    breaking_change: false     # 相对上一版本是否有破坏性变更

    # Harness 映射（卡点1b 后填充）
    test_file: ""              # 由规格层-B 生成后回填
    test_function: ""          # 由规格层-B 生成后回填

  - id: AC-002
    title: "报告生成时间性能"
    description: "完整风控报告从接收输入到返回 JSON 响应不超过 30 秒"
    acceptance_metric: "响应时间 <= 30秒"
    measurement_unit: "milliseconds"
    baseline: 30000
    type: performance
    test_category: integration
    environment: production-like   # 性能测试需要稳定环境
    ci_enabled: false              # 不在轻量 CI 跑，仅 Staging 验收
    priority: P0
    depends_on: []
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

  - id: AC-003
    title: "输出格式标准化"
    description: |
      生成的风控报告（JSON）必须符合 risk-report-schema-v1.json。
      包含字段：risk_level (HIGH/MEDIUM/LOW)、key_risks (array)、
      recommendation (APPROVE/REJECT/MANUAL_REVIEW)
    acceptance_metric: "Schema 验证通过率 100%"
    measurement_unit: "percentage"
    baseline: 100
    type: functional
    test_category: integration
    environment: standard
    ci_enabled: true
    priority: P0
    depends_on: []
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

  - id: AC-004
    title: "错误处理与降级"
    description: |
      OCR 识别失败或 LLM 分析异常时，返回有意义的错误信息。
      允许的失败场景：图片模糊(OCR_QUALITY_LOW)、
      无法识别(IDENTITY_EXTRACTION_FAILED)
    acceptance_metric: "所有预定义错误场景有正确的错误响应"
    measurement_unit: "count"
    baseline: 0    # 0 个未覆盖的错误场景
    type: functional
    test_category: unit
    environment: standard
    ci_enabled: true
    priority: P1
    depends_on: ["AC-001"]
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

# ===== 历史兼容性声明 =====
compatibility:
  inherits_from: []            # 本版本基于哪些历史版本（新功能为空）
  breaking_changes: []         # 本版本的破坏性变更列表
  impact_analysis: |           # AI 生成，人在卡点1a 确认时审核
    本次是新功能首次发布，无历史版本约束。
    后续 v2 需确保：AC-001 准确率不降低，AC-002 响应时间不增加。
  cross_feature_dependencies: []   # 与其他功能的交叉依赖

# ===== 元数据 =====
metadata:
  owner: "@daxin"
  business_context: "租赁风控"
  customer_impact: high
  compliance_requirements: ["数据隐私", "审计日志"]
  tags: ["风险管理", "OCR", "LLM集成"]
```

#### ACM 版本演进示例

当需求变更时（如 v2 改进性能要求并新增多语言支持）：

```yaml
# docs/specs/risk-report-v2-acceptance.yaml
feature: risk-report
version: 2

acceptance_criteria:
  # --- 继承自 v1（不变）---
  - id: AC-001
    # ... 同 v1 ...
    source_version: 1
    breaking_change: false

  # --- 继承自 v1（变更）---
  - id: AC-002
    title: "报告生成时间性能"
    acceptance_metric: "响应时间 <= 20秒"   # 从 30s 改为 20s
    baseline: 20000
    source_version: 1
    breaking_change: true   # 标记为 breaking

  # --- v2 新增 ---
  - id: AC-005
    title: "多语言报告支持"
    description: "输出报告支持中英文切换"
    source_version: 2
    breaking_change: false

compatibility:
  inherits_from: [1]
  breaking_changes:
    - ac_id: AC-002
      description: "响应时间从 30s 降至 20s"
      mitigation: "已评估，客户网络环境支持"
```

#### Spec 写作阶段的历史上下文注入

为了让写 Spec 的人在飞书草稿阶段就能看到历史约束，飞书文档模板会自动注入只读参考：

```
─── 历史约束参考（只读，由系统从 GitHub 拉取注入）───────
本功能可能影响以下历史验收标准：
• AC-003（v1）：输出格式必须兼容 risk-report-schema-v1.json
• AC-007（v2）：API 响应时间 <= 200ms
注意：以上约束已在 harness 中有覆盖，新 Spec 不得退化。
──────────────────────────────────────────────────────
```

#### Spec 版本管理规则

| 情况 | 处理方式 |
|------|----------|
| 现有功能报错 | 直接开 PR 修复，不需要新 Spec |
| 现有功能行为不符预期但测试通过 | Spec 验收标准写错了，需要新 Spec 版本 |
| 新增能力 | 新 Spec + 新 ACM |
| 性能改进 | 新 Spec 版本，ACM 中标记 `breaking_change: true` |

**⚡ 卡点1a（方案门）**：飞书发送确认卡片，包含：
- 结构化 Spec 全文预览
- ACM 验收标准清单
- 兼容性检查报告（与历史 ACM 的冲突点）
- 按钮：[确认提交] [返回修改]

确认后，Spec + ACM + API 契约自动提交到 GitHub `docs/specs/`，打 Git tag，进入版本控制。

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

#### ⓪ OpenClaw Agent 配置（v1.2 新增）

> 注：本节描述的是方法论 v1.2 的原始基线形态。
> 在本仓库当前落地方案中，主协调能力已下沉为独立的 `Coordinator Service`；
> OpenClaw 不再承担需求层主编排，而只承接 `author agent` / `review agent` 等智能角色。

**角色**：方法论原始基线中，OpenClaw 被视作飞书生态内的工作流编排器，驻扎在项目群。
当前实现建议中，该能力已拆分为 `Coordinator Service + OpenClaw author/reviewer`。

**部署方式**：OpenClaw 飞书插件 + WebSocket 长连接（与 checkpoint-handler 类似）

**所需 Skills**：

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

**OpenClaw 与 checkpoint-handler 分工**：

| 职责 | OpenClaw | checkpoint-handler |
|------|----------|-------------------|
| 覆盖层 | 需求层全流程 + 跨层状态同步 | 规格层-B → 交付层 |
| 运行环境 | 飞书群聊（OpenClaw 飞书插件） | 独立服务（飞书 WebSocket） |
| 状态存储 | Bitable 需求追踪表 | 无持久状态 |
| 交互方式 | @mention 对话式 + 飞书卡片 | 仅飞书卡片按钮回调 |
| GitHub 操作 | 创建分支/PR（半自动化阶段） | 合并 PR/触发部署 |
| 通知发送 | 需求层所有通知 | 卡点2/3 通知 |
| 卡点处理 | 卡点1a（方案门） | 卡点1b/2/3 |

**协作接口**：
- 卡点1a 确认后：OpenClaw 更新 Bitable → checkpoint-handler 接管后续卡点
- 卡点2/3 按钮回调：checkpoint-handler 处理 → 通知 OpenClaw 更新 Bitable 状态
- 通信方式：共享 Bitable 表（OpenClaw 写，checkpoint-handler 读/写状态字段）

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

四个卡点是两轨之间的唯一接口：

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

> 注：以下步骤属于方法论原始基线。
> 当前仓库的实现方向已经调整为：
> - `Coordinator Service` 负责飞书事件、状态机、Bitable 和工作流
> - OpenClaw 只作为 `author/reviewer` 的智能运行时
- 安装 OpenClaw 飞书插件
- 配置飞书连接（WebSocket 长连接）
- 安装官方 Skills: `feishu-doc`, `feishu-bitable-creator`, `feishu-automation`
- 开发并安装自定义 Skills: `requirement-writer`, `requirement-reviewer`, `ui-design-bridge`, `github-bridge`
- 在项目群中添加 OpenClaw Agent，配置 @mention 响应
  当前实现建议中，这一步会弱化为：
  - author agent 提供私聊需求构造入口
  - review agent 仅作为后台智能角色或定向交互角色
  - 项目群中的主要系统消息由 Coordinator Service 对应机器人发送

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

> 注：这里的原始路线图以“OpenClaw 驻扎项目群”作为主路径。
> 当前仓库对应的实现将调整为：
> - 创建群中 `@CoordinatorService` 创建需求
> - 用户私聊 author agent 完成需求构造
> - 项目群负责同步状态、审查通知与最终结果

**目标**：需求层在飞书内完全闭环，OpenClaw 驱动全流程。

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

## 附录B：全链路流程总图（v1.2 更新）

```
┌─────────────────────────────────────────────────────────────────┐
│              飞书需求空间（OpenClaw 驱动，飞书内闭环）              │
│                                                                 │
│  客户需求 → @OpenClaw 创建需求 → REQ-XXX-001                     │
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

Bitable 需求追踪表全程记录状态（OpenClaw + checkpoint-handler 协作更新）
```

## 附录C：自研工具完成状态（v1.2 更新）

| # | 工具 | 状态 | 位置 |
|---|------|------|------|
| 1 | 飞书通知脚本 | ✅ 完成 | `scripts/notify_feishu.py` |
| 2 | 卡点响应处理器 | ✅ 完成 | `services/checkpoint-handler/` |
| 3 | AI 失败分析脚本 | ✅ 完成 | `scripts/analyze_failure.py` |
| 4 | 项目回顾生成器 | □ 待建 | — |
| 5 | 客户部署脚本 | ✅ 完成 | `deploy/deploy.sh` |
| 6 | Spec 转化服务 | □ 待建 | — |
| 7 | spec-to-harness workflow | □ 待建 | `.github/workflows/spec-to-harness.yml` |
| 8 | harness-confirmed workflow | □ 待建 | `.github/workflows/harness-confirmed.yml` |
| 9 | ACM 兼容性检查脚本 | □ 待建 | — |
| 10 | OpenClaw Skill: requirement-writer | □ 待建 | OpenClaw custom skill |
| 11 | OpenClaw Skill: requirement-reviewer | □ 待建 | OpenClaw custom skill |
| 12 | OpenClaw Skill: ui-design-bridge | □ 待建 | OpenClaw custom skill |
| 13 | OpenClaw Skill: github-bridge | □ 待建 | OpenClaw custom skill |

---

*版本：v1.2 | 日期：2026-04-08*
*v1.2 变更：OpenClaw 集成、需求层四阶段子流程、Bitable 状态机、REQ ID 跨层穿透*
*v1.1 变更：规格层拆分、ACM 引入、四卡点模型、两阶段流程设计*
*下一步：Phase 1 — OpenClaw + 飞书工作流基础设施建设*
