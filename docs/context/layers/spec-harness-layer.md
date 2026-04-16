# 规格层实现规格（规格层 + Harness 层）

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §5.2–§5.3 规格层的实现细节文档。
> 描述目标/使命、上下文契约、六阶段工作流、四文件 Spec 格式、子状态机、转化博弈、Harness 目录结构、卡片模板等。
> 本文服务 Phase 2（规格层）实施者；Harness 层（§十）服务 Phase 3。

---

## 零、实现状态与变更记录

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v1 | 2026-04 以前 | 五文件 Spec（requirements.md + design.md + design-ui.md + acceptance.yaml + tasks.md），路径 `spec/REQ-*/`；单阶段状态机 `SPEC_DRAFTING → SPEC_LOCKED` |
| **v2** | **2026-04-16** | **四文件 Spec**（drop `requirements.md`，acceptance.yaml → `ac-schedule.yaml`），路径迁到 `docs/specs/REQ-*/`；新增中间态 `SPEC_TRANSFORMING` + spec-transformer/reviewer 博弈；新增 Round 0 AC 回显、Computational gate 前置、transform_trace、regression scan 四道工程化闸门 |

---

## 一、目标与使命

### 1.1 核心使命

把"经人工双闸门确认的 APPROVED 需求"**转化**为"让生成层能无人值守自驱 coding 的机器可解析三元组"——

- **约束集**（design.md 承载）：接口契约 + 数据模型 + 架构接合点 + supersedes 节
- **反馈集**（ac-schedule.yaml + harness 骨架承载）：声明式 AC + 可执行判定回路
- **边界锚**（supersedes + acm-registry patch + ARCHITECTURE revision 三重锚）：防跨 REQ 漂移 + 防架构颠覆

### 1.2 关键判定（SPEC_LOCKED 时必须满足）

1. 生成层只消费四文件 + 根仓库 `acm-registry.yaml`，**不回看飞书文档**即可开始 coding
2. P0 Harness 通过成为 Impl PR 合并的硬门槛
3. 本次 Spec 的决策通过三重锚**单调写入**项目级上下文

### 1.3 非职责（避免越界）

- **不**产出实现代码（生成层职责）
- **不**填充完整测试断言，只产出骨架（Harness 层职责）
- **不**决定 AC 是否通过（验证层职责）
- **不**定义项目级架构；ARCHITECTURE 跨层演化，本层只消费 + 增量合并写回

---

## 二、上下文契约

> 遵循 [infra/context-chain-principle.md](../infra/context-chain-principle.md) 五问格式。

### 2.1 规格层消费输入

**唯一合法入口**：`/queries/openclaw/spec-context` 端点（CLI 子命令 `spec-context`）。状态门控：`requirement.status == APPROVED && spec_status ∈ {null, SPEC_DRAFTING}`。

> **禁用**需求层的 `fetch-context`——它不返回 `architecture_doc_url` / `architecture_doc_revision` / `context_token`。

| 上下文产物 | 来源 | 性质 | 用于三元组 |
|---|---|---|---|
| 需求文档 8 字段 | 飞书 docx（requirement_document_url） | 只读 | 约束集 + 反馈集 |
| latest_review_summary | Coordinator state | 只读 | — |
| **ARCHITECTURE 飞书文档** | 飞书项目级 docx（architecture_doc_url）+ 入口 `architecture_doc_revision` | 读入 + 增量合并 + 写回 | 约束集（架构接合点）+ 边界锚 |
| **acm-registry 切片** | Coordinator 根据技术范围声明过滤后的相关条目 | 只读 | 边界锚（supersedes 依据） |
| **context_token** | Coordinator 签发 | 只读 | 并发写回握手 |
| tech_stack / category / template_version | project_config | 只读 | 约束集（技术栈锚） |
| 高保真 UI 原型链接 | Bitable（`needs_ui = true` 时） | 只读 | 约束集（UI 技术合同） |
| 设计系统快照 | Coordinator 在 Spec 启动时导出的飞书设计系统文档 | 只读 | 约束集（UI 规格） |

### 2.2 规格层产出

分两阶段，对应状态 `SPEC_DRAFTING` 末态与 `SPEC_LOCKED` 末态。

**阶段一（飞书，`SPEC_DRAFTING` 末态）**：

| 产物 | 载体 | 更新策略 |
|---|---|---|
| 飞书 9 节 Spec（人-AI 协作协议，非交付物） | 飞书 docx（`spec_document_id`） | 每节覆盖写；卡点 1a 通过后冻结 |
| ARCHITECTURE 演化版本（跨 REQ 共享产出物） | 同一份项目级飞书文档（`architecture_doc_id`） | 覆盖写 + 飞书原生 revision；走 context_token + revision round-trip |
| `spec_document_url` | Coordinator state | `spec_start` callback 回传 |
| `architecture_doc_revision`（写后） | Coordinator state | `spec_submit` callback 回传 |
| `spec_author_summary` | Coordinator state | `spec_submit` 事件写入 |
| `spec_review_summary` | Coordinator state | 每次 reviewer 完成后更新 |
| `spec_source_revision` | Coordinator state | **卡点 1a 通过时**捕获飞书 Spec revision，作为 `SPEC_TRANSFORMING` 阶段的单向审计锚 |

**阶段二（GitHub，`SPEC_LOCKED` 末态）**：

| 产物 | 载体 | 内容 |
|---|---|---|
| design.md | `docs/specs/REQ-{PROJECT}-{NNN}/design.md` | 约束集主体 + `## supersedes` 节 |
| tasks.md | `docs/specs/REQ-{PROJECT}-{NNN}/tasks.md` | 每行 `- [ ] T-NN: verb (acceptance: AC-K)` |
| ac-schedule.yaml | `docs/specs/REQ-{PROJECT}-{NNN}/ac-schedule.yaml` | 反馈集声明部分 |
| harness 骨架 | `harness/tests/REQ-{PROJECT}-{NNN}/` 下每 AC 一个 pytest 占位文件 | 含 `@pytest.mark.ac("AC-K")` + 占位 assert |
| acm-registry patch | 根仓库 `acm-registry.yaml` 的追加 commit | 承接 supersedes 链、注册本次新增 AC |
| Spec PR | GitHub `spec/REQ-{PROJECT}-{NNN}` 分支 PR | body 含 `spec_source_revision` + `transform_round` 审计链 |
| `transform_trace` digest | Bitable + state.json | 博弈过程日志摘要（sha256 前 12 位） |

### 2.3 ARCHITECTURE 并发写回契约

ARCHITECTURE 是**跨 REQ 共享的项目级产出物**，并发保护必须走 [context-chain-principle.md §七](../infra/context-chain-principle.md#七并发写回契约)：

1. `spec-context` 端点返回 `architecture_doc_url` + 入口 `architecture_doc_revision` + `context_token`
2. spec-author 写回 ARCHITECTURE 后，再调 `spec-context` 取写后 revision
3. `spec_submit` callback 同时回传 `context_token` 与写后 revision
4. Coordinator 校验失败（`token_invalid` / `revision_conflict`）→ 指令 spec-author 重新从 step 1 拉取后合并提交

### 2.4 Callback 即状态机真相

写完飞书 Spec + 写回 ARCHITECTURE ≠ 流程推进。未成功调用 `spec-submit` callback，Coordinator **不会**推进子状态。SKILL.md 必须把「本次会话最终动作必须是 spec-submit callback」写成硬约束。见 [context-chain-principle.md §八](../infra/context-chain-principle.md#八callback-作为状态机唯一真相)。

### 2.5 Harness 层消费与产出

| Harness 层消费 | 来源 |
|---|---|
| `ac-schedule.yaml`（全部 AC） | `docs/specs/REQ-*/` 目录 |
| `design.md`（接口契约 + 数据模型） | `docs/specs/REQ-*/` 目录 |
| harness 骨架（占位文件） | `harness/tests/REQ-*/` |
| 设计系统快照（AC-UI 类） | `docs/specs/REQ-*/` 或根仓库 `specs/design-system-snapshot.yaml` |

| Harness 层产出 | 载体 |
|---|---|
| 完整测试代码（填充骨架） | `harness/tests/REQ-*/` 原路径 |
| 覆盖率矩阵文档 | `harness/tests/REQ-*/COVERAGE.md` |
| `ac-schedule.yaml` 的 `test_file` / `test_function` 字段回填 | 同一份 ac-schedule.yaml |

### 2.6 防漂移验证

| Review 维度 | 验证内容 | 层 | 类型 |
|---|---|---|---|
| 需求字段全覆盖 | 飞书 9 节与需求 8 字段一一对应，无遗漏 | Spec（阶段一） | 阻断 |
| ARCHITECTURE 消费声明完整 | design.md 含「项目级上下文消费」子节，列出 architecture_doc_revision | Spec（阶段二） | 阻断 |
| API 具体性 | 入参/出参字段名 + 类型，无模糊描述 | Spec | 阻断 |
| supersedes 完整性 | design.md 含 `## supersedes`，可为 `"no supersession"` | Spec（阶段二） | 阻断 |
| AC↔骨架路径一致 | ac-schedule 每条 `test_file` 在 harness/tests 存在且含 `@pytest.mark.ac` | Spec（阶段二） | 阻断 |
| Regression scan | acm-registry active AC 全部在骨架中有锚 | Spec（Phase 4 闸门） | 阻断 |
| P0 AC 全覆盖 | 所有 P0 AC 在覆盖率矩阵中有对应测试文件 | Harness | 阻断 |
| 字段一致性 | 测试用例字段名与 ac-schedule.yaml 定义一致 | Harness | 阻断 |

---

## 三、四文件 Spec 结构（阶段二产出）

### 3.1 目录布局

```
# Spec 元数据（生成层只读消费）
docs/specs/REQ-{PROJECT}-{NNN}/
  design.md
  tasks.md
  ac-schedule.yaml

# 测试骨架（Impl/Harness 层填充；CI 直接跑）
harness/tests/REQ-{PROJECT}-{NNN}/
  AC-001_<slug>/
    test_case.py       # 骨架，含 @pytest.mark.ac("AC-001") + 占位 assert
    fixtures/          # 空目录或 .gitkeep
  AC-002_<slug>/
    test_case.py
    ...
  visual/              # needs_ui = true 时
    test_visual_regression.py

# 项目级注册表（每次 Spec PR 追加 patch）
acm-registry.yaml       # 根仓库
```

**路径规约**：
- 元数据文件（design / tasks / ac-schedule）**必须**落在 `docs/specs/REQ-{PROJECT}-{NNN}/` 下
- 骨架文件**必须**落在 `harness/tests/REQ-{PROJECT}-{NNN}/` 下
- `ac-schedule.yaml` 中每条 AC 的 `test_file` 字段必须与实际骨架路径**字符串严格一致**

### 3.2 design.md 格式

```markdown
# REQ-{PROJECT}-{NNN} Design
> req_id: REQ-{PROJECT}-{NNN} | spec_source_revision: <rev-id> | transformed_at: <iso>

## 背景
（从飞书 §1 转化的一段话，不超过 200 字）

## 项目级上下文消费
- ARCHITECTURE 飞书文档 revision: <rev-id>
- acm-registry 切片日期: <iso>
- 设计系统快照 revision: <rev-id>（needs_ui = true 时）

## 接口契约
（从飞书 §2/§3/§4 转化）
POST /api/v1/xxx
  Request: ...
  Response 200: ...
  Errors: ...

## 数据模型
（从飞书 §9 转化）
新增表 / 字段 / 索引 / 外键

## 架构接合点
（从飞书 §7/§8 转化）
- 新建模块: <name>
- 复用模块: <name>（不修改）
- 新增服务层 / 数据访问 / ...

## supersedes
（必选段。从 acm-registry 历史切片中找出被本 REQ 取代的 AC 条目；若无，声明 "no supersession"）
- 取代 AC-X-007（REQ-PROJ-003），原因：本 REQ 收紧性能约束 P99 3s → 1s
- 取代 AC-X-011（REQ-PROJ-005），原因：接口路径从 /foo/bar 改为 /foo/baz

或：
- no supersession
```

**硬约束**：
- `## supersedes` 段必须存在，否则 Computational gate 阻断
- `## 项目级上下文消费` 必须列出至少 `ARCHITECTURE` 的 revision

### 3.3 tasks.md 格式

```markdown
# REQ-{PROJECT}-{NNN} Tasks
> req_id: REQ-{PROJECT}-{NNN} | generated_from: design.md + ac-schedule.yaml

- [ ] T-01: 创建 risk_reports 表迁移脚本 (acceptance: AC-001)
- [ ] T-02: 实现 RiskReportService.generate (acceptance: AC-001)
- [ ] T-03: 实现 422 校验与错误码映射 (acceptance: AC-002)
- [ ] T-04: 实现 OCR 无效图片错误路径 (acceptance: AC-003)
- [ ] T-05: 实现 RiskReportPage 提交中状态 (acceptance: AC-UI-001)
```

**硬约束**（Computational gate 正则）：
- 每行必须匹配 `^- \[ \] T-\d+: .+ \(acceptance: AC-[A-Z0-9-]+\)$`
- 禁止使用自由格式标题或子列表；生成层逐行消费

### 3.4 ac-schedule.yaml 格式

```yaml
# docs/specs/REQ-{PROJECT}-{NNN}/ac-schedule.yaml
req_id: REQ-{PROJECT}-{NNN}
spec_source_revision: <rev-id>
spec_version: 1
generated_at: <iso>

acceptance_criteria:

  - id: AC-001
    priority: P0
    title: "有效输入返回风控报告"
    given:
      - "营业执照图片有效（jpg/png，< 5MB）"
      - "credit_report 含 applicant_id 和 credit_score"
    input:
      license_image: "valid_license.jpg"
      credit_report: { applicant_id: "u001", credit_score: 720 }
    expected:
      status: 200
      body:
        risk_level: { enum: ["low","medium","high"] }
        score:      { type: integer, min: 0, max: 100 }
        report_id:  { type: string, format: uuid }
    test_type: integration
    ci_enabled: true
    source_version: 1
    breaking_change: false
    test_file: "harness/tests/REQ-{PROJECT}-{NNN}/AC-001_valid_input/test_case.py"
    test_function: "test_returns_200_with_valid_fields"

compatibility:
  inherits_from: []
  breaking_changes: []
  impact_analysis: "新功能首次发布"
  cross_feature_dependencies: []
```

**硬约束（jsonschema + Computational gate）**：
- `req_id` 格式 `REQ-[A-Z0-9]+-\d{3,}`
- `acceptance_criteria[*].id` 唯一且格式 `AC-[A-Z0-9-]+`
- `acceptance_criteria[*].priority ∈ {P0, P1, P2}`
- `acceptance_criteria[*].test_file` 文件在 commit 时实际存在（Computational gate 校验）
- `given / input / expected` 三字段全部必填

### 3.5 harness 骨架格式

```python
# harness/tests/REQ-{PROJECT}-{NNN}/AC-001_valid_input/test_case.py
# SKELETON — 生成层/Harness 层负责填充真实 assert
# DO NOT EDIT path / test function name / @pytest.mark.ac argument

import pytest

@pytest.mark.ac("AC-001")
def test_returns_200_with_valid_fields(api_client):
    """AC-001 [P0] 有效输入返回风控报告
    given: 营业执照图片有效 + credit_report 完整
    expected: status=200, body 含 risk_level/score/report_id
    """
    pytest.skip("skeleton — fill in during impl phase")
```

**硬约束**：
- 文件名 = `test_case.py`
- 每文件**恰好一个** `@pytest.mark.ac("AC-K")` 标记
- 测试函数名与 ac-schedule 中 `test_function` 严格一致
- 骨架阶段用 `pytest.skip` 标记，避免 CI 红灯

### 3.6 acm-registry.yaml patch 格式

`acm-registry.yaml` 是根仓库级全局注册表，Coordinator 在 `SPEC_LOCKED` 前自动生成 patch 作为 Spec PR 的追加 commit：

```yaml
# acm-registry.yaml （根仓库，accumulate）
version: 3
entries:
  - ac_id: AC-001
    req_id: REQ-{PROJECT}-{NNN}
    status: active
    added_at: <iso>
    priority: P0
    breaking_change: false
    source_version: 1
    supersedes: []
    superseded_by: null

  - ac_id: AC-X-007
    req_id: REQ-PROJ-003
    status: retired          # 被本 REQ 取代
    retired_at: <iso>
    superseded_by: AC-001    # 指向新版
    # ... 原字段保留
```

**状态字段**：
- `active`：生效中，harness/conftest 会跑
- `retired`：已被取代，harness/conftest 自动 skip（via `@pytest.mark.ac` 与 registry 的 runtime 对照）

---

## 四、飞书 9 节 ↔ 四文件映射

> spec-author 写飞书 9 节（阶段一），spec-transformer 按下表产出四文件（阶段二）。转化必须遵循此映射，**不得自由发挥**。

| 飞书 Spec 节 | 主要落点 | 次要落点 |
|---|---|---|
| §1 背景与目标 | `design.md` §背景 | — |
| §2 API 入参定义 | `design.md` §接口契约（入参） | `ac-schedule.yaml` 各 AC 的 `given` / `input` |
| §3 API 出参定义 | `design.md` §接口契约（出参） | `ac-schedule.yaml` 各 AC 的 `expected` |
| §4 异常处理与边界 | `design.md` §接口契约（错误码表） | `ac-schedule.yaml` 异常类 AC |
| §5 测试策略 | `ac-schedule.yaml` AC 全集（含 P0 标记） | `tasks.md`（测试相关 T 项）+ harness 骨架（逐条派生） |
| §6 性能与可用性 | `design.md` §非功能约束 | `ac-schedule.yaml` 非功能类 P0 AC |
| §7 实现范围 | `design.md` §架构接合点 | `tasks.md`（T 项范围） |
| §8.1 顶层架构背景 | `design.md` §架构接合点 | — |
| §8.2 项目级上下文消费 | `design.md` §项目级上下文消费 | — |
| §8.3 关键架构决策 | `design.md` §架构决策（可与 §架构接合点合并） | — |
| §8.4 存储与数据流 | `design.md` §数据模型 | — |
| §9 数据模型 | `design.md` §数据模型（表/字段/索引/外键） | `tasks.md` T-迁移项 |
| supersedes 判定 | `design.md` §supersedes | `acm-registry.yaml` patch（retired 条目） |

**UI 补充**：`needs_ui = true` 时，高保真原型直接转化为 `design.md` 的 UI 子节（组件树 + 组件接口 + 交互规格），视觉类 AC（AC-UI-*）在 `ac-schedule.yaml` 与功能 AC 并列。

**覆盖性校验**（spec-transformer-reviewer 第 5 维度）：四文件中必须能定位到飞书 9 节每一节的主要落点，缺失任一节 → reject。

---

## 五、六阶段工作流

规格层完整流水线。**仅一个人工卡点（卡点 1a）**；Round 0 / Computational gate / Regression scan / Deadlock 都是机械闸门，不打扰人。

### 5.1 Phase 1：进入授权（APPROVED → SPEC_DRAFTING）

**触发**：需求层 `APPROVED` + 项目群「启动 Spec 撰写」卡片被点击。

**动作**：
1. Coordinator 创建飞书 Spec 文档（9 节模板），写入 docx metadata `req_id`
2. 初始化 Spec 子状态机：`null → SPEC_DRAFTING`
3. 通过 `spec-context` 端点注入项目级上下文：
   - 捕获入口 `architecture_doc_revision`
   - 生成 `context_token`
   - 导出设计系统快照（`needs_ui = true` 时）
4. 投递任务给 spec-author Agent（CLI 调用 + SKILL.md 硬约束 "最终必须调 spec-submit callback"）

**出态**：`spec_status = SPEC_DRAFTING`，`spec_document_url` 写入 Bitable。

### 5.2 Phase 2：飞书 9 节撰写与审查（SPEC_DRAFTING 内循环）

**循环主体**：

1. spec-author 读飞书需求文档 + ARCHITECTURE + ACM 切片 + 设计系统快照 → 撰写 9 节 Spec → 增量合并 ARCHITECTURE 覆盖写回飞书
2. spec-author 触发 `spec_submit` callback（带写后 `architecture_doc_revision` + `context_token`）
3. Coordinator 校验 token / revision 握手；失败 → 指令 spec-author 重拉重写
4. 校验通过 → 投递给 spec-reviewer
5. spec-reviewer 按 9 节质量清单审查 → `ai_review_pass` / `ai_review_reject`
6. `ai_review_reject` → 回 step 1（spec-author 迭代）；`ai_review_pass` → 进入卡点 1a 等待态

**多轮允许**，人不感知；人感知的第一眼是卡点 1a 卡片。

**质量清单**（spec-reviewer 使用）：
- 9 节全部非空
- 需求 8 字段在飞书 9 节中可定位（字段覆盖率）
- API 入/出参含字段名 + 类型 + 约束
- 验收标准格式为"给定输入 → 期望输出 → 判断方式"
- supersedes 判定有明确依据（不允许空 + 不允许 "待定"）

### 5.3 卡点 1a（唯一人工卡点）

**推送物**（飞书项目群卡片）：
```
[卡点 1a · 方案门] REQ-{PROJECT}-{NNN} · Spec 第 <n> 轮

Spec 链接: <飞书 Spec URL>
Reviewer TL;DR:
  - API: POST /api/v1/xxx
  - 新增表: <table_name>（<n> 字段）
  - 架构接合: <service>:<modules>
  - ACM: P0×<n>, P1×<n>, P2×<n>
  - supersedes: 取代 AC-X-007; 取代 AC-X-011
  - ARCHITECTURE 变更: +<n> 新模块, ~<n> 修改接口

[查看完整 Spec] [确认提交 → 进入转化] [返回修改]
```

**判断维度**（4 个 yes/no，技术负责人打钩）：
1. 设计方案是否合理
2. ACM 条目（priority / breaking_change）是否合理
3. supersedes 声明是否准确
4. ARCHITECTURE 演化是否可接受

**事件**：
- `checkpoint_1a_pass` → 冻结飞书 Spec + 捕获 `spec_source_revision`（此后飞书 Spec 只读）+ 进入 `SPEC_TRANSFORMING`
- `checkpoint_1a_reject` → `SPEC_REJECTED`（留档，不回退需求层状态；人工决定是否重启 `spec_start`）

### 5.4 Phase 3：转化博弈（SPEC_TRANSFORMING 内循环）

Coordinator 调度两个 Agent 博弈产出四文件。`max_rounds = 3`。

#### 5.4.1 Round 0：AC 回显（机械化，ADR-S1）

spec-transformer 在每一轮的 payload 顶层附 `round_zero_ac_ids: list[str]`——本 REQ 进入 `SPEC_TRANSFORMING` 时由 Coordinator 捕获的 `acm_active_slice` 全集，必须**逐条**回显。Coordinator 的 `round_zero_ac_recall` 规则在 Computational gate 中机械校验 `expected ⊆ declared`，缺项即 semantic finding（占 round）。

不再使用独立的 Round 0 Inferential reviewer 阶段（XML `<acknowledged_acceptance>`）。歧义陈述仍可由 transformer 在 design.md 自由文本中表达，但**不参与 gate 判定**——审计追溯靠 `transform_trace` jsonl 而非 reviewer 阶段化。完整理由见 §十二 ADR-S1。

#### 5.4.2 Round 1–3：四文件博弈

每轮步骤：

1. **spec-transformer 产出四文件 JSON payload**
   - Round ≥ 2 时：**只按上一轮 reviewer findings 做定向修改**，禁止全文重写

2. **Coordinator 跑 Computational gate**（完整 11 条规则见 §8.5）
   - 11 条规则分两类：**format 类**（schema / 正则 / 路径前缀 / 骨架唯一性 / supersedes 语法 / 元数据非空 / harness 作用域）和 **semantic 类**（`round_zero_ac_recall`、`supersedes_completeness`）。
   - **纯 format 失败 → soft retry（不占 max_rounds，最多 `max_soft_retries`，默认 2 次）**，reject 原因作为教训性反馈回 transformer（ADR-S4）。
   - 一旦混入 semantic 失败 → 占 round，进 round+1（避免 transformer 把语义错误伪装成可机械修复的格式错）。

3. **Inferential review**（spec-transformer-reviewer）
   - 5 维度：
     1. supersedes 完整性（acm-registry 切片中该触发的 retired 都在 supersedes 列表里）
     2. ac-schedule schema（非结构性语义：priority 分布是否合理、breaking_change 标记是否一致）
     3. tasks 可执行性（每 T 项动词明确、依赖合理、无悬空 AC）
     4. AC↔harness 路径一致（非路径存在，而是语义对齐：AC 描述的场景与骨架 docstring 是否匹配）
     5. 飞书 9 节覆盖（按 §四映射表每节是否有落点）
   - `transform_review_pass` → 进 Phase 4 闸门
   - `transform_review_reject` → `round += 1`，回 step 1

4. **Append `transform_trace`**（jsonl 文件，ADR-S2）
   - Coordinator 通过 `TraceWriter` 把每个事件 append 到 `trace_dir/<REQ-ID>.jsonl`（事件 = `{event, round, ts, ...}`，灵活字典而非固定 dataclass）。
   - 不写 `Requirement` 字段；仅在 `SPEC_LOCKED` 时把全文 `sha256[:12]` 摘要落到 `Requirement.transform_trace_digest` 与 Spec PR body 作审计锚（见 §5.6）。
   - `spec_restart` 时由 `archive_trace(req_id, suffix="restart")` 把当前文件移动到 `trace_dir/archive/`，新一轮重新 append。详见 ADR-S2。

#### 5.4.3 Deadlock（max_rounds=3 仍 reject）

- 触发 `transform_deadlock`
- 状态**留在 `SPEC_TRANSFORMING`**（自循环，**不回退 `SPEC_DRAFTING`**，保护人工在卡点 1a 已给出的结论）
- Coordinator 写死锁工单到项目群（见 §九卡片模板），附最近 6 条 trace
- 技术负责人决定：
  - 选项 A：手工修复四文件 → 绕过博弈直接建 Spec PR（手动触发 `transform_converged`）
  - 选项 B：打回重启卡点 1a（飞书 Spec 解冻，spec-author 重写；触发 `spec_restart` 回 `SPEC_DRAFTING`——此事件本文明确声明，补充子状态机）

### 5.5 Phase 4：SPEC_LOCKED 前闸门（Regression Scan，Gap 4）

`transform_converged` 之后、状态迁移前：

```python
active_acs = acm_registry.active_ac_ids_for_scope(req.project)
bound_acs  = scan_pytest_ac_marks("harness/tests/REQ-*/")
missing = active_acs - bound_acs
if missing:
    raise TransformConvergenceError(f"AC 未绑定骨架: {missing}")
```

- `missing ≠ ∅` → **阻断 LOCK**，带 missing 清单回 `SPEC_TRANSFORMING`（round 保持；下一轮 transformer 的 findings 输入即 missing 清单）
- `missing == ∅` → 正式进入 `SPEC_LOCKED`

### 5.6 Phase 5：Spec PR 发布（SPEC_LOCKED 生效）

Coordinator 调 `GitHubGateway`（repo 假定已存在 + 已配置 `github_repo_url`；scaffold 不在本层）：

1. 切分支 `spec/REQ-{PROJECT}-{NNN}`（已存在则复用，发生在 `on_enter_transforming` 时即创建）
2. **一次原子 commit**（ADR-S3）：四文件（design.md + tasks.md + ac-schedule.yaml + harness 骨架）+ `transform_trace.jsonl` 落到 PR + 同时变更 `acm-registry.yaml`，全部走 `commit_spec_pr_files` 单次 Git Data API 提交
3. 开 PR：
   - title: `Spec: REQ-{PROJECT}-{NNN}`
   - body: `spec_source_revision=<rev> | transform_round=<n> | transform_trace_digest=<sha256[:12]>`
4. on_locked 回调写回 `Requirement`：`spec_status=SPEC_LOCKED` / `spec_pr_url` / `spec_source_revision` / `transform_trace_digest`（Bitable 同步在更上层发生）
5. 推送"Spec 已锁定"卡片到项目群

### 5.7 Phase 6：飞书 Spec 冻结标记

- 飞书 Spec 文档标题前缀加 `[SPEC_LOCKED]`（Phase 1a 实际已冻结，Phase 6 只是可视化确认）
- 后续任何 Spec 变更走新 REQ（小改）或 Spec PR（大改），飞书 Spec 不再可编辑

---

## 六、闸门矩阵

本层所有闸门汇总。**机械前置、Inferential 居中、人工只在方案层**——保证人类注意力不被机器可判定的问题稀释。

| 闸门 | 阶段 | 类型 | 执行者 | 失败动作 | 消耗 max_rounds |
|---|---|---|---|---|---|
| context_token + revision 握手 | Phase 2 每次 spec_submit | 机械 | Coordinator | 指令重拉重写 | — |
| AI ready（Spec reviewer） | Phase 2 末 | Inferential | spec-reviewer | 回 SPEC_DRAFTING 迭代 | — |
| **卡点 1a（唯一人工）** | 卡点 1a | Human | 技术负责人 | SPEC_REJECTED 留档 | — |
| Round 0 AC 回显（`round_zero_ac_recall`） | Phase 3 每 Round | 机械（ADR-S1） | Coordinator | semantic finding，占 round | 是 |
| **Computational gate**（11 条规则，§8.5） | Phase 3 每 Round | 机械 | Coordinator | format → soft retry；混入 semantic → 占 round（ADR-S4） | 视类型 |
| Inferential review 5 维度 | Phase 3 每 Round | Inferential | spec-transformer-reviewer | round+1 定向修改 | 是 |
| **Regression scan** | Phase 4 | 机械 | Coordinator | 回 TRANSFORMING 带 missing | 否 |
| Deadlock tripwire | Phase 3 Round 3 末 | 机械 | Coordinator | 写人工工单，状态自循环 | — |

---

## 七、Spec 子状态机

### 7.1 状态字段

- `requirement.spec_status`（Bitable 字段 `Spec状态`）
- 取值：`null`（未进入）/ `SPEC_DRAFTING` / `SPEC_TRANSFORMING` / `SPEC_LOCKED` / `SPEC_REJECTED`
- 与需求主态机正交：`spec_abort` / `checkpoint_1a_reject` / `transform_deadlock` **不**回写 `requirement.status`

### 7.2 转移表

| 当前 `spec_status` | 事件 | 目标 | 触发方 | 说明 |
|---|---|---|---|---|
| null | `spec_start` | SPEC_DRAFTING | Coordinator 收到 spec-author `spec_start` callback | 同时创建飞书 Spec 文档 |
| SPEC_DRAFTING | `spec_submit` | SPEC_DRAFTING | spec-author 上报 9 节完稿 | 更新 `spec_author_summary`；不立即转态 |
| SPEC_DRAFTING | `ai_review_reject` | SPEC_DRAFTING | spec-reviewer | spec-author 继续修改 |
| SPEC_DRAFTING | `ai_review_pass` | SPEC_DRAFTING | spec-reviewer | 等待卡点 1a |
| SPEC_DRAFTING | `checkpoint_1a_pass` | **SPEC_TRANSFORMING** | 人（飞书卡片） | 冻结飞书 Spec + 捕获 `spec_source_revision` + 启动 Round 0 |
| SPEC_DRAFTING | `checkpoint_1a_reject` | SPEC_REJECTED | 人（飞书卡片） | 留档；人工决定是否重启 |
| SPEC_DRAFTING | `spec_abort` | SPEC_REJECTED | 人或超时清理 | 同上 |
| SPEC_TRANSFORMING | `transform_converged` | **SPEC_LOCKED**（经 Phase 4 闸门） | Coordinator（Phase 4 通过后） | 开 Spec PR |
| SPEC_TRANSFORMING | `transform_deadlock` | SPEC_TRANSFORMING（自循环） | Coordinator | 写人工工单；不回退 DRAFTING |
| SPEC_DRAFTING | `spec_restart` | **null**（未进入规格层） | 人 | 飞书 Spec 文档信息清空，可重新 `spec_start` |
| SPEC_TRANSFORMING(deadlocked=true) | `spec_restart` | **null**（未进入规格层） | 人（死锁工单"打回重写"按钮） | trace.jsonl 归档到 `archive/`，`spec_source_revision` / `transform_trace_digest` / `spec_pr_url` 清空 |
| SPEC_LOCKED | — | （终态） | — | 后续变更走新 spec_version |

**`spec_restart` 事件**：从 `SPEC_DRAFTING` 或 `SPEC_TRANSFORMING(deadlocked=true)` 回到 `null`（**不是 SPEC_DRAFTING**），状态机转移见 `apply_spec_event(SpecEvent.SPEC_RESTART)`。Coordinator 同时做：
1. `archive_trace(req_id, suffix="restart")` 把 `trace_dir/<REQ-ID>.jsonl` 移动到 `archive/<REQ-ID>.<ts>.restart.jsonl`（**归档不删除**，保留死锁现场审计）；
2. drop in-memory `RoundContext`；
3. 清空 `spec_status` / `spec_document_url` / `spec_document_id` / `spec_deadlocked` / `spec_transform_snapshot` / `spec_source_revision` / `transform_trace_digest` / `spec_pr_url`。

---

## 八、转化博弈详细规格

### 8.1 spec-transformer Agent

**输入**：飞书 9 节 Spec（`spec_source_revision` 锁定的那一版）+ ARCHITECTURE 当前 revision + acm-registry 切片 + 上一轮 reviewer findings（Round ≥ 2）

**输出**：单一 JSON payload（实际投递到 Coordinator 的 `handle_transformer_output(req_id, payload)`）

```json
{
  "design_md": "...",
  "tasks_md": "...",
  "ac_schedule_yaml": "version: 1\nacs:\n  - id: AC-100\n    ...",
  "harness_files": {
    "harness/tests/REQ-PROJ-001/test_ac100.py": "import pytest\n@pytest.mark.ac('AC-100')\ndef test_x(): pass\n"
  },
  "supersedes_decl": [
    {"old_ac_id": "AC-X-007", "by_ac_id": "AC-100"}
  ],
  "round_zero_ac_ids": ["AC-001", "AC-002", "AC-003"]
}
```

**字段语义**：
- `design_md` / `tasks_md` / `ac_schedule_yaml`：四文件中的内容字段，路径前缀 `docs/specs/<REQ-ID>/` 由 Coordinator 在 `_compose_pr_files` 硬编码（transformer 不传路径）
- `harness_files`：path → content；path 必须以 `harness/tests/<REQ-ID>/` 开头（`harness_path_prefix` 规则）
- `supersedes_decl`：取代关系结构化声明，`AcmRegistry.compose_patch` 据此生成 `acm-registry.yaml` 的最终 patch（transformer 不传原始 yaml diff）
- `round_zero_ac_ids`：本 REQ 进入 `SPEC_TRANSFORMING` 时活跃 AC 的回显全集（`round_zero_ac_recall` 规则校验）

**约束**：
- 不持 GitHub 凭据；所有 GitHub I/O 由 Coordinator 的 `GitHubGateway` 独占
- Round ≥ 2 只做定向修改；diff 范围受 reviewer findings 约束
- 禁止引入飞书 9 节外的新概念（Computational gate 之前，transformer 可自校验）

### 8.2 spec-transformer-reviewer Agent

**输入**：transformer 的 payload + Computational gate 已通过的证明

**输出**：单一判定
```json
{
  "verdict": "transform_review_pass" | "transform_review_reject",
  "findings": [
    { "dimension": "supersedes", "severity": "blocking", "detail": "acm-registry 中 AC-X-007 应在 supersedes，但未出现" },
    ...
  ]
}
```

**约束**：
- 只报 pass / reject 二值；不做"小问题可放行"的妥协
- findings 必须标注 dimension（5 维度之一）和 severity（blocking / advisory）
- 死锁判定由 Coordinator 做，reviewer 不自行"投降"

### 8.3 博弈参数

| 参数 | 值 | 说明 |
|---|---|---|
| `max_rounds` | 3 | 不含 Round 0 |
| Round 0 超时 | 3 min | 单个 ack 生成 + 审核 |
| Round N 超时 | 5 min | 单轮 draft + gate + review |
| 总超时 | 30 min | 超时视为 deadlock，走工单 |

### 8.4 transform_trace 记录格式（ADR-S2）

**载体**：`trace_dir/<REQ-ID>.jsonl`，append-only；`TraceWriter` 负责 append / reset / archive，事件本身是**自由 dict**（不绑死 dataclass schema），常用键：

```jsonc
{"event": "transform_started", "snapshot": { "spec_source_revision": "...", "architecture_revision": "...", "acm_registry_revision": "...", "acm_active_slice": [...] }, "ts": 1745001234.567}
{"event": "soft_retry", "round": 1, "retry": 1, "findings": [...]}
{"event": "round_used", "reason": "semantic", "round": 1, "findings": [...]}
{"event": "gate_pass", "round": 2}
{"event": "reviewer_verdict", "verdict": "converged", "findings": [], "round": 2}
{"event": "regression_retry", "attempt": 1, "missing": ["AC-007"]}
{"event": "acm_race_retry", "attempt": 1}
{"event": "locked", "pr_url": "https://github.com/..."}
{"event": "deadlock", "reason": "max_rounds"}
```

**生命周期**：
- 进入 `SPEC_TRANSFORMING` 时 `TraceWriter.reset()`；append `transform_started`。
- 每个事件由 `SpecTransformOrchestrator` 自身 append；reviewer / transformer agent 不直接写。
- `SPEC_LOCKED` 时全文 `sha256[:12]` 摘要落到 `Requirement.transform_trace_digest` 与 Spec PR body；jsonl 全文同时被打包进 Spec PR（`docs/specs/REQ-*/transform_trace.jsonl`）做单次审计快照。
- `spec_restart` 时 `archive_trace(req_id, suffix="restart")` 把当前文件移到 `trace_dir/archive/<REQ-ID>.<ts>.restart.jsonl`，下一轮 `on_enter_transforming` 重新 reset。
- 不进 `Requirement` 字段、不进 state.json，避免膨胀长生命期对象。

### 8.5 Computational gate 规则（完整清单）

实现位于 `src/requirement_workflow_v12/spec_gate.py`；`run_gate(payload, snapshot) -> GateResult`。规则分两类：**format**（落到本表 1–9）和 **semantic**（落到本表 10–11）；`format` 类参与 soft retry，`semantic` 类占 round（ADR-S4）。

| # | 规则 | kind | 说明 |
|---|---|---|---|
| 1 | `metadata_files_present` | format | `design_md` / `tasks_md` / `ac_schedule_yaml` 三个 payload 字段非空 |
| 2 | `design_md_required_sections` | format | `design.md` 同时含 `## supersedes` 与 `## 项目级上下文消费` |
| 3 | `supersedes_section_syntax` | format | `## supersedes` 段含 `no supersession` 或 `- 取代 AC-...` 行 |
| 4 | `ac_schedule_schema` | format | `ac_schedule_yaml` 解析 + 每条 AC 含必填 `{id, title, priority, given, expected, test_file, test_function}` |
| 5 | `tasks_md_format` | format | `tasks.md` 至少含一行匹配 `T-\d{3,} <subject>` |
| 6 | `path_consistency` | format | ac-schedule 中每个 `test_file` 在 `harness_files` 中存在且含 `@pytest.mark.ac('<AC id>')` |
| 7 | `harness_path_prefix` | format | `harness_files` 所有 key 以 `harness/tests/<REQ-ID>/` 开头 |
| 8 | `harness_scope_discipline` | format | `harness_files` key 不得是 Coordinator 管辖路径（`acm-registry.yaml` 或 `docs/specs/...`） |
| 9 | `skeleton_unique_anchor` | format | 每个 harness 文件**恰好一个** `@pytest.mark.ac(...)` 标记 |
| 10 | `round_zero_ac_recall` | semantic | `payload.round_zero_ac_ids` ⊇ `snapshot.acm_active_slice`（ADR-S1） |
| 11 | `supersedes_completeness` | semantic | `payload.supersedes_decl[*].old_ac_id` 全部出现在 `snapshot.acm_active_slice` |

注意事项：
- 旧版"acm-registry patch 合法性"规则**不存在**——payload 不再传原始 patch，改传 `supersedes_decl: list[{old_ac_id, by_ac_id}]`，由 `AcmRegistry.compose_patch` 在 Coordinator 侧生成最终 yaml；`harness_scope_discipline` 替它把守 harness 不越界。
- 旧版"路径规约"被拆为 `harness_path_prefix`（harness 侧）+ `_compose_pr_files` 在 Coordinator 内硬编码 `docs/specs/<REQ-ID>/` 前缀（payload 不传 design/tasks/ac-schedule 路径，只传内容字段）。

### 8.6 Regression scan 规则

Coordinator 的 `pre_lock_scan(req) -> Set[str]`：

```python
def pre_lock_scan(req) -> Set[str]:
    # 本项目所有 active AC（含本 REQ 新增、减去被 supersede 的）
    active = acm_registry.active_ac_ids(project=req.project)
    # 扫 harness/tests/REQ-*/ 下所有 @pytest.mark.ac 标记
    bound = set()
    for path in glob("harness/tests/REQ-*/**/*.py"):
        for mark in parse_pytest_marks(path):
            if mark.name == "ac":
                bound.add(mark.args[0])
    return active - bound  # missing set
```

返回非空 → 阻断 LOCK，带 missing 清单回 `SPEC_TRANSFORMING`。

---

## 九、卡片模板

### 9.1 启动 Spec 撰写卡片（Phase 1 触发）

```
[规格层] REQ-{PROJECT}-{NNN} 已 APPROVED

需求摘要：<summary>
技术范围声明：<tech_scope>
UI 需求：<needs_ui: true|false>

[启动 Spec 撰写] [推迟]
```

### 9.2 卡点 1a 方案门卡片（见 §5.3）

### 9.3 死锁工单卡片（Phase 3 deadlock）

```
[警告] REQ-{PROJECT}-{NNN} 转化博弈死锁（Round 3 未收敛）

最近 3 轮 reject 原因（from transform_trace）：
  R1: supersedes 漏报 AC-X-007
  R2: tasks.md 第 3 行缺 acceptance 锚
  R3: AC-UI-001 骨架 assert 场景与 design.md 偏离

完整 trace digest: <sha256[:12]>
可下载完整 trace: <link>

[手工修复四文件后标记 converged] [打回重启卡点 1a]
```

### 9.4 Spec 已锁定卡片（Phase 5）

```
[Spec 已锁定] REQ-{PROJECT}-{NNN}

Spec PR: <url>
spec_source_revision: <rev-id>
transform_round: <n>
新增 AC: P0×<n>, P1×<n>, P2×<n>
retired AC: <list>

生成层可以开始消费 Spec 自驱 coding。
```

---

## 十、Harness 层：Harness 实现规格（Phase 3 实施）

> 此节服务 Harness 层（方法论 §5.3），把规格层产出的骨架填充为完整测试代码。

### 10.1 目录结构

```
harness/tests/
├── REQ-PROJECT-001/                        # 由规格层产出骨架
│   ├── AC-001_valid_input/
│   │   ├── test_case.py                    # 骨架 → 填充
│   │   └── fixtures/
│   │       └── valid_request.json          # Harness 层新增
│   ├── AC-002_missing_credit_score/
│   │   ├── test_case.py
│   │   └── fixtures/
│   │       └── invalid_request.json
│   ├── AC-003_invalid_license/
│   │   ├── test_case.py
│   │   └── fixtures/
│   │       └── invalid_license.jpg
│   ├── visual/                             # needs_ui = true 时
│   │   ├── test_visual_regression.py
│   │   └── screenshots/                    # 首次 CI 通过时建立基线
│   │       ├── idle_state.png
│   │       ├── submitting_state.png
│   │       └── success_state.png
│   └── COVERAGE.md                         # 覆盖率矩阵，卡点 1b 消费
├── conftest.py                             # 共享 fixture
└── README.md
```

**关键规则**：
- 每个 AC 一个目录，目录名 `{AC-ID}_{slug}`
- 卡点 1b 通过后，当前 REQ 的 Harness 目录**只读**
- CI 运行全部 Harness（`pytest harness/tests/`），含所有历史 REQ
- 新实现**不得**删除旧 REQ 已覆盖的 AC 测试（除非显式 BREAKING CHANGE + acm-registry patch 标 retired）

### 10.2 骨架 → 完整代码的转化

规格层产出的骨架：
```python
@pytest.mark.ac("AC-001")
def test_returns_200_with_valid_fields(api_client):
    """docstring from ac-schedule"""
    pytest.skip("skeleton — fill in during impl phase")
```

Harness 层填充后：
```python
@pytest.mark.ac("AC-001")
def test_returns_200_with_valid_fields(api_client):
    """AC-001 [P0] 有效输入返回风控报告"""
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
    assert len(body["report_id"]) == 36
```

**硬约束**：
- `@pytest.mark.ac` 参数、函数名、文件路径**不得修改**（与 ac-schedule.yaml 锁定一致）
- docstring 首行与 ac-schedule `title` 一致
- 删除 `pytest.skip`

### 10.3 视觉回归测试

```python
# harness/tests/REQ-PROJECT-001/visual/test_visual_regression.py
import pytest
from playwright.sync_api import Page, expect

SCREENSHOT_DIR = "harness/tests/REQ-PROJECT-001/visual/screenshots"
THRESHOLD = 0.02  # 2% 像素差异容忍

@pytest.mark.ac("AC-UI-001")
def test_submitting_state(page: Page, app_base_url: str):
    """AC-UI-001 [P0] 提交中 SubmitButton 禁用"""
    page.goto(f"{app_base_url}/risk-report")
    fill_valid_form(page)
    with page.expect_request("**/api/v1/risk-report"):
        page.click("[data-testid=submit-button]")
        screenshot = page.screenshot()
    assert_visual_match(screenshot, f"{SCREENSHOT_DIR}/submitting_state.png", THRESHOLD)
    expect(page.locator("[data-testid=submit-button]")).to_be_disabled()
```

### 10.4 覆盖率矩阵 COVERAGE.md

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

### 10.5 卡点 1b 飞书卡片

```
[卡点 1b · Harness 门] REQ-PROJECT-001 · Harness PR #45

覆盖率矩阵（见 COVERAGE.md）：
  AC-001 [P0] → AC-001_valid_input/test_case.py ✅
  AC-002 [P0] → AC-002_missing_credit_score/test_case.py ✅
  AC-003 [P0] → AC-003_invalid_license/test_case.py ✅
  AC-UI-001 [P0] → visual/test_visual_regression.py ✅

P0 全覆盖：✅（4/4）
历史回归：N/A（首版）

[查看 Harness PR] [确认 Harness] [打回重生成]
```

---

## 十一、Spec 版本管理规则

| 情况 | 处理方式 |
|---|---|
| 现有功能 Bug | 直接开 Impl PR 修复，不需要新 Spec |
| 行为不符预期但测试通过 | Spec AC 写错了；需要新 Spec（increment `spec_version` 或新 REQ） |
| 新增能力 | 新 REQ（新 REQ ID，走完整六阶段流程） |
| 性能改进 | 新 REQ；变更 AC 标记 `breaking_change: true` |
| BREAKING CHANGE | 必须在 design.md `## supersedes` 声明 + acm-registry patch 将被取代 AC 标 `retired`；触发 acm-registry 兼容性告警 |

---

## 十二、实现侧 ADR：与本文叙述的刻意偏离

> 本节登记规格层实现侧（`src/requirement_workflow_v12/`）相对于本文 §五–§九 叙述的 4 处刻意偏离。每条都是基于工程权衡做出的设计决策，不是 bug；`spec-harness-layer.md` 与代码若发生冲突，以本节为准。日期：2026-04-17。

### ADR-S1 Round 0 AC 回显机械化（非 Inferential reviewer）

**与本文偏离**：§5.4.1 + §6 闸门矩阵描述 Round 0 由 spec-transformer-reviewer 做 Inferential 审核、独占一轮且不消耗 `max_rounds`。

**实际决策**：把"AC id 集合覆盖"下沉为 `spec_gate.py` 的 `round_zero_ac_recall` **语义规则**，与其他 Computational gate 规则同回合（Round 1+）执行。transformer 在每轮 payload 自带 `round_zero_ac_ids` 字段，Coordinator 用集合差判定遗漏。`SpecTransformOrchestrator.RoundContext.round_index` 从 1 起，无 Round 0 分支。

**理由**：
- "AC id 集合覆盖"本质是机械可判定问题，不需要 Inferential 判断
- 节省每 REQ 至少一次 reviewer 唤起 + 一次 trace 事件
- reviewer 无需持有 acm-registry 切片，符合最小授权（§8.1 仅 transformer 读 ACM 切片）

**失去**：对"AC id 全在但表达偏离"的歧义，reviewer 没有专门的 Round 0 窗口，需到 Round 1 起按 5 维度才能拍砖。

**反向退路**：若 deadlock 率显著上升，恢复 Inferential Round 0 只需 (a) 给 reviewer 加 acm-registry 切片输入、(b) `NextAction` 加 `wake_reviewer_round_zero`、(c) 调整 `RoundContext.round_index` 默认值——改动局部。

### ADR-S2 transform_trace 落 jsonl 文件（非 state.json 字段）

**与本文偏离**：§8.4 描述 trace 应作为 `Requirement.transform_trace: list[TransformEvent]` 持久化到 state.json，Bitable 仅存 `sha256[:12]` digest。

**实际决策**：trace 落到 `state/spec_traces/{REQ-ID}.jsonl` 独立文件，append-only；state.json **不**新增 `transform_trace` 字段；converged 时 jsonl 文件内容作为 Spec PR 工件（`docs/specs/{req}/transform_trace.jsonl`）进 GitHub 审计链。`spec_source_revision` 与 `transform_trace_digest` 仍以 Requirement 字段形式（见 ADR-S2 配套 Chunk D）回写 Bitable。

**理由**：
- state.json 是 Coordinator 全状态镜像，trace 是高写入（每轮 ≥3 事件）、低读取频率工件；进 state.json 会拖慢 store flush
- jsonl 天然 crash-safe（只 append），无需事务包裹
- 进 PR 后 GitHub 才是 source of truth，state.json 不再是单点
- digest 由 jsonl 文件懒计算即可，不必常驻 state.json

**失去**：`coord status` 类 CLI 工具看不到 trace 摘要，需直接读文件或拿 PR digest。

**反向退路**：若需 state.json 可见 digest，只需在 `_on_spec_locked` 前 hash jsonl 内容写入 `Requirement.transform_trace_digest`（Chunk D 已计划），不必把 trace 内容也搬进 state.json。

### ADR-S3 Spec PR 一次原子 commit（非两次）

**与本文偏离**：§5.6 描述 Phase 5 应分两次 commit：先四元数据文件 + harness 骨架，再 acm-registry 根仓库 patch。

**实际决策**：用 GitHub Git Data API（blob → tree → commit → ref）一次原子 commit 包含全部文件（`design.md` / `tasks.md` / `ac-schedule.yaml` / `harness/tests/REQ-*/...` / `acm-registry.yaml` / `transform_trace.jsonl`）。`GitHubGateway.commit_spec_pr_files` 单方法承载。

**理由**：
- 两次 commit 的中间态（只有四文件 + 旧 acm-registry）是非法状态：reviewer 已基于新切片判过 supersedes，旧 registry 与新四文件不自洽
- 单 commit 让 `git revert <sha>` 一次回滚整套
- 原子语义在 Git Data API 内部已天然支持，无额外成本

**失去**：无法用 commit 范围拆分回退（比如只回退 acm-registry patch 保留四文件）。

**反向退路**：拆为 `_commit_metadata` + `_commit_acm_patch` 两个原子操作，顺序约束写在 `_on_converged` 即可。

### ADR-S4 Soft retry 范围限定 pure-format

**与本文偏离**：§8.5 写"Computational gate 失败 → 回 transformer 带失败清单（不占 max_rounds）"，暗示**所有**机械失败都软重试。

**实际决策**：软重试**仅当** `GateResult.has_format_failure and not has_semantic_failure` 且未超 `max_soft_retries=2`。任何 semantic gate 失败（`round_zero_ac_recall` / `supersedes_completeness`）立即占用 round 推进。

**理由**：
- Format 失败是"打字错"（YAML 缩进、tasks 行格式、缺段）——立即重试代价低、收敛概率高
- Semantic 失败反映"理解错"——需要 reviewer 介入或下一轮 deeper context refresh，不该在同一轮无限重试遮蔽真问题
- `max_soft_retries=2` 防止 transformer 卡死同一类格式错误（实践中观察到 LLM 偶在缩进上反复栽倒）

**失去**：semantic 失败的 REQ 总轮次 = format 失败时的轮次（reviewer 看不到的细节多）。

**反向退路**：把 semantic 也纳入软重试，只需删掉 `not has_semantic_failure` 条件；但需要同步重新评估 `max_soft_retries` 上限。

### ADR 索引

| ADR | 主题 | 触动文件 | 配套 Chunk |
|---|---|---|---|
| S1 | Round 0 机械化 | spec_gate.py、spec_transform.py | （已落地）|
| S2 | trace jsonl 文件化 | spec_transform.py（TraceWriter）| Chunk D（digest 回写） |
| S3 | 一次原子 commit | github_gateway.py、spec_transform.py（_compose_pr_files） | （已落地）|
| S4 | Soft retry pure-format only | spec_transform.py（handle_transformer_output） | （已落地）|

---

*v2 · 2026-04-16 · 六阶段工作流 + 四文件 Spec + 转化博弈 + 四道工程化闸门。*
*v2.1 · 2026-04-17 · 追加 §十二 实现侧 ADR：登记 4 处与本文叙述的刻意偏离。*
*参见: [epics/spec-transform-epic-2026-04.md](../epics/spec-transform-epic-2026-04.md) · [infra/harness-engineering-industry-alignment-2026-04-16.md](../infra/harness-engineering-industry-alignment-2026-04-16.md)*
