# 规格层与项目级上下文设计
## 2026-04-14

> 本文档沉淀以下讨论结论：
> 1. 需求文档 → Spec → Harness → AI 实现 的完整链路设计（问题一）
> 2. UI 能力的完整融入方案（问题三）
> 3. 项目级上下文框架（防漂移核心基础设施，连接问题一/二/三）
>
> 防漂移机制（问题二）的完整设计留待后续独立讨论。

---

## 一、设计背景与核心目标

### 1.1 核心目标

以经过双闸门确认的需求文档为起点，通过一套可重复执行的规格生成流程，产出足够精确的技术约定，使 AI Coding Agent 能够自主、稳定、符合架构约束地完成实现，无需人在实现过程中持续介入。

### 1.2 现有需求层的产物

需求层（Coordinator Service）已完成，产出：
- 状态机：`CREATED → DRAFTING → AI_REVIEW → HUMAN_CONFIRM → FINAL_REVIEW → APPROVED`
- 产物：经 Author + Reviewer 双 Agent 协作、人工双闸门确认的结构化需求文档（飞书）
- 字段：问题描述、使用场景、输入、输出、边界、验收标准、非功能要求

### 1.3 已识别的核心问题

- 需求文档描述"用户要什么"，规格层需要描述"系统怎么建"——这中间有本质跃迁
- 没有接口契约、数据模型、架构接合点，AI Coding Agent 只能靠猜
- 没有跨需求的知识积累机制，每次迭代 AI 从零推导，架构漂移不可避免
- UI 设计缺乏明确的流程位置，高保真视觉产物没有生命周期管理

---

## 二、SDD 方案：需求文档 → Spec → Harness → 实现

### 2.1 链路总览

整个链路分三个站点（Station），人工介入点仅有两处（卡点1a、卡点1b）：

```
Station 1：需求层（飞书，Coordinator Service）
  产物：APPROVED 需求文档
  人工卡点：HUMAN_CONFIRM + FINAL_REVIEW（现有）

      ↓ APPROVED 触发（需要UI = true 时先经过 UI 设计阶段）

[UI 设计阶段]（需要UI = true）
  产物：经确认的高保真可运行 UI 原型
  人工卡点：设计确认（视觉 + 交互全貌）

      ↓ 设计确认 / 跳过（需要UI = false）

Station 2：Spec 生成（GitHub，新增）
  注入上下文：ARCHITECTURE.yaml + 历史 ACM 注册表 + 设计系统快照
  产物：四层 Spec（Requirements + Design + ACM + Tasks）
  人工卡点：卡点1a（Design 层 review）

      ↓ 卡点1a 通过

Station 3：实现层（GitHub，AI Coding Agent）
  Harness 生成（自动，卡点1b 前）
  人工卡点：卡点1b（测试覆盖确认）
  AI Coding Agent 实现，直到所有 P0 Harness 通过
```

### 2.2 需求文档格式升级（Station 1 小幅变更）

现有 7 字段整体保留，做以下定向升级：

#### 2.2.1 输入 / 输出：从描述升级为半结构化契约

**升级前（允许）：**
```
输入：用户上传营业执照图片和征信报告
```

**升级后（要求）：**
```
输入：
  - license_image: 图片文件，支持 jpg/png，最大 5MB
  - credit_report: JSON 对象，包含 applicant_id（string）和 credit_score（number）
```

不要求完整 OpenAPI schema，要求字段名 + 类型 + 主要约束。Author Agent 负责在对话中引导用户补全到这个粒度。

#### 2.2.2 验收标准：从条件描述升级为可测试断言

每条 AC 必须能回答：用什么输入、期望什么输出、怎么判断通过。

**升级前（允许）：**
```
系统应准确分析申请人资质
```

**升级后（要求）：**
```
- 给定完整营业执照和征信数据，生成的风控报告中 risk_level 字段必须存在且为 low/medium/high 之一
- 给定缺失 credit_score 的输入，系统返回 422 + error_code: MISSING_CREDIT_SCORE
```

Reviewer Agent 需新增可测试性审查维度：含糊的 AC 必须退回，不允许进入 AI_REVIEW。

#### 2.2.3 新增字段：技术范围声明

```
技术范围：
  - 涉及现有模块：[现有服务/模块名称]
  - 操作类型：新增接口 / 修改现有接口 / 纯数据处理
  - 数据持久化：是否需要新增/修改数据表
  - 对外依赖：调用哪些第三方服务
```

这是 Design 层生成的必要输入。Author Agent 从 ARCHITECTURE.yaml 拉取现有模块列表供用户勾选，降低填写成本。技术范围为空时 Reviewer Agent 退回。

### 2.3 Spec 四层结构（Station 2 核心产物）

Spec 存储于 GitHub `spec/REQ-{PROJECT}-{NNN}/` 目录，包含四个层：

```
spec/REQ-PROJECT-001/
  requirements.md       ← Layer 1
  design.md             ← Layer 2（唯一人工 review 层）
  design-ui.md          ← Layer 2 UI 技术规格（需要UI = true 时）
  acceptance.yaml       ← Layer 3 ACM
  tasks.md              ← Layer 4
```

#### Layer 1：Requirements（自动生成，无需人工 review）

从需求文档 7 字段自动转换为 EARS 格式用户故事：

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

#### Layer 2：Design（AI 生成 + 卡点1a 人工 review）

**这是整个链路唯一需要深度人工判断的层。**

注入上下文：ARCHITECTURE.yaml + 技术范围声明

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
  - score: integer
  - created_at: timestamp

## 架构接合点
- 在 risk-assessment-service 新增 /api/v1/risk-report 路由
- 复用 license-parser 模块（已有，无需新建）
- 调用 third-party-credit-api（已有封装，在 CreditDataGateway）

## 兼容性影响
[由 ACM 注册表兼容性检查自动生成]
- 无影响：该接口为全新接口，不修改现有接口
```

若 `需要UI = true`，同时生成 `design-ui.md`：

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

#### Layer 3：ACM（自动生成，人可否决）

```yaml
req_id: REQ-PROJECT-001
spec_version: 1

acceptance_criteria:
  - id: AC-001
    priority: P0
    description: "有效输入返回风控报告"
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

  - id: AC-002
    priority: P0
    description: "缺失 credit_score 返回 422"
    input:
      license_image: "valid.jpg"
      credit_report: { applicant_id: "u001" }
    expected:
      status: 422
      body:
        error_code: "MISSING_CREDIT_SCORE"
    test_type: integration
```

#### Layer 4：Tasks（自动生成，按依赖排序）

```markdown
## 实现任务

### Task-1：数据模型
- 新建 risk_reports 表 migration（见 design.md 数据模型）
- 对应 AC：无（基础设施）

### Task-2：接口实现
- 在 risk-assessment-service 实现 POST /api/v1/risk-report
- 调用 license-parser 模块和 CreditDataGateway
- 对应 AC：AC-001

### Task-3：错误处理
- 实现输入校验和错误返回
- 对应 AC：AC-002

### Task-4：前端页面（需要UI = true）
- 实现 RiskReportPage（见 design-ui.md）
- 基于设计系统快照中现有组件
- 对应 AC：AC-UI-001
```

### 2.4 Harness 生成（Station 3，卡点1b 前）

从 ACM 自动生成可执行测试代码，结构：

```
harness/tests/
  REQ-PROJECT-001/
    AC-001_valid_input/
      test_case.py        ← 从 ACM 生成
      fixtures/input.json ← 从 AC expected input 生成
    AC-002_missing_score/
      test_case.py
```

P0 级 AC 对应的 Harness 测试必须全部通过，Impl PR 才能合并。

---

## 三、UI 能力完整融入方案

### 3.1 UI 在整个流程中的两个形态

| 阶段 | 形态 | 目的 | 受众 |
|---|---|---|---|
| HUMAN_CONFIRMING（需求层） | 低保真线框图 | 验证 AI 理解需求方向是否正确 | 需求发起人（人） |
| UI 设计阶段（APPROVED 后） | 高保真可运行原型 | 视觉/交互全貌确认，产出 UI 技术合同 | 产品/设计负责人（人）+ Coding Agent（机器） |

两者目的不同，不能合并。前者是"沟通验证"，后者是"技术合同"。

### 3.2 UI 设计阶段详细设计

**触发条件**：REQ APPROVED 且 `需要UI = true`

**输入**：
- 需求文档（7 字段，含低保真线框图链接）
- 项目设计系统文档（Coordinator 从飞书读取）
- 现有 UI 组件库（设计系统文档中的组件清单）

**AI 生成内容**（以可运行前端代码为高保真形态，非静态图片）：
- 所有关键页面/视图的可交互原型（React/Vue 组件，可在浏览器中运行）
- 核心状态的完整展示：空状态、加载态、错误态、成功态
- 完整用户流程走一遍：主路径 + 主要异常路径
- 设计决策说明：每个关键视觉/交互选择的理由

**人工 review 内容**：
- 视觉是否符合产品预期
- 交互是否符合用户习惯
- 与已有界面风格是否一致（对照设计系统文档）
- 边界状态是否处理完整

**迭代机制**：
- 设计 Agent 根据 review 意见修改原型
- 直到产品/设计负责人确认"这就是要做的"
- 确认后 Coordinator 更新设计系统文档（append-only）

**产物**：
- 高保真原型代码（存入飞书文档，同时作为 Coding Agent 的视觉参考）
- 设计决策记录（append 进项目设计系统文档）

### 3.3 高保真 UI 产物的流向

```
UI 设计阶段产物（高保真原型代码）
  ↓
进入 Spec 生成
  → 从原型提取 UI 技术规格（组件树/接口/状态机）→ design-ui.md
  → 无需 AI 凭空推导 UI 结构，直接从确认的原型提取
  ↓
Coding Agent 实现
  · 视觉参考：高保真原型代码（直接可复用或参考）
  · 接口约束：design-ui.md（组件接口定义）
  · 完成标准：视觉回归测试（Playwright）
```

### 3.4 视觉回归测试（UI 层的 Harness）

每次 Impl PR 合并触发视觉回归测试：
- 对比当前渲染 vs 上一次通过的截图基线
- 超过阈值 → PR 阻断
- 作用：防止 Coding Agent 实现时悄悄改动组件样式

---

## 四、项目级上下文框架

### 4.1 定义

项目级上下文是一个项目在整个生命周期中积累的、跨 session 持久存在的结构化知识，使得任何 agent（对话式或编码式）在任何时刻介入，都能理解"这个项目现在是什么状态、已经做了哪些决定、约束是什么"，而不需要从头推导。

### 4.2 五层内容

#### Layer 1：功能契约层（What the system promises）

| 产物 | 内容 |
|---|---|
| ACM 注册表 | 所有已批准需求的验收条件矩阵（consolidated.yaml） |
| REQ 索引 | 所有 REQ 的状态、文档链接、spec 位置 |

**防止**：功能漂移（新 Spec 与已有功能契约冲突）

#### Layer 2：架构快照层（How the system is built）

| 产物 | 内容 |
|---|---|
| ARCHITECTURE.yaml | 服务/模块、公开接口、数据模型、外部依赖 |
| ADR 归档 | 关键架构决策及原因（docs/decisions/ADR-xxx.md） |

**防止**：架构漂移（新实现破坏已有架构约定）

#### Layer 3：视觉规范层（How the system looks）

| 产物 | 内容 |
|---|---|
| 项目设计系统文档 | Token、组件库、交互模式、视觉决策日志（飞书文档） |
| 设计系统快照 | 上述文档在 Spec 生成时的 GitHub 导出版本 |

**防止**：视觉漂移（新 UI 与已有界面风格不一致）

#### Layer 4：规范惯例层（How we build things）

| 产物 | 内容 |
|---|---|
| CLAUDE.md | 编码规范、命名约定、已知陷阱（热加载） |
| 技术栈声明 | 语言、框架、版本约定 |

**防止**：代码风格漂移（AI 每次 session 自动加载）

#### Layer 5：需求历史层（What has been decided）

| 产物 | 内容 |
|---|---|
| 需求文档集 | 所有 REQ 的飞书文档 |
| UI 原型集 | 每个 REQ 经确认的高保真 UI 原型 |

**作用**：新需求构造时的历史背景参考

### 4.3 双平面存储模型

```
飞书平面（人工协同轨）
  ├── 需求文档集（Layer 5）
  ├── UI 原型集（Layer 5）
  └── 设计系统文档（Layer 3）
  
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

### 4.4 管理职责分工

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

### 4.5 事件驱动更新表

| 触发事件 | 更新内容 | 更新者 |
|---|---|---|
| REQ 创建 | REQ 索引新增条目 | Coordinator |
| REQ APPROVED | REQ 索引状态更新 | Coordinator |
| UI 设计确认 | 设计系统文档 append（飞书） | Coordinator |
| Spec 生成（卡点1a 通过） | ACM 注册表新增条目；设计系统快照导出 GitHub | Coordinator 触发，checkpoint-handler 执行 |
| Harness 通过（卡点1b） | ACM 注册表该条目标记 finalized | checkpoint-handler |
| Impl PR 合并 | ARCHITECTURE.yaml 更新（如有接口变更） | checkpoint-handler Hook |
| 架构决策发生 | ADR 新增文档 | 人工写入 |

**核心原则：所有更新 append-only，可追溯到触发它的 REQ ID。**

### 4.6 生产与消费矩阵

```
                    生产位置              消费者
Layer 1 ACM注册表   GitHub（Spec生成时）  Spec Agent（兼容性检查）
                                         AI Coding Agent（了解现有契约）
Layer 2 架构快照    GitHub（Impl合并时）  Spec Agent（Design层生成）
                                         AI Coding Agent（架构接合点）
Layer 3 设计系统    飞书（UI确认时）      UI设计Agent（新UI生成时注入）
  ↓快照             GitHub（Spec生成时）  AI Coding Agent / 视觉回归CI
Layer 4 CLAUDE.md   GitHub（人工维护）   AI Coding Agent（每session热加载）
Layer 5 需求文档    飞书（Coordinator）  Author Agent（历史背景）
                                         Spec Agent（需求内容读取）
```

### 4.7 冷热内存模型

参考 Codified Context 论文（arXiv 2602.20478），上下文按访问频率分层：

**热（每次 session 自动加载）：**
- CLAUDE.md（编码规范）
- ARCHITECTURE.yaml（当前架构）
- 当前 REQ 的 Spec（Requirements + Design + Tasks）
- design-system-snapshot.yaml（需要UI = true 时）

**温（按 REQ 加载）：**
- 当前 REQ 的 ACM
- 与当前 REQ 技术范围有重叠的历史 ACM 条目

**冷（按需查询）：**
- 完整 ACM 注册表（兼容性检查时）
- 设计系统完整历史（UI 决策追溯时）
- ADR 归档（架构决策参考时）

---

## 五、方法论 v1.3 需要更新的位置

基于本次设计，v1.3 方法论文档需要在以下位置做实质更新：

### §1.4（新增）：项目级上下文

引入项目级上下文作为贯穿全链路的基础概念，内容见本文第四章。

### §2.1（更新）：需求层

- 需求文档格式升级（见本文 2.2）
- UI 设计阶段正式纳入流程（APPROVED 后、Spec 生成前）
- Author Agent 引导策略更新（半结构化输入/输出、技术范围声明）
- Reviewer Agent 审查策略更新（可测试性维度、技术范围非空校验）

### §2.2（全新）：规格层-A（Spec 生成）

- 四层 Spec 结构（见本文 2.3）
- 卡点1a 对应 Design 层人工 review
- 必须注入的三类上下文：ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照
- 设计系统快照导出到 GitHub

### §2.3（更新）：规格层-B（Harness）

- ACM 作为 Harness 生成的唯一输入
- 视觉回归测试（Playwright）作为 UI 层 Harness 的对等机制
- P0 AC 对应测试全通过作为 Impl PR 合并门槛

### §五（新增）：项目级上下文基础设施

- Coordinator 和 checkpoint-handler 的职责分工
- 各类上下文产物的格式规范
- 更新事件触发表
- 冷热内存模型

---

## 六、开放问题（留待后续讨论）

1. **防漂移机制（问题二）**：ARCHITECTURE.yaml 的具体结构；ACM 注册表的兼容性检查流程；回归 Harness 与现有 CI 的集成方式

2. **Coordinator Service 扩展**：如何支持设计系统文档的管理；跨轨道上下文同步的具体实现

3. **checkpoint-handler 扩展**：ACM 注册表维护 Hook；ARCHITECTURE.yaml 更新触发机制

4. **冷启动策略**：项目第一个 REQ 时，设计系统文档如何初始化；ARCHITECTURE.yaml 如何建立初始版本

5. **UI 设计 Agent 选型**：高保真原型生成的具体工具和能力评估
