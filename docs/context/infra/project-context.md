# 项目级上下文产物规格

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §3.2 项目级上下文的产物规格文档。
> 描述各层产物的存储路径、文件格式、更新触发规则。

---

## 一、ARCHITECTURE.yaml 格式

存储于 GitHub 仓库根目录，由 checkpoint-handler 在每次 Impl PR 合并时更新（如有接口变更）。

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
| 需求字段更新（每轮讨论） | 飞书需求文档（section-level 幂等重写） | Coordinator（onExit DISCUSSING Hook） | 幂等替换 |
| REQ APPROVED | Bitable REQ 索引（状态更新） | Coordinator | 更新字段 |
| UI 设计第二阶段确认 | 飞书设计系统文档（append 新组件 + 决策日志） | Coordinator | Append-only |
| UI 设计第二阶段确认 | Bitable 高保真原型链接 | Coordinator | 更新字段 |
| Spec 生成触发（卡点1a 前） | 飞书设计系统快照导出 → GitHub `specs/design-system-snapshot.yaml` | Coordinator | 覆盖写（快照） |
| 卡点1a 通过 | ACM 注册表新增条目（status: locked） | checkpoint-handler | Append |
| 卡点1a 通过 | Bitable 状态 → SPEC_LOCKED，记录卡点1a 时间 | checkpoint-handler | 更新字段 |
| 卡点1b 通过 | ACM 注册表更新条目（status: finalized，回填 test_file/test_function） | checkpoint-handler | 更新字段 |
| 卡点1b 通过 | Bitable 状态 → HARNESS_READY，记录卡点1b 时间 | checkpoint-handler | 更新字段 |
| Impl PR 合并 | ARCHITECTURE.yaml（新接口/模块/数据模型） | checkpoint-handler Hook | 更新对应节点 |
| 架构决策发生 | ADR 文档（docs/decisions/ADR-{N}-*.md） | 人工写入 | 新建文件 |
| 项目交付 | 飞书知识库（客户档案 + 经验总结） | 人工整理 | 新建文档 |

**核心约束**：所有自动更新均 append-only 或幂等更新，不删除历史记录。每次更新可通过 REQ ID 追溯到触发它的需求。
