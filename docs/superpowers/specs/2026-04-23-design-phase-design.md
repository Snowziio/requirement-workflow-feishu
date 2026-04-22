# Design 阶段完整设计规格

> 本规格定义 `APPROVED → PlanStatus.DRAFTING` 之间、当 `needs_ui=true` 时生效的 **Design 阶段**完整职责、状态机、制品、端点与人机协作流程。
>
> 核心定位：Design 阶段**不自建多轮 IM agent**。由 Claude Design（`claude.ai/design`）作为外部工具承载 UI/UX 设计工作，coordinator 只做**上下文桥 + 状态机 + 归档**三件事；OpenClaw 只用一个单轮 skill `design-brief-author` 在进场前生成结构化 Brief。
>
> 关联文档：
> - 方法论：[harness-engineering-methodology-v3.0.md](../../context/harness-engineering-methodology-v3.0.md) §6.2 规划层
> - 规划层规格：[planning-harness-layer.md](../../context/layers/planning-harness-layer.md) §四 / §六（Design 侧当前为 stub，本文是其正式化）
> - Plan 层设计：[2026-04-19-planning-phase-design.md](./2026-04-19-planning-phase-design.md)（DesignStatus 被定义但未落地；本文接续）
> - Project 层 / Bootstrap：[2026-04-20-project-layer-design.md](./2026-04-20-project-layer-design.md)（本文的前置依赖源）

---

## 零、变更记录

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v1 | 2026-04-23 | 首版：定义 DesignStatus 三态机（含 SUBMIT_PENDING_REVIEW 中间态）；采用 Claude Design 作为外部 UI 工具；`design-brief-author` 单轮 skill；飞书 zip 附件上传作为 intake 协议；`design/` 项目级目录结构；每 REQ 全量快照不追 drift；前端默认栈 Vite + React + TS + Tailwind + shadcn/ui |

---

## 一、目标与使命

### 1.1 核心使命

对 `needs_ui=true` 的 REQ，产出一份下游（Plan / Spec / Impl）可机器消费、又能防跨 REQ 视觉漂移的 **Design Artifact**。

三条硬性交付：

1. **设计意图** — 人类可读的 Design Brief + handoff bundle 原件（飞书 design docx + `design/archive/<req>/`）
2. **可追溯身份** — `design/PAGES.yaml` Page Registry 增量（本 REQ 新增/修改了哪些 page）
3. **完整 UI 快照** — 每 REQ 一份自包含的 Claude Design handoff bundle 归档，供实施期 Claude Code 作为视觉规范

### 1.2 不做的事（明确非职责）

- **不自建多轮 IM agent**。UI 视觉决策是人工作业，agent 的"骨架 → 深入 → 定稿"多轮对话不适合 UI 层
- **不做 file-level diff / drift 追踪**。方法论 v1（本规格）采用"每 REQ 自包含快照"简化模型；drift 由下次 REQ 设计师点 Claude Design "Sync now" 自然消解，不维护偏离台账
- **不做 per-page 分级策略（A/B/C）**。简化模型不需要
- **不强制目标代码仓固定目录结构**。Claude Design 官方明确说"不要复制 bundle 内部结构，按视觉重做"——我方代码组织约定只在 CLAUDE.md 里给建议，不做 CI 强制
- **不实施 Bootstrap 层变更**。本层依赖 Bootstrap 提供前置条件（见附录 A），Bootstrap 本身的设计归下一轮

### 1.3 适用范围

- 触发条件：`requirement.status == APPROVED` 且 `requirement.needs_ui == true`
- 前置条件：见附录 A
- 下游消费：Plan 层 `/queries/openclaw/plan-context/` 增加 `design_artifact_ref` 字段；Spec 层同理；Impl 层由 CLAUDE.md 指令规范

---

## 二、状态机

### 2.1 DesignStatus 三态扩展

```
null ──(DESIGN_START)──▶ DRAFTING ──(DESIGN_SUBMIT)──▶ SUBMIT_PENDING_REVIEW
                           ▲                                  │
                           │                                  │
                           │──(DESIGN_FINAL_REJECT)───────────┤
                           │                                  │
                           │                        (DESIGN_FINAL_APPROVE)
                           │                                  ▼
                           │                                READY
                           │                                  │
                           │                                  ▼
                           │                       解锁 PlanStatus 启动前置
                           │
                           │ (DESIGN_RESTART 可在任意非 null 态触发 → null)
```

当前代码已有：`DesignStatus = {DRAFTING, READY}` + 事件 `{DESIGN_START, DESIGN_SUBMIT, DESIGN_RESTART}` + `design_restart()` 级联重置方法（`coordinator_service.py:984`）。本规格**扩展**为：

### 2.2 状态集

```python
class DesignStatus(str, Enum):
    DRAFTING              = "DESIGN_DRAFTING"
    SUBMIT_PENDING_REVIEW = "DESIGN_SUBMIT_PENDING_REVIEW"   # 新增
    READY                 = "DESIGN_READY"
```

### 2.3 事件集

```python
class DesignEvent(str, Enum):
    DESIGN_START           = "design_start"
    DESIGN_SUBMIT          = "design_submit"                  # 既有，语义调整：DRAFTING → SUBMIT_PENDING_REVIEW（不再直接到 READY）
    DESIGN_FINAL_APPROVE   = "design_final_approve"           # 新增
    DESIGN_FINAL_REJECT    = "design_final_reject"            # 新增
    DESIGN_RESTART         = "design_restart"                 # 既有
```

### 2.4 转移规则

| 当前 | 事件 | 下一态 | 守卫 |
|---|---|---|---|
| `null` | `DESIGN_START` | `DRAFTING` | `requirement.status == APPROVED && needs_ui` |
| `DRAFTING` | `DESIGN_SUBMIT` | `SUBMIT_PENDING_REVIEW` | bundle intake 成功（zip 已解压到 `design/archive/`） |
| `SUBMIT_PENDING_REVIEW` | `DESIGN_FINAL_APPROVE` | `READY` | 操作者属于创建群 / 技术负责人名单 |
| `SUBMIT_PENDING_REVIEW` | `DESIGN_FINAL_REJECT` | `DRAFTING` | 同上 |
| 任意非 `null` | `DESIGN_RESTART` | `null` | 已有，级联 Plan + Spec |

### 2.5 与 Plan / Spec 并行列的关系

DesignStatus 是 PlanStatus 启动的**前置条件**（仅当 `needs_ui=true`）：

```
needs_ui=true:
  DesignStatus: null → DRAFTING → SUBMIT_PENDING_REVIEW → READY
  PlanStatus:   null ──────────────── waiting ─────────────→ DRAFTING
                                                    ↑ (only after DesignStatus=READY)

needs_ui=false:
  DesignStatus: null（永不进入）
  PlanStatus:   null → DRAFTING → ...
```

SpecStatus 的 precondition 不变（仍是 `PlanStatus == READY`）。

### 2.6 失败回退

- `DESIGN_FINAL_REJECT` → 退回 `DRAFTING`；对应 `design/archive/REQ-XXX_<slug>/` 目录在新分支中标记 `REJECTED.md`，PR 不 merge，保留内容供设计师参照修改
- `DESIGN_RESTART` → DesignStatus 重置为 null，级联 PlanStatus、SpecStatus 全部重置（既有行为不变）；`design/archive/` 下本 REQ 的归档保留（便于审计），标记为 `RESTARTED.md`

---

## 三、分工

| 角色 | 干什么 | 不干什么 |
|---|---|---|
| **Coordinator** | DesignStatus 状态机；派发 skill；飞书 design docx 编排；Bundle intake；`design/archive/` 归档；Registry 写入；GitHub 单向同步 | 不产生设计内容；不持有 AI 能力；不做 file-level diff |
| **OpenClaw Skill `design-brief-author`**（新建，单轮） | 从 REQ 8 字段 + 项目上下文 + Registry，生成结构化 Brief 一次性 callback 回 coordinator | 不做多轮 IM；不做终审；不读 Claude Design；不产生设计稿 |
| **设计师（人）** | 接 BRIEF → 进 Claude Design 点 Sync now → 迭代 → Export zip → 飞书上传 | 不写代码；不维护 PAGES.yaml（coordinator 自动写） |
| **技术负责人（人）** | 点 D-DESIGN-2 终审卡（通过 / 打回） | 不做设计；不动代码 |

---

## 四、端到端流程

### 4.1 Step 0｜前置（Project 寿命层 Bootstrap 一次性做）

**触发**：Project Bootstrap
**责任方**：项目 owner + 设计负责人

1. Bootstrap 从 `Snowziio/Template-repository` 创建项目仓库，按 `architecture_templates/*.yaml` 渲染 `docs/ARCHITECTURE.md` 含 "## UI Context" 节
2. `populate_files` 额外写入（本规格对 Bootstrap 的新增要求，附录 A）：
   - `design/README.md`
   - `design/PAGES.yaml`（空骨架）
   - `design/INDEX.md`（空骨架）
   - `design/system/.gitkeep`
   - `design/archive/.gitkeep`
3. 前端脚手架按 category 对应栈 scaffold 到 `src/{pkg}_webapp/`（or `src/{pkg}_miniapp/`）
4. 设计师在 Claude Design 建 Project → Import GitHub 仓库 → 搭组织级 Design System
5. 设计师把 Claude Design Project URL 回填到 Bootstrap 卡片 → coordinator 写入 `ProjectConfig.claude_design_project_url`
6. 设计师从 Claude Design export 一次 DS 快照 → 通过 Bootstrap 提供的上传入口存入 `design/system/`

> **本规格对 Bootstrap 的依赖以附录 A 形式存档，实施归 Bootstrap 层下一轮规格。**

---

### 4.2 Step 1｜进入 DRAFTING（`DESIGN_START`）

**触发**：REQ 正式批准（`WorkflowStatus = APPROVED`）且 `needs_ui=true`
**自动 / 手动**：自动（由 approve_requirement 的 post-hook 触发）

**Coordinator 动作**：

1. `apply_design_event(null, DESIGN_START)` → `DRAFTING`
2. 飞书创建 per-REQ design docx → 回写 `Requirement.design_doc_id` / `design_doc_url`
3. 派发 OpenClaw skill `design-brief-author`：
   - 通过飞书私聊把 handoff text 发给设计师（含 `req_id` + "开始设计 Brief 生成"指令）
   - skill 从 OpenClaw 拉 `GET /queries/openclaw/design-context/<req_id>`
4. skill 产出 `BRIEF` payload → callback `POST /openclaw/design-callback`
5. Coordinator 接到 callback：
   - 把 Brief YAML frontmatter 保存到 `Requirement.pending_design_brief` 字段
   - 把 Brief 正文（含首轮 prompt）写入飞书 design docx（模板化结构）
6. Coordinator 推**"设计启动卡"**到项目群 + 设计师私聊：
   - 显示：`req_id` / 需求摘要 / BRIEF 飞书链接 / `claude_design_project_url`
   - 操作指南："先点 Sync now → 粘贴 BRIEF → 迭代 → Export → 回来点卡片上传"
   - 按钮：**打开飞书 Brief** / **前往 Claude Design** / **上传 Handoff**（待下一步启用）

**人做什么**：等卡片收到，进入下一步

---

### 4.3 Step 2｜Claude Design 作业（DRAFTING 期间）

**主体**：设计师（唯一操作者）

1. 从飞书 design docx 复制 BRIEF 正文
2. 打开 Claude Design Project → 点 **"Sync now"**（拉最新代码态）
3. 把 BRIEF 粘进 Claude Design 首轮 prompt
4. 多轮迭代：chat / inline 评论 / 旋钮 / 直接编辑
5. 对 BRIEF 里 `expected_pages[]` 逐条自检：是否覆盖、是否冗余、是否缺失
6. 完成后：**Export → Handoff to Claude Code** → 下载 zip 到本地

**Coordinator 动作**：无（纯人工作业期）

**上下文交接方式**：飞书 docx → 人手工复制 → Claude Design chat。单向、手动、无 API。

---

### 4.4 Step 3｜提交（`DESIGN_SUBMIT`）—— Bundle Intake

**触发**：设计师在"设计启动卡"上点 **"上传 Handoff"** 按钮 → 选择本地 zip 附件
**端点**：`POST /cards/design-upload-bundle`

**Coordinator intake handler**：

1. 验证：卡片 action 有效、`req_id` 存在、`DesignStatus == DRAFTING`
2. 从飞书 File API 下载 zip 到临时目录
3. 解压到 `design/archive/REQ-XXX_<slug>/extracted/`（Chinese 文件名 UTF-8 修复；见 §5.5 实现注意）
4. 保留原始 `bundle.zip` 到同目录（>10MB 进 git-lfs；需要项目 `.gitattributes` 配置，附录 A）
5. 生成 `MANIFEST.md`：
   - 读 extracted bundle 的内部 README（`extracted/untitled/project/design_handoff_*_v*/README.md`）提取 prose 摘要
   - 从 bundle bare src/ 文件名识别本次涉及的 pages（display_name 来源）
   - 记录 export 类型：`pure_export` / `anchor_bump`（通过检测嵌套 anchor 目录的 SHA-256 是否为首次出现决定）
6. 生成 `BRIEF.md` 的归档副本：从 `Requirement.pending_design_brief` 冻结到 archive 目录
7. 更新飞书 design docx：追加"已收到 handoff / MANIFEST 摘要 / 等待终审"
8. `apply_design_event(DRAFTING, DESIGN_SUBMIT)` → `SUBMIT_PENDING_REVIEW`
9. `on_enter(SUBMIT_PENDING_REVIEW)` hook：推送 **D-DESIGN-2 终审卡**到项目群

**终审卡**内容：

- MANIFEST 摘要（pages 增删改 + bundle 内部 README 节选）
- `claude_design_project_url` 跳转链接
- `design/archive/REQ-XXX_<slug>/` 的 PR 预览 URL（临时分支未 merge）
- 两个按钮：**通过** (`/cards/design-final-approve`) / **打回** (`/cards/design-final-reject`)

**人做什么**：无（自动处理期）

---

### 4.5 Step 4｜终审（D-DESIGN-2）

**触发**：技术负责人在项目群点按钮
**端点**：`POST /cards/design-final-approve` / `design-final-reject`

**路径 A — 通过**：

1. `apply_design_event(SUBMIT_PENDING_REVIEW, DESIGN_FINAL_APPROVE)` → `READY`
2. `on_enter(READY)` hook 原子操作：
   - 更新 `design/PAGES.yaml`：新增 / 修改条目（schema 见 §5.2）
   - 更新 `design/INDEX.md`：追加时间线条目
   - （可选）更新 `design/DECISIONS.md`：由终审人在卡片上勾选"纳入决策总账"
   - 原子 commit 到 GitHub（与 plan 层 `on_enter(READY)` 同构）：
     - `design/archive/REQ-XXX_<slug>/`（全部）
     - `design/PAGES.yaml`（更新）
     - `design/INDEX.md`（更新）
     - 可选 `design/DECISIONS.md`（更新）
     - 单个 commit，message: `design: lock handoff for REQ-XXX`
   - 回写 `Requirement.design_archive_path` / `design_github_revision` 审计字段
3. `on_exit(READY)` hook：解锁 PlanStatus 启动前置条件（`Requirement.design_precondition_met = True`）

**路径 B — 打回**：

1. `apply_design_event(SUBMIT_PENDING_REVIEW, DESIGN_FINAL_REJECT)` → 退回 `DRAFTING`
2. 在临时分支的 `design/archive/REQ-XXX_<slug>/REJECTED.md` 写入打回意见（终审人卡片填写）
3. PR 不 merge；临时分支保留
4. 通知设计师修改后重新 export 并重新上传

**人做什么**：点一个按钮（+ 可选填理由）

---

### 4.6 Step 5｜下游消费 Design Artifact

#### Plan 层

`/queries/openclaw/plan-context/<req>` 增加字段：

```yaml
design_artifact:
  archive_path: "design/archive/REQ-XXX_report-editor-tweaks/"
  pages_touched:
    - { display_name: ReportEditor, action: modify }
    - { display_name: ApprovalToast, action: new }
  claude_design_project_url: "https://claude.ai/design/projects/xyz"
```

`plan-author` 读它做决策输入；plan.md 里涉及 UI 组件选型的 Decision 可以引用 `design_artifact.archive_path`。

#### Spec 层

`/queries/openclaw/spec-context/<req>` 同样增加 `design_artifact` 字段；`spec-author` 写 UI 相关 AC 时参照。

#### 实施期（Claude Code）

通过 CLAUDE.md 指令段规范：

```markdown
## Design Reference Rules（来自 design 层，由 Bootstrap 植入 / 维护）

本 REQ 实施时，视觉规范以 `design/archive/<CURRENT_REQ_ID>_*/extracted/` 为准。

1. **样式翻译原则**：bundle 里的 JSX 是 React-via-CDN 原型，不是生产代码。
   - 按视觉效果在前端栈中重新组织（见 docs/ARCHITECTURE.md > UI Context）
   - CSS tokens 来自 `extracted/*/assets/colors_and_type.css`，落到前端工程的 `src/lib/tokens.ts` + `tailwind.config.js`
2. **历史归档**：`design/archive/<其他 REQ>/` 仅用于追溯，不作为本 REQ 的规范
3. **Commit message 引用**：前端 UI 实施 commit 的 message 必须含 `design: <REQ-ID>_<slug>` tag
```

---

## 五、核心制品 Schema

### 5.1 `BRIEF.md`（skill 产出 + 归档固化）

YAML frontmatter + Markdown 正文：

```markdown
---
schema_version: "1.0"
req_id: "REQ-PROJ-007"
generated_at: "2026-04-23T14:00:00+08:00"
generated_by: "design-brief-author@1.0"

expected_pages:
  - display_name: ReportEditor
    action: modify                       # new | modify
    existing_page_ref: ReportEditor      # 仅 modify 时；与 PAGES.yaml 的条目匹配
    intent: 增加右侧面板可折叠功能
    key_interactions:
      - 点击折叠按钮 → 右侧面板宽度 0
      - 折叠态下仍保留顶部图标供展开
    must_cover_states: [default, collapsed]

  - display_name: ApprovalToast
    action: new
    intent: 审核通过/拒绝时的结果提示
    key_interactions:
      - 3 秒自动消失
      - 通过=绿色，拒绝=红色
    must_cover_states: [success, error]

design_system_hints:
  - 使用 Quant Indigo 主色（--brand-500）作为主按钮
  - 字体遵循 DS：IBM Plex Sans / SC / Mono

cross_req_references:
  prior_archive: design/archive/REQ-PROJ-006_xxx/
  prior_summary: |
    （引用上一 REQ 的 MANIFEST 摘要供设计师了解上下文）
---

# 首轮 Prompt（供设计师粘到 Claude Design chat）

## 背景
（来自 REQ 8 字段的自然语言摘要，约 100–200 字）

## 本次需要交付的 pages

### 1. ReportEditor（修改）
（intent / interactions / states 的人读展开）

### 2. ApprovalToast（新增）
...

## 设计系统约束
（design_system_hints 的人读展开）

## 前一 REQ 上下文
（cross_req_references 的人读展开）
```

**字段语义**：

- `expected_pages[]` 是本 REQ 预期设计师在 Claude Design 里产出的 page 清单；设计师自检 Coverage 时参照
- `action = modify` 时 `existing_page_ref` 必填，matches PAGES.yaml 条目的 `display_name`
- `must_cover_states` 最低包含 `default`；UI 组件按场景加 `empty / error / loading / success` 等
- `design_system_hints` 是来自 ARCHITECTURE.md UI Context 和 `design/system/` 的提示；非强制

---

### 5.2 `design/PAGES.yaml`（Project-level Registry）

```yaml
schema_version: "1.0"

pages:
  - display_name: Dashboard
    created_by_req: REQ-PROJ-001
    last_modified_by_req: REQ-PROJ-003
    latest_archive_ref: design/archive/REQ-PROJ-003_report-editor-tweaks/
    target_component: DashboardPage       # 实施后回填；初始空串
    target_route: /dashboard              # 实施后回填；初始空串
    bundle_src_hint: src/Dashboard.jsx    # bundle 里对应的简化原型文件名（供 Brief 生成 cross-reference）

  - display_name: ReportEditor
    ...
```

**字段语义**：

- `display_name` 是 Registry 主键（唯一约束）；语义同 Claude Design canvas 上的 page 标题 / bundle src 文件名
- `target_component` / `target_route` 在 Impl 阶段由 Claude Code 回填（本层不写）
- `bundle_src_hint` 是"Claude Design handoff 里对应的原型文件"的**线索**，不是强契约——bundle 内部结构可变

**不包含的字段**（刻意不做）：

- ❌ `drift_strategy` — v1 不做 drift 分级
- ❌ `claude_design_page_ref` — Claude Design 不稳定暴露 per-page URL
- ❌ `supersedes` — v1 不维护历史链

---

### 5.3 `design/archive/REQ-XXX_<slug>/MANIFEST.md`

```markdown
---
req_id: REQ-PROJ-007
archived_at: "2026-04-23T15:30:00+08:00"
archived_by: coordinator-service

export_type: pure_export                 # pure_export | anchor_bump
anchors_in_bundle:
  - folder_name: design_handoff_投资经理助手_v2
    tree_sha256: a1b2c3d4...
    first_seen_in_req: REQ-PROJ-004      # 若 export_type == anchor_bump 且首次出现

pages_touched:
  - display_name: ReportEditor
    action: modify
    expected_from_brief: true            # Brief 里声明了 → 实现了
  - display_name: ApprovalToast
    action: new
    expected_from_brief: true
  - display_name: UploadModal
    action: new
    expected_from_brief: false           # Brief 里没声明但 bundle 里多出来的
    coverage_note: "设计师主动新增，见 Claude Design chat"

bundle_inner_readme_excerpt: |
  （摘抄自 extracted/untitled/project/design_handoff_*_v*/README.md 前 500 字）
---

# REQ-PROJ-007 Design Handoff Summary

## Brief → Handoff Coverage

### Covered（expected_from_brief=true 且实现）
- [x] ReportEditor: 新增右侧面板折叠交互
- [x] ApprovalToast: 通过/拒绝两状态

### Extra（Brief 外新增）
- UploadModal: 设计师判断需要的额外弹窗

### Missing（expected_from_brief=true 但未实现）
（如有）

## Reviewer Notes（D-DESIGN-2 终审人填写）
_待填_
```

**字段语义**：

- `export_type` 通过检测嵌套 anchor 目录的 tree_sha256 是否已在前序 `design/archive/*/MANIFEST.md.anchors_in_bundle` 里出现决定
- `pages_touched[]` 与 `BRIEF.md.expected_pages[]` 逐条对比 → 自动标注 `expected_from_brief`
- `bundle_inner_readme_excerpt` 保留 Claude Design 的 prose delta 描述，供下游 Plan / Spec 参考

---

### 5.4 `design/INDEX.md`（自动生成的时间线）

```markdown
# Design Handoff Index

<!-- Auto-generated by coordinator on DESIGN_READY. DO NOT edit by hand. -->

## 2026-04-23 | REQ-PROJ-007 | Report Editor Tweaks
- Archive: [design/archive/REQ-PROJ-007_report-editor-tweaks/](./archive/REQ-PROJ-007_report-editor-tweaks/)
- Pages touched: ReportEditor (modify), ApprovalToast (new), UploadModal (new)
- Commit: abc1234

## 2026-04-22 | REQ-PROJ-006 | Initial Upload Flow
- ...
```

格式：新条目 prepend 到顶（时间倒序）。

---

### 5.5 Intake handler 对 zip 的处理实现注意

1. **中文文件名编码**：Claude Design 的 zip 用 cp437 编码 filename（Unix zipinfo 踩坑）。Python 实现必须做：
   ```python
   info.filename = info.filename.encode("cp437").decode("utf-8")
   ```
2. **双层内容**：每个 bundle 的 `project/` 下同时有 bare `src/` + 嵌套 `design_handoff_..._v{N}/src/`，两者在 anchor bump 时一致、bump 之后 bare 继续演化、嵌套冻结。intake 时保留整棵 extracted 树，无需去重（v1 简化策略）
3. **Anchor 哈希**：为 MANIFEST 生成 `anchors_in_bundle[].tree_sha256`，算法：对嵌套目录排序后逐文件 sha256 → concat → final sha256。**仅用于元数据识别**，v1 不做全局池 dedup
4. **失败回滚**：intake 任一步失败（解压 / 写盘 / 飞书同步 / 分支推送）→ 回滚本 REQ 的所有本次变更 → 状态保持 DRAFTING → 推送失败卡片让设计师重传

---

## 六、目录结构

### 6.1 项目仓库视角

```
<project-repo>/
├── README.md
├── CLAUDE.md                              # 含 "## Design Reference Rules" 节（Bootstrap 植入）
├── .gitattributes                         # git-lfs 规则：design/archive/**/bundle.zip filter=lfs
├── .gitignore
├── docs/
│   └── ARCHITECTURE.md                    # 含 "## UI Context" 节（来自 architecture_templates YAML 渲染）
├── design/
│   ├── README.md                          # 方法论契约说明（Bootstrap 植入）
│   ├── INDEX.md                           # 时间线（coordinator 维护）
│   ├── PAGES.yaml                         # Page Registry（coordinator 维护）
│   ├── system/                            # 组织级 DS 快照（Bootstrap 首次填充）
│   │   ├── README.md
│   │   ├── tokens/
│   │   └── ui-kit-manifest.md
│   └── archive/
│       └── REQ-PROJ-007_<slug>/           # 逐 REQ 自包含归档
│           ├── BRIEF.md                   # 进场前 Brief（冻结版）
│           ├── MANIFEST.md                # 本次摘要 + coverage
│           ├── bundle.zip                 # 原始（git-lfs）
│           ├── extracted/                 # 解压全量
│           │   └── untitled/...
│           └── REJECTED.md                # 仅打回时存在
├── src/
│   ├── {pkg}/                             # 后端 Python
│   └── {pkg}_webapp/                      # 前端脚手架（Bootstrap 植入）
│       ├── package.json
│       ├── src/
│       │   ├── app/
│       │   ├── components/{ui,features,layouts}/
│       │   └── lib/tokens.ts
│       └── ...
└── project/
    ├── README.md
    ├── req-registry.yaml
    └── environments.yaml
```

### 6.2 coordinator 源码视角（新增/修改清单）

| 文件 | 动作 | 目的 |
|---|---|---|
| `src/requirement_workflow_v12/plan_state_machine.py` | 修改 | 扩展 DesignStatus 为三态 + 新增事件 + 转移规则 |
| `src/requirement_workflow_v12/models.py` | 修改 | `Requirement` 新增字段：`design_doc_id` / `design_doc_url` / `design_archive_path` / `design_github_revision` / `design_precondition_met` / `pending_design_brief` |
| `src/requirement_workflow_v12/store.py` | 修改 | 新字段的序列化 / 反序列化 |
| `src/requirement_workflow_v12/design_context.py` | 新建 | `DesignContextBuilder`，类比 `plan_context.py` |
| `src/requirement_workflow_v12/design_intake.py` | 新建 | zip 解压 / MANIFEST 生成 / extract 清理 |
| `src/requirement_workflow_v12/design_syncer.py` | 新建 | `on_enter(READY)` 的 GitHub 原子 commit 同构逻辑 |
| `src/requirement_workflow_v12/coordinator_service.py` | 修改 | `design_start` / `design_submit` / `design_final_approve` / `design_final_reject` 方法；hook 装配 |
| `src/requirement_workflow_v12/service_app.py` | 修改 | 5 个新端点（见 §七）+ 3 个新卡片 handler |
| `src/requirement_workflow_v12/feishu_gateway.py` | 修改 | `create_design_document` / `download_card_attachment` 方法 |
| `tests/` | 新建 | 状态机 / intake / context / syncer 的单元测试 |

---

## 七、端点、事件与卡片清单

### 7.1 HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/queries/openclaw/design-context/<req>` | 给 `design-brief-author` skill 拉上下文 |
| POST | `/openclaw/design-callback` | skill 回写 Brief（单轮） |
| POST | `/cards/design-upload-bundle` | 飞书卡片附件上传（intake 入口） |
| POST | `/cards/design-final-approve` | D-DESIGN-2 "通过" 按钮 |
| POST | `/cards/design-final-reject` | D-DESIGN-2 "打回" 按钮 |

**既有**：

| 方法 | 路径 | 用途 |
|---|---|---|
| CLI | `/design restart <req>` | 级联重置（已实装，不动） |

### 7.2 状态机事件

| 事件 | 触发者 | 目标状态 |
|---|---|---|
| `DESIGN_START` | coordinator（approve_requirement post-hook） | `null → DRAFTING` |
| `DESIGN_SUBMIT` | coordinator（intake 成功） | `DRAFTING → SUBMIT_PENDING_REVIEW` |
| `DESIGN_FINAL_APPROVE` | 终审卡片按钮 | `SUBMIT_PENDING_REVIEW → READY` |
| `DESIGN_FINAL_REJECT` | 终审卡片按钮 | `SUBMIT_PENDING_REVIEW → DRAFTING` |
| `DESIGN_RESTART` | `/design restart` CLI | `任意 → null`（级联） |

### 7.3 Hook 装配

```python
# configure_design_hooks(hooks, services)
hooks.on_enter(DesignStatus.DRAFTING,              _dispatch_design_brief_author)
hooks.on_enter(DesignStatus.SUBMIT_PENDING_REVIEW, _push_final_approval_card)
hooks.on_enter(DesignStatus.READY,                 _commit_design_archive_and_update_registry)
hooks.on_exit(DesignStatus.READY,                  _unlock_plan_precondition)
```

### 7.4 飞书卡片清单

| 卡片 | 触发点 | 按钮 / 字段 |
|---|---|---|
| 设计启动卡 | `on_enter(DRAFTING)` | "打开 Brief" / "前往 Claude Design" / "上传 Handoff" |
| D-DESIGN-2 终审卡 | `on_enter(SUBMIT_PENDING_REVIEW)` | "通过" / "打回"（打回含意见输入） |
| Intake 失败卡 | intake handler 异常时 | "重新上传" / "取消" |
| READY 通知卡 | `on_enter(READY)` | （无按钮；通知类） |

---

## 八、OpenClaw Skill `design-brief-author`

### 8.1 定位

- **单轮 skill**：不跑 IM 对话，不和设计师互动；一次 context query → 一次 callback → 结束
- **产出**：`BRIEF.md` payload（YAML frontmatter + Markdown 正文）
- **参照先例**：`spec-transformer` 是批处理式 skill，但它有 loop 机制；本 skill 比它更简单（真·一次性）

### 8.2 Context payload（coordinator 返回给 skill）

```yaml
req_id: REQ-PROJ-007
project: PROJ

requirement_document_url: https://<feishu>/docs/xxx
requirement_8_fields:
  问题描述: "..."
  使用场景: "..."
  输入: "..."
  输出: "..."
  边界: "..."
  验收标准: "..."
  非功能要求: "..."
  技术范围声明: "..."
needs_ui: true

claude_design_project_url: https://claude.ai/design/projects/xyz
frontend_subpath: "src/{pkg}_webapp"
frontend_tech_stack:
  framework: "React 18 + TypeScript"
  build: "Vite 5.x"
  styling: "Tailwind CSS 3.x"
  component_library: "shadcn/ui"

design_system_snapshot_ref: "design/system/"

current_pages:                                  # design/PAGES.yaml 切片
  - display_name: Dashboard
    last_modified_by_req: REQ-PROJ-003
    target_component: DashboardPage

prior_handoff_archive_ref: design/archive/REQ-PROJ-006_xxx/
prior_handoff_summary: |
  （上一 REQ MANIFEST.bundle_inner_readme_excerpt 的摘录）

design_doc_id: doc-xxx
design_doc_url: https://<feishu>/docs/xxx
```

### 8.3 Skill 契约

- **输入**：上面 context payload
- **输出**：`POST /openclaw/design-callback` body：
  ```json
  {
    "req_id": "REQ-PROJ-007",
    "event": "design_brief_submit",
    "payload": {
      "brief_yaml_frontmatter": "...",
      "brief_markdown_body": "..."
    }
  }
  ```
- **超时**：skill 执行 > 3 分钟 coordinator 侧告警（类似 spec-transformer 超时）
- **幂等**：同 req_id 重复 submit 以最后一次为准（coordinator 更新 `pending_design_brief`）

### 8.4 Skill 的 SKILL.md 放置

- OpenClaw 仓库 `skills/design-brief-author/SKILL.md`
- 可引用本项目 `docs/specs/bitable-agent-readable-fields-v1.2.md`（只读字段契约）
- skill 实现另写一份 skill 实现指引：`docs/specs/openclaw-design-brief-author-skill-impl.md`（本规格不覆盖）

---

## 九、前端技术栈（默认推荐）

**本规格的前端栈是"项目可覆盖的默认值"，不是强制**。

### 9.1 默认栈（`architecture_templates/*.yaml` 写入 `frontend.tech_stack`）

| 维度 | 选型 |
|---|---|
| 构建工具 | Vite 5.x |
| 框架 | React 18 + TypeScript |
| 路由 | react-router 6 |
| 样式 | Tailwind CSS 3.x |
| 组件库 | shadcn/ui（copy-paste，不走 npm） |
| 图标 | lucide-react |
| 字体 | IBM Plex Sans / SC / Mono |
| 状态 | zustand（按需） |
| 请求 | fetch + @tanstack/react-query（按需） |
| 表单 | react-hook-form + zod（按需） |

### 9.2 按 category 的覆盖

| Category | 前端栈 | 前端目录 |
|---|---|---|
| `enterprise-app` | 默认栈 | `src/{pkg}_webapp/` |
| `enterprise-bot` | 默认栈（仅需管理后台时）；否则 `frontend: null` | `src/{pkg}_webapp/` |
| `public-web-site` | 默认栈（需要 SSR 时项目可覆盖为 Next.js 14 App Router） | `src/{pkg}_webapp/` |
| `saas-ai-automation` | 默认栈 | `src/{pkg}_webapp/` |
| `miniprogram` | Taro 4.x + React + TS + NutUI | `src/{pkg}_miniapp/` |

### 9.3 选型理由

1. **不是 Claude Design 强制**。Claude Design 明确说适配任何栈；选默认栈的真正理由是 (2) (3) (4)
2. **生态匹配度最佳**：shadcn/ui + Tailwind + React 在 UI-agent 生态（Claude Code、Cursor、Claude Design）里识别度最高；lucide-react + IBM Plex 是 Claude Design Design System 的自然延续
3. **轻量符合方法论范围**：Vite SPA 部署最简（静态文件），内网工具不吃 SSR 红利
4. **React 生态覆盖最广**：招聘 / 文档 / 示例最多；团队上手成本最低

---

## 十、REQ ID 全链路穿透（Requirement 模型字段扩展）

当前 `Requirement` 已有的 design 相关字段（见 `models.py:115-142`）：

```python
needs_ui: bool = False
hifi_prototype_url: str = ""                      # 保留但语义调整
hifi_prototype_confirmed: bool = False            # 保留但语义调整
design_status: "DesignStatus | None" = None       # 既有
```

**本规格新增**：

```python
design_doc_id: str = ""                           # 飞书 per-REQ design docx ID
design_doc_url: str = ""                          # 飞书文档 URL
design_archive_path: str = ""                     # design/archive/REQ-XXX_<slug>/
design_github_revision: str = ""                  # DESIGN_READY 时写入的 commit SHA
design_precondition_met: bool = False             # PlanStatus 启动守卫字段
pending_design_brief: dict | None = None          # skill callback 后的 Brief 缓存；DESIGN_READY 时清空（已归档）
pending_design_handoff: dict | None = None        # intake 成功后、terminate_approve 之前的临时包信息
```

**既有字段语义调整**：

- `hifi_prototype_url` → 退役，v1 不使用（保留兼容老数据）
- `hifi_prototype_confirmed` → 同上

---

## 十一、完成标准 & 失败回退

### 11.1 DesignStatus == READY 的完成标准

1. `design_archive_path` 非空，指向已 merge 的 GitHub 路径
2. `design/PAGES.yaml` 已更新（本 REQ 涉及的 pages 在 `created_by_req` / `last_modified_by_req` 中可见）
3. `design_precondition_met == True`
4. `design_github_revision` 非空（审计字段）
5. D-DESIGN-2 终审通过（`pending_design_handoff` 清空，MANIFEST 终稿已归档）

### 11.2 失败回退

| 失败点 | 回退行为 |
|---|---|
| Step 1 skill 超时 / 失败 | DesignStatus 保持 DRAFTING；coordinator 推"Brief 生成失败"卡片 → 人可选重试 / restart |
| Step 3 intake 解压失败（zip 损坏） | DesignStatus 保持 DRAFTING；推失败卡请设计师重传 |
| Step 3 intake GitHub 推送失败 | DesignStatus 保持 DRAFTING；`design/archive/REQ-XXX_<slug>/` 本次变更回滚（本地目录删除）；推失败卡 |
| Step 4 `DESIGN_FINAL_REJECT` | 退回 DRAFTING；archive 目录标记 REJECTED；PR 不 merge；设计师被通知 |
| Step 4 `on_enter(READY)` commit 失败 | DesignStatus 保持 SUBMIT_PENDING_REVIEW；推失败卡（重试 / 打回） |
| `/design restart` | 级联 Plan + Spec 重置（已有行为）；archive 目录标记 RESTARTED |

---

## 十二、已知遗留 / 未来演进

- **Anchor hash dedup 未做**：v1 每 REQ archive 独立存嵌套 anchor 目录，存在跨 REQ 冗余（~100KB/anchor）。v2 可引入 `design/anchors/` 全局池 + `index.yaml` 去重
- **File-level diff 未做**：v1 不生成 DIFF.md。v2 若发现下游消费者（plan-author / spec-author）有强需求可追加
- **Drift Truth 未做**：v1 靠"下次 REQ 设计师点 Sync now"自然消解漂移。v2 若实施期出现大量 "bundle ≠ code" 投诉，可引入 `design/DRIFT-TRUTH.md` + Claude Code auto-append 指令
- **Per-page drift strategy（A/B/C）未做**：v1 无分级。v2 观察真实项目运行后按需补
- **Bundle URL fetch 未做**：v1 只支持 zip 附件上传。v2 若 Claude Design 开放无需设计师 session 的 bundle URL 下载，可补一条"卡片填 URL"的入口（附录 C）
- **Claude Design 未实际 link 过 GitHub 仓库时**的 bundle 形态与本规格 §5.5 描述的略有差异（fallback 到 React-via-CDN 简化版）——实施时 intake handler 要容错处理
- **前端脚手架**：当前 `Snowziio/Template-repository` 里没有前端代码；Bootstrap 需要额外步骤从外部 `scaffolds/` 仓库 / npm init 初始化。这是 Bootstrap 层职责

---

## 附录 A：对 Bootstrap 层的前置依赖清单

本层能正常工作必须由 Bootstrap 层保证下列条件（本规格仅列，实施归 Bootstrap 下一轮）：

### A.1 仓库初始化时

- **populate_files 新增**：
  - `design/README.md`（方法论契约说明，见 B.1）
  - `design/PAGES.yaml`（空骨架：`schema_version: "1.0"\npages: []`）
  - `design/INDEX.md`（空骨架：`# Design Handoff Index`）
  - `design/system/.gitkeep`
  - `design/archive/.gitkeep`
- **`.gitattributes` 配置**：
  ```
  design/archive/**/bundle.zip filter=lfs diff=lfs merge=lfs -text
  ```
- **`CLAUDE.md` 增加 "## Design Reference Rules" 节**（见 §4.6 内容）
- **`docs/ARCHITECTURE.md` 增加 "## UI Context" 节**（由 `architecture_templates/*.yaml` 新增 `frontend` + `design` 字段 → `render_template` 自动展开）
- **前端脚手架**：按 category 对应栈（§9.2）scaffold 到 `src/{pkg}_webapp/` 或 `src/{pkg}_miniapp/`

### A.2 `architecture_templates/*.yaml` schema 扩展

每个 category YAML 新增：

```yaml
frontend:
  subpath: "src/{pkg}_webapp"                    # category 可覆盖
  tech_stack:
    framework: "React 18 + TypeScript"
    build: "Vite 5.x"
    routing: "react-router 6"
    styling: "Tailwind CSS 3.x"
    component_library: "shadcn/ui"
    icons: "lucide-react"
    fonts: "IBM Plex (Sans/SC/Mono)"

design:
  claude_design_project_url: ""                  # Bootstrap 运行期填
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
  archive_path: "design/archive/"
```

### A.3 Bootstrap 运行期新增子步骤

- **"Claude Design 绑定"子步骤**：
  1. Bootstrap 卡片提醒"请完成 Claude Design Project 建设 + Import GitHub 仓库 + 搭 DS"
  2. 卡片含"回填 Claude Design Project URL"输入框
  3. 用户填 URL → coordinator 写入 `ProjectConfig.claude_design_project_url`
- **"DS 快照初始同步"子步骤**：
  1. 卡片提醒"请从 Claude Design 导出 DS 并上传到以下入口"
  2. 用户上传 zip → coordinator 解压到 `design/system/`

### A.4 ProjectConfig 字段扩展

```python
@dataclass
class ProjectConfig:
    # 既有字段...
    claude_design_project_url: str = ""
    frontend_subpath: str = ""                   # 从 architecture_templates YAML 派生
    frontend_tech_stack: dict = field(default_factory=dict)   # 同上
```

---

## 附录 B：模版 / 样板文件内容契约

### B.1 `design/README.md`（样板）

```markdown
# Design Artifacts

本目录存放 design 阶段产出的所有制品。产物来自 Claude Design（https://claude.ai/design），
通过 coordinator 的 handoff intake 流程自动入仓。

## 目录结构
- `INDEX.md`   — 所有 REQ 的 handoff 时间线（coordinator 自动维护）
- `PAGES.yaml` — Page Registry（本项目当前有哪些 page）
- `system/`    — 组织级 Design System 快照（Claude Design DS 的副本）
- `archive/`   — 逐 REQ 的 handoff 完整 bundle

## 实施期参考规则
本 REQ 实施时，代码层视觉规范以 `archive/<当前 REQ>/extracted/` 为准。
详见根目录 `CLAUDE.md` 的 "Design Reference Rules" 小节。

## 不在此维护的事项
- 不记录 file-level diff（每 REQ 是自包含快照）
- 不记录 drift 台账（设计师每次在 Claude Design 点 "Sync now" 自然消解）
```

### B.2 `CLAUDE.md` 中 "## Design Reference Rules" 小节

（正文见 §4.6）

### B.3 `docs/ARCHITECTURE.md` 中 "## UI Context" 小节

```markdown
## UI Context

- **前端栈**：{{frontend.tech_stack}}
- **前端代码位置**：{{frontend.subpath}}
- **设计工具**：Claude Design（project URL 见 `project_configs.yaml` → `design.claude_design_project_url`）
- **Page Registry**：`design/PAGES.yaml`
- **Design System 快照**：`design/system/`
```

---

## 附录 C：记录项（已讨论、未来决策）

### C.1 Bootstrap 渲染 vs 模版仓库富化（四种方式对比）

**问题本质**：scaffold 内容（`CLAUDE.md` / `design/` / `SKILL.md` 等）的真相源应在哪里？

| 方式 | 真相源 | 到新项目的路径 |
|---|---|---|
| **α. 当前 Bootstrap 代码渲染** | coordinator 的 `static_content.py` + `architecture_templates/*.yaml` | `populate_files` 在 POPULATE_MAIN 步骤写入新 repo |
| **β. 模版仓库直接富化** | `Snowziio/Template-repository` git 本身 | Bootstrap 只做 create-from-template，内容随克隆自带 |
| **γ. 混合：模版占位符 + Bootstrap 后处理** | 两者共同（模版含骨架 + `{{PLACEHOLDER}}`） | 克隆 + coordinator 做 patch 替换 |
| **δ. 多分支按 category** | 模版仓库多分支（一分支一 category） | Bootstrap 用对应分支做 template source |

| 维度 | α 当前 | β 富化 | γ 混合 | δ 多分支 |
|---|---|---|---|---|
| template 克隆即可看懂全貌 | ❌ | ✅ 最好 | 🟡 中 | ✅ |
| 方法论演进时同步成本 | ✅ 只改代码 | 🟡 改模版 git | 🟡 两处都要 | ❌ N 分支 |
| 项目特定内容注入（项目名/category） | ✅ 自然 | ❌ 不可 | ✅ 占位符替换 | 🟡 粗粒度 |
| scaffold 真相源漂移风险 | ✅ 单点 | ✅ 单点 | ❌ 双源易冲突 | 🟡 多分支维护 |
| 下游独立克隆可用 | ❌（仓库是 stub） | ✅ | ✅ | ✅ |

**长期建议**：向 **γ（混合）** 迁移——template 仓库作为方法论自文档（带占位符的完整骨架）+ coordinator 只做占位符替换和 category 特有补丁。

**本规格不变更现状，保留 α**。

### C.2 模版仓库引导文件方法论富化建议

当前 `Snowziio/Template-repository` 是 minimal stub（README 22 行，无 CLAUDE.md / design/ / docs/）。建议将来补：

- README.md 带项目诞生路径 + 五阶段概览 + `{{PROJECT_NAME}}` 占位
- CLAUDE.md：给 Claude Code 的项目级 AI 行为铁律
- docs/ARCHITECTURE.md 骨架
- design/ 完整骨架
- project/ README 解释 `req-registry.yaml` / `environments.yaml`

本规格不实施；记录待 Bootstrap 层下一轮决策。

### C.3 v2 命令 URL 快捷上传

Claude Design handoff 输出一条可粘贴的命令，含 bundle URL（`https://api.anthropic.com/v1/design/h/<token>`）。v1 走 zip 附件；v2 可增加"卡片填 URL"入口，前提是实测 URL 认证行为允许 coordinator 侧 fetch。

---

## 附录 D：术语对齐

| 术语 | 定义 | 来源 |
|---|---|---|
| **Design Brief** | 进 Claude Design 前的结构化首轮 prompt + expected_pages 清单 | 本规格独创 |
| **Handoff Bundle** | Claude Design Export 产出的 zip | Claude Design 官方 |
| **Page** | UI 层最小可命名单元（非路由 UI 状态如 modal / toast 不单独进 Registry） | 对齐 Claude Design 官方术语（弃用 "screen"） |
| **Anchor Checkpoint** | Claude Design 内部的"保留快照"机制，体现为 bundle 内 `design_handoff_{name}_v{N}/` 子目录 | 本规格基于实证命名 |
| **Display Name** | Page 的稳定标识（主键） | 本规格独创 |
| **Design Artifact** | Design 阶段总产出（飞书 docx + `design/archive/<req>/`）的合集 | 方法论 v3.0 §6.2 已有 |
| **D-DESIGN-2 Final Approval** | 终审人工决策点 | 对齐方法论 D-PLAN-2 命名 |
