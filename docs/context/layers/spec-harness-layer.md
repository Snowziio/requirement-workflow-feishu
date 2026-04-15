# 规格层实现规格（Spec 子层 + Harness 子层）

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §4.2–§4.3 规格层的实现细节文档。
> 描述四层 Spec 的完整格式、ACM schema、Harness 目录结构、视觉回归测试配置、卡点卡片格式等。

---

## 项目级上下文契约

> 遵循 [infra/context-chain-principle.md](../infra/context-chain-principle.md) 规定的五问格式。

### Spec 子层消费（来自需求层 + 项目级）

**唯一合法上下文入口**：`/queries/openclaw/spec-context` 端点（CLI 子命令 `spec-context`），状态门控 `APPROVED | SPEC_DRAFTING`。不要用需求层的 `fetch-context`——它不返回 `architecture_doc_url` / `architecture_doc_revision` / `context_token`。

| 上下文产物 | 来源 | 读取机制 |
|-----------|------|---------|
| 需求文档 8 字段 | 飞书文档（requirement_document_url） | feishu_fetch_doc(document_id) |
| latest_review_summary | Coordinator state | spec-context 端点 |
| **ARCHITECTURE 飞书文档** | 飞书项目级 docx（architecture_doc_url） | feishu_fetch_doc + 进入时 architecture_doc_revision |
| **context_token** | Coordinator 签发 | spec-context 端点响应 |
| tech_stack / category / template_version | Coordinator state（project_config） | spec-context 端点 |
| 设计系统快照 | （needs_ui = true 时，Phase 2 启用） | — |
| 高保真 UI 原型链接 | Bitable（needs_ui = true 时） | spec-context 端点 |

### Spec 子层产出（本层双产出物）

| 上下文产物 | 内容 | 存储位置 | 更新策略 |
|-----------|------|---------|---------|
| Spec 飞书文档（9 节） | 背景/API 入参/API 出参/异常/测试策略/性能/实现范围/架构设计（含 §8.2 项目级上下文消费声明）/数据模型 | 飞书 docx（spec_document_id） | 每节覆盖写；SPEC_LOCKED 后冻结 |
| **ARCHITECTURE 演化版本** | 本轮增量合并后的全量 YAML | **同一份项目级飞书文档**（architecture_doc_id） | 覆盖写（保留飞书原生 revision 历史）；走 context_token + revision 握手 |
| spec_document_url | Spec 飞书文档 URL | Coordinator state | spec_start 回传 |
| architecture_doc_revision（写后） | ARCHITECTURE 飞书文档写回后的新 revision | Coordinator state | spec-submit 回传，与 context_token 一并校验 |
| spec_review_summary | Spec 审查结论 | Coordinator state | 每次 Spec 审查完成后更新 |

> **Phase 3 接入点**：Harness 子层启动时，如果需要消费 ARCHITECTURE，由 Coordinator 在卡点 1a 前导出当前飞书文档到 GitHub `specs/architecture-snapshot.yaml`（类比设计系统快照），不让 Harness/Impl Agent 直接读飞书。本文 Spec 子层暂不涉及此导出。

### 并发写回契约

ARCHITECTURE 是**跨 REQ 共享的项目级产出物**，并发保护必须走 [context-chain-principle.md §七](../infra/context-chain-principle.md#七并发写回契约) 的握手协议：

1. spec-context 端点获取 `architecture_doc_url` + 进入时 `architecture_doc_revision` + `context_token`，必须保存
2. 写回 ARCHITECTURE 后再次调 spec-context 取写后 revision
3. `spec-submit` 同时回传 `context_token` 与写后 revision
4. Coordinator 校验失败（`token_invalid` / `revision_conflict`）→ 重新从 Step 1 拉取再合并提交

**Callback 即状态机真相**：写完 Spec 飞书文档 + 写回 ARCHITECTURE ≠ 流程推进。未成功调用 `spec-submit` callback，Coordinator 不会推进到 `SPEC_DRAFTING_SUBMITTED`。SKILL.md 必须将「本次会话最终动作必须是 `spec-submit` callback」作为硬约束。见 [context-chain-principle.md §八](../infra/context-chain-principle.md#八callback-作为状态机唯一真相)。

### Harness 子层消费（来自 Spec 子层）

| 上下文产物 | 来源 | 读取机制 |
|-----------|------|---------|
| acceptance.yaml（全部 AC） | GitHub 仓库 spec/ 目录 | GitHub API |
| design.md（数据模型 + 接口定义） | GitHub 仓库 spec/ 目录 | GitHub API |
| 设计系统快照（AC-UI 类） | GitHub 仓库（needs_ui = true 时） | GitHub API |

### Harness 子层产出

| 上下文产物 | 内容 | 存储位置 | 更新策略 |
|-----------|------|---------|---------|
| 测试用例代码 | 按 AC 组织的 Harness 测试 | GitHub PR（harness/tests/REQ-xxx/） | 卡点1b 确认后只读 |
| 覆盖率矩阵 | AC 与测试文件的对应关系 | GitHub PR | 同上 |
| ACM 注册表（finalized） | acceptance.yaml status 更新为 finalized | GitHub 仓库 | 卡点1b 确认时写入 |

### 终止

| 上下文产物 | 终止原因 |
|-----------|---------|
| discussion_history（需求讨论记录） | 需求层内部记录，Spec 只需要最终 8 字段 |
| design.md 架构叙述（Harness 层） | Harness 只依赖接口契约，不依赖实现架构 |

### 防漂移验证

| Review 维度 | 验证内容 | 层次 | 类型 |
|------------|---------|------|------|
| 需求字段全覆盖 | Spec 各节与需求文档 8 字段一一对应，无遗漏 | Spec | 阻断 |
| 上下文消费声明完整性 | design.md 中「项目级上下文消费声明」子节非空 | Spec | 阻断 |
| API 具体性 | 入参/出参有字段名+类型，无模糊描述 | Spec | 阻断 |
| AC 对齐 | 每条需求验收标准有对应测试用例 | Spec | 阻断 |
| P0 AC 全覆盖 | 所有 P0 AC 在覆盖率矩阵中均有对应测试文件 | Harness | 阻断 |
| 字段一致性 | 测试用例使用的字段名与 acceptance.yaml 定义一致 | Harness | 阻断 |

---

## 一、规格层-A：四层 Spec 完整格式

Spec 存储于 GitHub `spec/REQ-{PROJECT}-{NNN}/` 目录：

```
spec/REQ-PROJECT-001/
  requirements.md       ← Layer 1（自动生成）
  design.md             ← Layer 2（唯一人工 review 层）
  design-ui.md          ← Layer 2 UI 技术规格（needs_ui = true 时）
  acceptance.yaml       ← Layer 3 ACM
  tasks.md              ← Layer 4
```

### Layer 1：requirements.md（自动生成）

从需求文档 8 字段转换为 EARS 格式。仅作格式化中间产物，无需人工 review。

```markdown
# REQ-PROJECT-001 Requirements
> req_id: REQ-PROJECT-001 | generated_at: 2026-04-14

## 功能场景

### UC-001：提交风控报告
**When** 用户提交有效的营业执照图片（jpg/png，< 5MB）和完整的征信数据（含 applicant_id 和 credit_score）
**The system shall** 在 3 秒内返回包含 risk_level、score、report_id 的风控报告

**When** 用户提交缺失 credit_score 的征信数据
**The system shall** 返回 HTTP 422，body 包含 error_code: MISSING_CREDIT_SCORE

## 非功能约束
- 响应时间：P99 < 3s（标准请求）
- 可用性：99.9%
- 数据不出境
```

### Layer 2：design.md（AI 生成 + ⚡卡点1a 人工 review）

**这是整个链路唯一需要深度人工判断的文件。**

AI 生成时注入三类项目级上下文：`ARCHITECTURE.yaml`（现有模块和接口）+ ACM 注册表（历史验收约束）+ 技术范围声明（从需求文档读取）。

```markdown
# REQ-PROJECT-001 Design
> req_id: REQ-PROJECT-001 | spec_version: 1

## 接口契约

POST /api/v1/risk-report
  Request:
    license_image: multipart/form-data（jpg/png，max 5MB）
    credit_report: application/json { applicant_id: string, credit_score: number }
  Response 200:
    { risk_level: "low"|"medium"|"high", score: integer(0-100), report_id: UUID }
  Errors:
    422 MISSING_CREDIT_SCORE — credit_report 缺少 credit_score 字段
    422 INVALID_LICENSE     — 图片无法识别为有效营业执照
    500 ANALYSIS_FAILED     — LLM 分析内部错误

## 数据模型变更

新增表：risk_reports
  id:           UUID（主键，系统生成）
  applicant_id: VARCHAR(64)（外键 → users.id）
  risk_level:   ENUM('low','medium','high')
  score:        SMALLINT（0-100）
  report_data:  JSONB（完整报告内容）
  created_at:   TIMESTAMP WITH TIME ZONE

索引：applicant_id（查询场景：按申请人查询历史风控记录）

## 架构接合点

- **新建路由**：在 `risk-assessment-service` 中新增 `/api/v1/risk-report` 路由处理器
- **复用模块**：`license-parser`（已有，不修改）、`CreditDataGateway`（已有封装，不修改）
- **新增服务层**：`RiskReportService`（协调 OCR + LLM 分析 + 报告生成）
- **数据访问**：新增 `RiskReportRepository`（封装 risk_reports 表操作）

## 兼容性影响

[由 ACM 注册表兼容性检查自动生成]
- 无影响：该接口为全新接口，不修改任何现有接口
- 新增表 risk_reports 不影响现有表结构
```

### Layer 2（可选）：design-ui.md（needs_ui = true 时）

从高保真原型直接提取，不由 AI 凭空推导。

```markdown
# REQ-PROJECT-001 UI Design
> req_id: REQ-PROJECT-001 | source: 高保真原型（见 Bitable 高保真原型链接）

## 组件树

RiskReportPage
  ├── PageHeader（复用现有 PageHeader 组件）
  ├── UploadSection
  │   ├── FileUploader（复用现有 FileUploader 组件）
  │   │   └── props: { accept: ".jpg,.png", maxSizeMB: 5, label: "营业执照" }
  │   ├── CreditReportInput（新建）
  │   │   └── fields: applicant_id（text），credit_score（number，0-850）
  │   └── ValidationMessage（复用现有 ValidationMessage 组件）
  ├── SubmitButton（复用现有 PrimaryButton 组件）
  │   └── states: idle / loading（disabled）
  └── ReportResult（新建，条件渲染：提交成功后显示）
      ├── RiskBadge（新建）
      │   └── props: { level: "low"|"medium"|"high" }
      │   └── styles: low=绿色(#22C55E)，medium=橙色(#F97316)，high=红色(#EF4444)
      └── ScoreDisplay（新建）
          └── props: { score: number }

## 组件接口定义

RiskBadge:
  props:  { level: "low" | "medium" | "high" }
  output: 彩色标签，含文字 "低风险" / "中风险" / "高风险"

CreditReportInput:
  props:   { onValidChange: (data: CreditReport) => void }
  output:  表单，输入完整后回调

RiskReportPage（页面级状态机）:
  states: idle → submitting → success | error
  idle:       展示上传表单
  submitting: SubmitButton disabled，FileUploader disabled，显示加载态
  success:    隐藏 UploadSection，展示 ReportResult
  error:      显示错误提示（ValidationMessage），恢复 idle 可重试

## 交互规格

- 文件大小超限：上传时立即校验，显示内联错误（不等到提交）
- credit_score 超出 0-850：输入时实时校验
- 提交后不可重复点击（SubmitButton 进入 loading）
- error 状态下展示错误原因（映射 error_code 到中文描述）
```

### Layer 3：acceptance.yaml（自动生成，人可在卡点1a 否决）

```yaml
# spec/REQ-PROJECT-001/acceptance.yaml

req_id: REQ-PROJECT-001
spec_version: 1
created_at: 2026-04-14
locked_at: ""           # 卡点1a 确认时自动填充

acceptance_criteria:

  - id: AC-001
    priority: P0
    title: "有效输入返回风控报告"
    given:
      - "营业执照图片有效（jpg/png，< 5MB）"
      - "credit_report 包含 applicant_id（string）和 credit_score（number）"
    input:
      license_image: "valid_license.jpg"
      credit_report: { applicant_id: "u001", credit_score: 720 }
    expected:
      status: 200
      body:
        risk_level: { enum: ["low", "medium", "high"] }
        score:      { type: integer, min: 0, max: 100 }
        report_id:  { type: string, format: uuid }
    test_type: integration
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: ""       # 由规格层-B 生成后回填
    test_function: ""

  - id: AC-002
    priority: P0
    title: "缺失 credit_score 返回 422"
    given:
      - "credit_report 缺少 credit_score 字段"
    input:
      license_image: "valid_license.jpg"
      credit_report: { applicant_id: "u001" }
    expected:
      status: 422
      body:
        error_code: "MISSING_CREDIT_SCORE"
    test_type: integration
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

  - id: AC-003
    priority: P0
    title: "无效营业执照返回 422"
    given:
      - "上传的图片无法识别为有效营业执照"
    input:
      license_image: "invalid_image.jpg"
      credit_report: { applicant_id: "u001", credit_score: 720 }
    expected:
      status: 422
      body:
        error_code: "INVALID_LICENSE"
    test_type: integration
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

  - id: AC-UI-001
    priority: P0
    title: "提交中 SubmitButton 禁用"
    given:
      - "用户已填写有效表单"
      - "正在提交请求中"
    input:
      form_state: "submitting"
    expected:
      ui:
        submit_button_disabled: true
        file_uploader_disabled: true
    test_type: visual
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: ""
    test_function: ""

compatibility:
  inherits_from: []
  breaking_changes: []
  impact_analysis: "本次为新功能首次发布，无历史版本约束。"
  cross_feature_dependencies: []
```

### Layer 4：tasks.md（自动生成）

```markdown
# REQ-PROJECT-001 Tasks
> req_id: REQ-PROJECT-001 | generated_from: design.md + acceptance.yaml

## 实现任务（按依赖排序）

### Task-1：数据库迁移
- 新建 risk_reports 表（见 design.md 数据模型）
- 添加 applicant_id 索引
- 对应 AC：无（基础设施）
- 依赖：无

### Task-2：服务层实现
- 新建 `RiskReportService`（协调 license-parser + CreditDataGateway + LLM 分析）
- 新建 `RiskReportRepository`（封装 risk_reports 表操作）
- 对应 AC：AC-001、AC-003
- 依赖：Task-1

### Task-3：路由和错误处理
- 在 risk-assessment-service 新增 POST /api/v1/risk-report 路由
- 实现输入校验逻辑和错误码映射
- 对应 AC：AC-001、AC-002、AC-003
- 依赖：Task-2

### Task-4：前端页面（needs_ui = true）
- 实现 RiskReportPage（见 design-ui.md）
- 实现 RiskBadge、CreditReportInput、RiskReportPage 三个新组件
- 对应 AC：AC-UI-001
- 依赖：Task-3
```

---

## 一bis、飞书 9 节 Spec ↔ GitHub 四文件 Spec 映射

> 规格层有两阶段产物（见方法论 §4.2 "两阶段 Spec 模型"）：飞书 9 节 Spec 为协作草稿，GitHub 四文件 Spec 为机器可解析结构。卡点1a 是二者的单向转化锁定点。下表给出每一节的落点，spec-author Agent 的 9 节输出到 checkpoint-handler 的四文件转化必须按此映射执行，不得自由发挥。

| 飞书 Spec 节 | 主要落点 | 次要落点 |
|---|---|---|
| §1 背景与目标 | `design.md` 头部"背景" | `requirements.md` 头部 `req_id` / `summary` |
| §2 API 入参定义 | `design.md` §接口契约（入参表） | `acceptance.yaml` 每条 AC 的 `given` 字段（结构化输入） |
| §3 API 出参定义 | `design.md` §接口契约（出参 + 错误码表） | `acceptance.yaml` 每条 AC 的 `then` 字段（期望输出） |
| §4 异常处理与边界条件 | `design.md` §接口契约（错误码表） | `acceptance.yaml` 异常类 AC 条目（AC-xxx_invalid_*） |
| §5 测试策略 | `acceptance.yaml`（AC 全集，含 P0 标记） | `tasks.md`（测试实现任务） |
| §6 性能与可用性指标 | `design.md` §非功能约束 | `acceptance.yaml` 非功能类 P0 AC（P99/QPS/可用性） |
| §7 实现范围 | `design.md` §架构接合点 | `tasks.md` 任务范围声明（in/out of scope） |
| §8.1 顶层架构背景 | `design.md` §架构接合点 | — |
| §8.2 项目级上下文消费声明 | `design.md` §上下文消费（新增子节，列出消费的 ARCHITECTURE.yaml 版本、ACM 快照日期等） | — |
| §8.3 关键架构决策 | `design.md` §架构决策（每条"决策 + 依据 + 影响"三要素保留） | — |
| §8.4 存储与数据流设计 | `design.md` §数据模型变更 | — |
| §9 数据模型 | `design.md` §数据模型变更（表/字段定义） | `tasks.md` Task-1 数据库迁移 |

**UI 补充**：`needs_ui = true` 时，高保真原型 → `design-ui.md`（组件树 + 组件接口 + 交互规格），独立于上表 9 节映射；视觉类 AC（AC-UI-xxx）在 `acceptance.yaml` 中与功能 AC 并列。

**覆盖性校验**：卡点1a 合并前，checkpoint-handler 必须校验飞书 Spec 9 节全部非空，且上表每一行的主要落点在四文件中可定位（缺失任一则打回）。

---

## 二、Spec 生成流程

> 本节"阶段 A / 阶段 B"是 Spec 生成方式的演进路径，与方法论 §六 的全局 Phase 命名相互独立。阶段 A 是当前实施方式，阶段 B 是 Phase 2 目标完成后的自动化形态。

### 阶段 A：人工桥接（当前实施方式）

```
1. Coordinator 通知：「REQ-PROJECT-001 已 APPROVED，可进入规格层」
2. 开发者操作：
   → git checkout -b spec/REQ-PROJECT-001
   → 读取飞书需求文档 + 高保真 UI 原型（如有）
   → 读取 GitHub ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照
   → 使用 Claude Code 生成四层 Spec 到 spec/REQ-PROJECT-001/ 目录
   → git push → 创建 PR，PR 标题含 REQ ID
3. 开发者触发：Bitable 状态 → SPEC_DRAFTING，记录 Spec PR 链接
4. checkpoint-handler 发送卡点1a 飞书卡片
```

### 阶段 B：半自动化（Phase 2 交付目标）

```
1. 人：@Coordinator 创建Spec REQ-PROJECT-001
2. Coordinator 执行：
   → 飞书 API：读取需求文档 + 高保真原型内容
   → GitHub API：读取 ARCHITECTURE.yaml + ACM 注册表
   → 导出设计系统快照：Coordinator → GitHub specs/design-system-snapshot.yaml
   → 调用 Spec 转化 Agent：生成四层 Spec
   → GitHub API：创建分支 spec/REQ-PROJECT-001，commit 所有文件，创建 PR
   → Bitable：状态 → SPEC_DRAFTING，记录 PR 链接
   → checkpoint-handler：触发卡点1a 飞书卡片
```

### 卡点1a 飞书卡片内容

```
[卡点1a · 方案门] REQ-PROJECT-001 · Spec PR #42

Design 层预览：
  接口：POST /api/v1/risk-report
  新增表：risk_reports（5 字段）
  架构接合：risk-assessment-service 新路由，复用 license-parser
  兼容性：无影响（全新接口）

ACM 验收标准：
  AC-001 [P0] 有效输入返回风控报告
  AC-002 [P0] 缺失 credit_score 返回 422
  AC-003 [P0] 无效营业执照返回 422
  AC-UI-001 [P0] 提交中 SubmitButton 禁用

[查看完整 Spec PR] [确认提交] [返回修改]
```

### ACM 版本演进

当需求 v2 变更时（如收紧性能要求、新增 AC）：

```yaml
# spec/REQ-PROJECT-002/acceptance.yaml（新需求）或需求变更时追加版本
feature: risk-report
version: 2

acceptance_criteria:
  # 继承自 v1（不变）
  - id: AC-001
    source_version: 1
    breaking_change: false

  # 继承自 v1（变更：响应时间从 3s 改为 1s）
  - id: AC-002
    title: "响应时间 P99 < 1s"
    source_version: 1
    breaking_change: true   # 标记 breaking

  # v2 新增
  - id: AC-004
    title: "支持批量请求"
    source_version: 2
    breaking_change: false

compatibility:
  inherits_from: [1]
  breaking_changes:
    - ac_id: AC-002
      description: "响应时间从 3s 降至 1s"
      mitigation: "已评估，新架构支持"
```

---

## 三、规格层-B：Harness 实现规格

### Harness 目录结构

```
harness/tests/
├── REQ-PROJECT-001/
│   ├── AC-001_valid_input/
│   │   ├── test_case.py
│   │   └── fixtures/
│   │       └── valid_request.json
│   ├── AC-002_missing_credit_score/
│   │   ├── test_case.py
│   │   └── fixtures/
│   │       └── invalid_request.json
│   ├── AC-003_invalid_license/
│   │   ├── test_case.py
│   │   └── fixtures/
│   │       └── invalid_license.jpg
│   └── visual/                        # needs_ui = true 时
│       ├── test_visual_regression.py
│       └── screenshots/               # 截图基线（首次 CI 通过时建立）
│           ├── idle_state.png
│           ├── submitting_state.png
│           └── success_state.png
├── conftest.py                        # 共享 fixture
└── README.md                          # Harness 生成规则说明
```

**关键规则**：
- 每个 AC 有独立目录，目录名为 `{AC-ID}_{简述}`
- 卡点1b 确认后，当前 REQ 的 Harness 目录**只读**
- CI 运行全部 Harness（`pytest harness/tests/`），包含所有历史 REQ
- 新实现不得删除旧 REQ 已覆盖的 AC 测试（除非显式 BREAKING CHANGE）

### 测试用例生成规格

每个 AC 的 `given / input / expected` 字段直接映射到测试用例：

```python
# harness/tests/REQ-PROJECT-001/AC-001_valid_input/test_case.py
# AUTO-GENERATED from spec/REQ-PROJECT-001/acceptance.yaml AC-001
# DO NOT EDIT MANUALLY

import pytest
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"

class TestAC001ValidInput:
    """AC-001 [P0]: 有效输入返回风控报告"""

    def test_returns_200_with_valid_fields(self, api_client):
        """Given: 有效营业执照图片和完整征信数据 → 返回 200 含 risk_level/score/report_id"""
        with open(FIXTURE_DIR / "valid_request.json") as f:
            credit_report = json.load(f)
        with open(FIXTURE_DIR / "valid_license.jpg", "rb") as img:
            response = api_client.post(
                "/api/v1/risk-report",
                files={"license_image": img},
                json={"credit_report": credit_report}
            )
        assert response.status_code == 200
        body = response.json()
        assert body["risk_level"] in ["low", "medium", "high"]
        assert isinstance(body["score"], int) and 0 <= body["score"] <= 100
        assert len(body["report_id"]) == 36  # UUID 长度
```

### 覆盖率矩阵格式

Harness 生成后同时输出覆盖率矩阵文档，供卡点1b 人工审核：

```markdown
# 覆盖率矩阵 - REQ-PROJECT-001

| AC 编号 | 优先级 | 验收标准 | 测试文件 | CI 运行 |
|---|---|---|---|---|
| AC-001 | P0 | 有效输入返回风控报告 | REQ-PROJECT-001/AC-001_valid_input/test_case.py | ✅ |
| AC-002 | P0 | 缺失 credit_score 返回 422 | REQ-PROJECT-001/AC-002_missing_credit_score/test_case.py | ✅ |
| AC-003 | P0 | 无效营业执照返回 422 | REQ-PROJECT-001/AC-003_invalid_license/test_case.py | ✅ |
| AC-UI-001 | P0 | 提交中 SubmitButton 禁用 | REQ-PROJECT-001/visual/test_visual_regression.py | ✅ |

P0 全覆盖：✅（4/4）
历史回归：N/A（首版）
```

### 视觉回归测试配置

```python
# harness/tests/REQ-PROJECT-001/visual/test_visual_regression.py
# AUTO-GENERATED from spec/REQ-PROJECT-001/design-ui.md
# DO NOT EDIT MANUALLY

import pytest
from playwright.sync_api import Page, expect

SCREENSHOT_DIR = "harness/tests/REQ-PROJECT-001/visual/screenshots"
THRESHOLD = 0.02  # 2% 像素差异容忍阈值

class TestVisualRegression:
    """AC-UI-001 [P0]: 视觉回归测试 - RiskReportPage"""

    def test_idle_state(self, page: Page, app_base_url: str):
        """初始状态：上传表单可见，SubmitButton 可用"""
        page.goto(f"{app_base_url}/risk-report")
        page.wait_for_load_state("networkidle")
        screenshot = page.screenshot()
        assert_visual_match(screenshot, f"{SCREENSHOT_DIR}/idle_state.png", THRESHOLD)

    def test_submitting_state(self, page: Page, app_base_url: str):
        """提交中：SubmitButton 禁用，FileUploader 禁用（AC-UI-001）"""
        page.goto(f"{app_base_url}/risk-report")
        # 填写有效表单后触发提交，在网络请求返回前截图
        fill_valid_form(page)
        with page.expect_request("**/api/v1/risk-report"):
            page.click("[data-testid=submit-button]")
            screenshot = page.screenshot()
        assert_visual_match(screenshot, f"{SCREENSHOT_DIR}/submitting_state.png", THRESHOLD)
        # 验证 AC-UI-001：SubmitButton 必须禁用
        submit_btn = page.locator("[data-testid=submit-button]")
        expect(submit_btn).to_be_disabled()
```

### 卡点1b 飞书卡片内容

```
[卡点1b · Harness 门] REQ-PROJECT-001 · Harness PR #45

覆盖率矩阵：
  AC-001 [P0] → AC-001_valid_input/test_case.py ✅
  AC-002 [P0] → AC-002_missing_credit_score/test_case.py ✅
  AC-003 [P0] → AC-003_invalid_license/test_case.py ✅
  AC-UI-001 [P0] → visual/test_visual_regression.py ✅

P0 全覆盖：✅（4/4）
历史回归：N/A（首版）

[查看 Harness PR] [确认 Harness] [打回重生成]
```

---

## 四、Spec 子状态机与 fallback

需求主态在 APPROVED 后不再变化（见 [requirement-layer.md](requirement-layer.md) §一）。规格层 Spec 子层引入独立的子状态字段 `spec_status`（Bitable 字段名：`Spec状态`，枚举：`NONE` / `SPEC_DRAFTING` / `SPEC_LOCKED` / `SPEC_REJECTED`），不覆盖需求主态。

### 子状态转移表

| 当前 `spec_status` | 事件 | 目标 | 触发方 | 说明 |
|---|---|---|---|---|
| NONE | spec_start | SPEC_DRAFTING | Coordinator 收到 spec-author Agent 的 `spec_start` 回调 | 同时创建飞书 Spec 文档，写入 `spec_document_url` |
| SPEC_DRAFTING | spec_submit | SPEC_DRAFTING（保持）| spec-author 上报 9 节完稿 | 仅更新 `spec_review_summary`，不立即转 SPEC_LOCKED |
| SPEC_DRAFTING | ai_review_reject | SPEC_DRAFTING（保持）| spec-reviewer 审查未通过 | spec-author 继续修改；回合数计入 `spec_iteration_round` |
| SPEC_DRAFTING | ai_review_pass | SPEC_DRAFTING（保持）| spec-reviewer 通过 | 等待人工卡点1a |
| SPEC_DRAFTING | checkpoint_1a_pass | SPEC_LOCKED | 人（飞书卡片"确认提交"按钮） | 触发飞书 9 节 → GitHub 四文件转化；飞书 Spec 文档自此只读 |
| SPEC_DRAFTING | checkpoint_1a_reject | SPEC_DRAFTING（保持）| 人（飞书卡片"返回修改"按钮）| spec-author 继续迭代 |
| SPEC_DRAFTING | spec_abort | SPEC_REJECTED | 人（显式放弃）或超时清理 | **需求主态回到 DRAFTING**（见下方 §"需求回炉 fallback"） |
| SPEC_LOCKED | — | （终态） | — | 任何进一步变更走"Spec 版本演进"（新 spec_version），不改现有 SPEC_LOCKED |

### 需求回炉 fallback（跨态降级）

若 Spec 阶段发现需求本身存在不可修复问题（字段不完整 / 技术范围声明与现实严重不符 / 核心验收标准无法落实），允许从 Spec 子状态机降级回需求主态机：

触发条件（任一）：
- 技术负责人在 Spec 讨论中主动判定"需求需要重做"，向 Coordinator 发送 `spec_to_requirement_rework` 事件
- spec-reviewer 连续 3 轮 `ai_review_reject` 且共同根因指向需求层字段（由 Coordinator 聚合判定）

执行动作（Coordinator 原子执行）：
1. `spec_status` → SPEC_REJECTED（标记当前 Spec 草稿作废）
2. `requirement.status`：APPROVED → DRAFTING（需求主态回炉）
3. 将 `spec_review_summary` 作为 "需求层需关注的问题" 写入需求文档的讨论追溯节
4. 通知 author 私聊：需求已回炉，请继续补全
5. 飞书 Spec 文档保留（只读，标记 `[已作废 · SPEC_REJECTED]`），供审计追溯
6. 同一 REQ ID 继续使用；若后续再次进入 Spec 阶段，`spec_version` 从 v1 重新开始（上个作废版本保留为 v0.rejected）

该 fallback 是**唯一允许从规格层回退到需求层的路径**，必须经 Coordinator 记录事件日志，不得由 Agent 直接改写状态。

---

## 五、Spec 版本管理规则

| 情况 | 处理方式 |
|---|---|
| 现有功能 Bug | 直接开 Impl PR 修复，不需要新 Spec |
| 行为不符预期但测试通过 | Spec AC 写错了，需要新 Spec 版本（increment spec_version）|
| 新增能力 | 新 Spec 目录（新 REQ ID 或新 spec_version）|
| 性能改进 | 新 spec_version，变更 AC 标记 `breaking_change: true` |
| BREAKING CHANGE | 必须在 ACM compatibility 节声明，触发 ACM 注册表兼容性告警 |
