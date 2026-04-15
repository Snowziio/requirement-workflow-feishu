# 项目级上下文产物规格

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §3.2 项目级上下文的产物规格文档。
> 描述各层产物的存储路径、文件格式、更新触发规则。

---

## 一、ARCHITECTURE 文档格式与生命周期

> **定位**（Pre-Phase-2 校准）：ARCHITECTURE 是 **Spec 层的核心产出物之一**，不是前置基础设施。每个项目一份飞书文档，跨 REQ 共享、随每条 REQ 的 Spec 迭代演化，与需求文档、设计系统文档位于同一平面。GitHub 侧不再维护 ARCHITECTURE.yaml 镜像（Harness/Impl 层未来若需消费，再走 Spec 生成时的快照导出机制，类比设计系统快照）。

### 存储与总体生命周期

- **存储位置**：飞书项目级 docx，`document_id` 登记在 Coordinator 的 `project_configs.architecture_doc_id`
- **权威来源**：始终以飞书文档最新 revision 为准；Coordinator 持有 URL 与最近一次写后 revision 作为状态元数据，不缓存文档内容
- **诞生**：项目**首条 REQ 进入 Spec 阶段**（APPROVED → SPEC_DRAFTING 过渡）时，Coordinator 以类目模板（template_version）为骨架创建飞书文档；不需要独立的 bootstrap/onboarding 流程
- **演化**：每条 REQ 的 Spec 阶段，spec-author Agent 通过 `/queries/openclaw/spec-context` 端点获取当前 revision 与 context_token → `feishu_fetch_doc` 读取当前 YAML → 基于本次 Spec 决策做增量合并 → `feishu_update_doc` 覆盖写回 → 再次拉 revision → 在 `spec-submit` callback 回传 context_token 与写后 revision（详见 [context-chain-principle.md §七](context-chain-principle.md#七并发写回契约)）
- **冻结**：无。ARCHITECTURE 永远随项目演进
- **原生版本历史**：依赖飞书 docx 的原生 revision 机制追溯；不再需要 GitHub commit 历史兜底

### 更新责任边界（防漂移）

| 操作 | 允许的责任方 | 禁止的责任方 |
|---|---|---|
| 首次创建骨架文档 | Coordinator（首条 REQ 进入 SPEC_DRAFTING 时自动） | 任何 Agent、任何 Hook、人工手建 |
| 新增 / 修改 service / module / data_model 条目 | **spec-author Agent**（在 Spec 阶段按增量合并规则写回） | spec-reviewer、requirement-author、人工直接编辑飞书文档 |
| 修改 `introduced_in` / `spec_version` 字段 | spec-author Agent | 所有其他 |
| 变更 `tech_stack` | 人工（通过类目模板升级或独立飞书文档编辑，需技术负责人确认） | 任何 Agent |
| 删除条目 | 人工（独立编辑 + 理由记录在飞书评论） | 任何 Agent |
| 校核 | spec-reviewer Agent 在 Spec 审查时比对 Spec §8.2「项目级上下文消费声明」是否如实引用当前 ARCHITECTURE 片段 | — |

### 并发安全

ARCHITECTURE 是**唯一跨 REQ 共享的项目级飞书产出物**，并发保护走 context_token + revision round-trip 握手。Coordinator 在 `spec-submit` 校验失败（`token_invalid` / `revision_conflict`）时拒绝状态推进，Agent 必须重读 ARCHITECTURE 后再提交。

### 格式示例

```yaml
# ARCHITECTURE.yaml
# 维护者：checkpoint-handler（自动更新）+ 人工（首次建立）
# 更新策略：每次 Impl PR 合并后，checkpoint-handler 读取 design.md 判断是否有变更，有则更新

version: "2026-04-14"
project: risk-assessment-platform

services:
  - name: risk-assessment-service
    description: "风控报告生成服务，核心业务逻辑"
    repo_path: "src/risk_assessment/"
    public_interfaces:
      - method: POST
        path: /api/v1/risk-report
        request:
          license_image: "File（jpg/png，max 5MB）"
          credit_report: "JSON { applicant_id: string, credit_score: number }"
        response:
          risk_level: "enum(low|medium|high)"
          score: "integer(0-100)"
          report_id: "UUID"
        errors:
          - code: 422
            reason: MISSING_CREDIT_SCORE
          - code: 422
            reason: INVALID_LICENSE
          - code: 500
            reason: ANALYSIS_FAILED
        introduced_in: REQ-PROJECT-001
        spec_version: 1

modules:
  - name: license-parser
    description: "营业执照 OCR 解析模块"
    repo_path: "src/license_parser/"
    public_api:
      - function: parse_license_image
        input: "image_bytes: bytes"
        output: "LicenseData | ParseError"
    introduced_in: REQ-LEGACY-001
    status: stable

  - name: CreditDataGateway
    description: "征信数据网关，封装第三方信用评估 API"
    repo_path: "src/credit_gateway/"
    public_api:
      - function: get_credit_data
        input: "applicant_id: str, credit_score: float"
        output: "CreditReport | GatewayError"
    introduced_in: REQ-LEGACY-002
    status: stable

data_models:
  - name: risk_reports
    description: "风控报告记录表"
    columns:
      id: "UUID, primary key"
      applicant_id: "VARCHAR(64), FK → users.id"
      risk_level: "ENUM(low, medium, high)"
      score: "SMALLINT(0-100)"
      report_data: "JSONB"
      created_at: "TIMESTAMP WITH TIME ZONE"
    introduced_in: REQ-PROJECT-001
    spec_version: 1

external_dependencies:
  - name: third-party-credit-api
    description: "外部征信查询 API"
    gateway: CreditDataGateway（上方模块）
    introduced_in: REQ-LEGACY-002

tech_stack:
  language: Python 3.12
  framework: FastAPI 0.110
  database: PostgreSQL 15
  orm: SQLAlchemy 2.0
  test_framework: pytest 8.0

# ---- 以下为 v2.0 新增节（AI 集成登记 / 硬约束清单 / IM 平台集成） ----
# 所有 ID 命名空间：
#   AC-xxx = Acceptance Criterion（验收标准，位于 acceptance.yaml，不在本文件）
#   KC-xxx = Known Constraint（硬约束条目，位于本文件 known_constraints 节）
# 注：ACM = Acceptance Criteria Matrix，即 acceptance.yaml 的整体；
#     AC 与 KC 是两套独立命名空间，不得复用。

ai_integrations:
  # 登记每个 AI 能力消费点。运行时配置（token 预算 / 限流 / 重试参数）
  # 由各 Agent 自身配置管理，不进入本 yaml。
  - name: spec-author
    provider: openclaw           # openclaw | anthropic_api | openai | aliyun_qianwen | ...
    model: claude-sonnet-4-6
    purpose: "Spec 9 节撰写"
    consumer_module: spec-author-agent
    prompt_source: "docs/agents/spec-author/SKILL.md"
    fallback: "none"             # 或另一个 provider 标识
    introduced_in: REQ-HARNESS-002

known_constraints:
  # 业务/合规/架构硬约束。spec-reviewer 审查 Spec 时必须把每条
  # Spec 内容与本清单比对，违反即阻断。
  - id: KC-001
    category: compliance         # compliance | performance | architecture | business
    statement: "所有用户凭证必须经飞书 tenant_access_token 签发，禁止本地存储明文"
    source: "外部合规要求"        # REQ-xxx / 外部合规要求 / 技术决策记录
    affects: [risk-assessment-service, credit-gateway]
  - id: KC-002
    category: architecture
    statement: "Agent 不得直接读写 Bitable，状态变更一律通过 Coordinator callback"
    source: REQ-LEGACY-002
    affects: [spec-author-agent, spec-reviewer-agent, requirement-author-agent]

external_integrations:
  # 企业 IM / 协作平台的集成登记。与 external_dependencies（第三方 API）区分：
  # external_integrations 描述"本项目嵌入哪些协作平台"，
  # external_dependencies 描述"本项目调用哪些外部业务 API"。
  - platform: feishu              # feishu | wecom | dingtalk
    app_id: "<APP_ID_PLACEHOLDER>"  # 模板中占位，实例化部署时填真实值
    scopes: [docx:document, im:message, bitable:app, contact:user.id:readonly]
    webhook_endpoints: [/callbacks/feishu/event]
    introduced_in: REQ-HARNESS-001
```

**data_models 节字段增强**：`data_models[*]` 除既有 `columns` / `introduced_in` / `spec_version` 外，新增两个可选字段，帮助 Coding Agent 生成方案时不猜测存储形态：

```yaml
data_models:
  - name: risk_reports
    storage: postgres             # postgres | mysql | redis | s3 | feishu_bitable | local_file
    retention: "180d"             # 保留策略：固定时长 / "permanent" / "until_req_closed"
    # 以下字段保持原有语义
    columns: { ... }
    introduced_in: REQ-PROJECT-001
    spec_version: 1
```

---

## 二、ACM 注册表格式

存储于 `spec/registry/consolidated.yaml`，由 checkpoint-handler 在卡点1a 通过时追加，卡点1b 通过时标记 finalized。

```yaml
# spec/registry/consolidated.yaml
# 维护者：checkpoint-handler（自动更新）
# 更新策略：append-only，每条记录可追溯到 REQ ID

last_updated: "2026-04-14"

registry:
  - req_id: REQ-PROJECT-001
    spec_version: 1
    title: "风控报告生成"
    status: finalized          # drafting | locked | finalized
    locked_at: "2026-04-14"    # 卡点1a 通过时间
    finalized_at: "2026-04-15" # 卡点1b 通过时间
    spec_path: "spec/REQ-PROJECT-001/acceptance.yaml"
    acceptance_criteria:
      - id: AC-001
        priority: P0
        title: "有效输入返回风控报告"
        test_file: "harness/tests/REQ-PROJECT-001/AC-001_valid_input/test_case.py"
        test_function: "TestAC001ValidInput::test_returns_200_with_valid_fields"
      - id: AC-002
        priority: P0
        title: "缺失 credit_score 返回 422"
        test_file: "harness/tests/REQ-PROJECT-001/AC-002_missing_credit_score/test_case.py"
        test_function: "TestAC002MissingCreditScore::test_returns_422"
      - id: AC-003
        priority: P0
        title: "无效营业执照返回 422"
        test_file: "harness/tests/REQ-PROJECT-001/AC-003_invalid_license/test_case.py"
        test_function: "TestAC003InvalidLicense::test_returns_422"
      - id: AC-UI-001
        priority: P0
        title: "提交中 SubmitButton 禁用"
        test_file: "harness/tests/REQ-PROJECT-001/visual/test_visual_regression.py"
        test_function: "TestVisualRegression::test_submitting_state"
```

**兼容性检查**：新 Spec 生成时，checkpoint-handler 扫描 consolidated.yaml，找出与新 ACM 有潜在冲突的历史 AC 条目，生成 impact analysis 注入卡点1a 卡片。

---

## 三、设计系统文档结构（飞书）

飞书文档，由 Coordinator Service 管理，append-only 更新，不允许删改历史记录。

```markdown
# {项目名} 设计系统
> 维护者：Coordinator Service（自动 append）+ 人工（初始建立）
> 更新策略：每次 UI 设计确认时 append 新记录，不修改历史

## 一、设计 Token

### 颜色
| Token | 值 | 用途 |
|---|---|---|
| color-risk-low | #22C55E | 低风险标签 |
| color-risk-medium | #F97316 | 中风险标签 |
| color-risk-high | #EF4444 | 高风险标签 |
| color-primary | #3B82F6 | 主按钮 |

### 间距
| Token | 值 |
|---|---|
| spacing-xs | 4px |
| spacing-sm | 8px |
| spacing-md | 16px |
| spacing-lg | 24px |

### 字体
| Token | 值 |
|---|---|
| font-body | 14px / 1.5 |
| font-heading | 18px / bold |

## 二、组件库

### 已有组件（可直接复用）

| 组件名 | 文件路径 | Props | 说明 |
|---|---|---|---|
| PrimaryButton | src/components/PrimaryButton.tsx | `{ label, onClick, loading?, disabled? }` | 主操作按钮，loading 状态自带 spinner |
| FileUploader | src/components/FileUploader.tsx | `{ accept, maxSizeMB, label, onFileSelected }` | 文件上传，内置大小和格式校验 |
| ValidationMessage | src/components/ValidationMessage.tsx | `{ message, type: 'error'｜'warning'｜'info' }` | 表单内联错误提示 |
| PageHeader | src/components/PageHeader.tsx | `{ title, breadcrumb? }` | 页面顶部标题栏 |

### REQ-PROJECT-001 新增组件（2026-04-14）

| 组件名 | 文件路径 | Props | 说明 | 引入需求 |
|---|---|---|---|---|
| RiskBadge | src/components/RiskBadge.tsx | `{ level: 'low'｜'medium'｜'high' }` | 风险等级彩色标签，使用 color-risk-* Token | REQ-PROJECT-001 |
| CreditReportInput | src/components/CreditReportInput.tsx | `{ onValidChange: (data) => void }` | 征信数据录入表单，内置校验 | REQ-PROJECT-001 |
| ScoreDisplay | src/components/ScoreDisplay.tsx | `{ score: number }` | 分数数字展示，0-100 进度条样式 | REQ-PROJECT-001 |

## 三、交互模式

### 表单提交模式
状态机：idle → submitting → success｜error
- idle：所有表单元素可用
- submitting：提交按钮和上传控件禁用，显示 loading
- success：隐藏表单，展示结果区域
- error：显示错误提示，恢复 idle（可重试）

此模式已在 RiskReportPage 落地（REQ-PROJECT-001），后续涉及表单提交的页面应遵循相同模式。

## 四、设计决策日志

### 2026-04-14（REQ-PROJECT-001）

**决策**：风险等级标签使用颜色编码而非文字说明

**背景**：需要让用户在扫视时快速识别风险等级，不能只靠文字

**决定**：低（绿）/ 中（橙）/ 高（红），与行业惯例保持一致

**注意**：后续新增任何包含"风险"概念的 UI，必须使用相同颜色 Token，不能自定义颜色

---

**决策**：RiskReportPage 不显示详细报告内容，只展示汇总（risk_level + score）

**背景**：详细报告数据量大，移动端不适合展示全部；同时详细报告有独立查看场景

**决定**：当前版本只展示汇总，通过 report_id 跳转查看详情（详情页为后续需求）

**注意**：report_id 必须在响应中返回，即使当前版本的详情页尚未实现
```

---

## 四、设计系统快照格式（GitHub）

存储于 `specs/design-system-snapshot.yaml`，由 Coordinator Service 在 Spec 生成时从飞书设计系统文档导出。供 AI Coding Agent 在编码时消费（热加载）。

```yaml
# specs/design-system-snapshot.yaml
# 维护者：Coordinator Service（在 Spec 生成时导出）
# 注意：这是快照，最新版本在飞书设计系统文档中

exported_at: "2026-04-14"
source_doc_id: "飞书文档 ID"

tokens:
  colors:
    color-risk-low:    "#22C55E"
    color-risk-medium: "#F97316"
    color-risk-high:   "#EF4444"
    color-primary:     "#3B82F6"
  spacing:
    spacing-xs: "4px"
    spacing-sm: "8px"
    spacing-md: "16px"
    spacing-lg: "24px"

existing_components:
  - name: PrimaryButton
    path: src/components/PrimaryButton.tsx
    props: "{ label: string, onClick: () => void, loading?: boolean, disabled?: boolean }"
    reuse_guidance: "所有主操作按钮使用此组件，不要自建"

  - name: FileUploader
    path: src/components/FileUploader.tsx
    props: "{ accept: string, maxSizeMB: number, label: string, onFileSelected: (file: File) => void }"
    reuse_guidance: "所有文件上传场景使用此组件"

  - name: ValidationMessage
    path: src/components/ValidationMessage.tsx
    props: "{ message: string, type: 'error' | 'warning' | 'info' }"
    reuse_guidance: "表单内联错误提示统一使用此组件，不要用其他方式显示错误"

interaction_patterns:
  - name: form-submit-state-machine
    description: "表单提交状态机：idle → submitting → success|error"
    guidance: "所有涉及表单提交的页面必须遵循此状态机，确保 submitting 时控件禁用"
```

---

## 五、事件驱动更新完整表

| 触发事件 | 更新的产物 | 执行者 | 更新策略 |
|---|---|---|---|
| REQ 创建 | Bitable REQ 索引（新增条目） | Coordinator | 写入 |
| 需求字段更新（每轮讨论） | 飞书需求文档（section-level 幂等重写） | Coordinator（onExit DRAFTING Hook） | 幂等替换 |
| REQ APPROVED | Bitable REQ 索引（状态更新） | Coordinator | 更新字段 |
| UI 设计第二阶段确认 | 飞书设计系统文档（append 新组件 + 决策日志） | Coordinator | Append-only |
| UI 设计第二阶段确认 | Bitable 高保真原型链接 | Coordinator | 更新字段 |
| 首条 REQ 进入 SPEC_DRAFTING | **ARCHITECTURE 项目级飞书文档（骨架创建）** | Coordinator | 一次性 create（类目模板） |
| Spec 撰写（每条 REQ） | **ARCHITECTURE 项目级飞书文档（增量演化）** | spec-author Agent | 覆盖写（保留飞书原生 revision 历史）；走 context_token + revision 握手 |
| Spec 生成触发（卡点1a 前） | 飞书设计系统快照导出 → GitHub `specs/design-system-snapshot.yaml` | Coordinator | 覆盖写（快照） |
| 卡点1a 通过 | ACM 注册表新增条目（status: locked） | checkpoint-handler | Append |
| 卡点1a 通过 | Bitable 状态 → SPEC_LOCKED，记录卡点1a 时间 | checkpoint-handler | 更新字段 |
| 卡点1b 通过 | ACM 注册表更新条目（status: finalized，回填 test_file/test_function） | checkpoint-handler | 更新字段 |
| 卡点1b 通过 | Bitable 状态 → HARNESS_READY，记录卡点1b 时间 | checkpoint-handler | 更新字段 |
| 架构决策发生 | ADR 文档（docs/decisions/ADR-{N}-*.md） | 人工写入 | 新建文件 |
| 项目交付 | 飞书知识库（客户档案 + 经验总结） | 人工整理 | 新建文档 |

**核心约束**：所有自动更新均 append-only 或幂等更新，不删除历史记录。每次更新可通过 REQ ID 追溯到触发它的需求。
