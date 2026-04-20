# Project 层 (§5.0) + Bootstrap 流程设计规格

> 本规格定义 harness 方法论的 **§5.0 Project 层**——位于 Requirement / Planning / Spec 之前的**项目生命周期层**。所有 REQ 必须挂靠在一个状态为 `PROVISIONED` 的 Project 上；项目首次创建通过 `/create project` 固化命令触发 Bootstrap 流程，一次性产出 GitHub repo + Feishu ARCHITECTURE doc + Feishu 群 + Bitable 行 + 项目级上下文文件。
>
> 关联文档：
> - 方法论：[harness-engineering-methodology-v2.0.md](../../context/harness-engineering-methodology-v2.0.md) —— 本规格落地后升级到 v2.5
> - Planning 层：[2026-04-19-planning-phase-design.md](./2026-04-19-planning-phase-design.md) —— `architecture_change` → `project_context_change` 统一 gate
> - 仓库工具层：[2026-04-19-project-repo-tools-design.md](./2026-04-19-project-repo-tools-design.md) —— 新增 `bootstrap_project_repo` verb
> - 架构作为 Spec artifact：[2026-04-15-architecture-as-spec-artifact-design.md](./2026-04-15-architecture-as-spec-artifact-design.md)

---

## 零、变更记录

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v1 | 2026-04-20 | 首版：引入 §5.0 Project 层；Bootstrap 7 步流程；`/create project` + `/create req` 固化命令；`project_context_change` 统一 gate；废弃 `_initialize_project_for_first_req` 懒初始化路径；模板仓库精简为纯基础设施骨架 |

---

## 一、目标与使命

### 1.1 核心使命

在 harness 方法论中补上缺失的**项目生命周期层**。让"项目从 0 到 1"成为一次显式、幂等、可审计的 Bootstrap 事件，**而不是**通过首个 REQ 的副作用被动懒初始化。所有后续 REQ 工作（Requirement / Planning / Spec）都**挂靠**在一个已 PROVISIONED 的 Project 上，享用 Bootstrap 阶段准备好的上下文（ARCHITECTURE、environments、SKILL 占位、req-registry、群聊）。

项目级上下文的**后续演化**由 REQ 驱动：plan-author 在 Planning 阶段通过统一的 `project_context_change` 信封提交跨 artifact 变更（MVP 只 `architecture` 真的生效；`environments` / `skill_md` 保留协议位、执行器 stub），走授权闸门后落盘。

### 1.2 四层关系

```
Project  →  Requirement  →  Planning  →  Spec
   │           │              │           │
   └─ §5.0 ────┴─ §5.1 ───────┴─ §5.2 ────┴─ §5.3 ... §5.6
```

- Project 层负责**创建与维护项目级资源**（repo / ARCHITECTURE / environments / 群 / 上下文文件）
- Requirement 层及以下，**假设** Project 已就绪；任何运行时发现 Project 未就绪的路径直接拒绝请求
- Project 级 artifact 的演化路径：REQ → Planning → `project_context_change` → 授权闸门 → section-patch 执行器

### 1.3 非职责（避免越界）

- **不**做 REQ 级资源创建（属于 §5.1 Requirement 层）
- **不**替代 plan-author 的决策能力；Bootstrap 只铺初始占位/骨架，**不**做技术选型
- **不**在 Bootstrap 阶段完善所有细节——MVP 的 environments / skill_md / secrets 只留抽象位
- **不**自动迁移存量项目（`test2` 及之前遗留行**硬切换**废弃，重建 `test3` 跑冒烟）

---

## 二、Project 状态机

### 2.1 状态集

```
UNBOOTSTRAPPED  →  BOOTSTRAPPING  →  PROVISIONED  →  ARCHIVED  →  DECOMMISSIONED
```

| 状态 | 含义 | 可接 REQ? | MVP 实现? |
|---|---|---|---|
| `UNBOOTSTRAPPED` | 逻辑态；实际不持久化（`project_configs` 无行即视为此态）| ❌ | ✅（隐式） |
| `BOOTSTRAPPING` | `/create project` 已触发，Bootstrap 步骤进行中 | ❌ | ✅ |
| `PROVISIONED` | Bootstrap 全部成功完成，项目可挂 REQ | ✅ | ✅ |
| `ARCHIVED` | 冻结；req-registry 只读；拒收新 REQ | ❌ | ❌ Phase 2 |
| `DECOMMISSIONED` | 退役终态；repo 物理删除 + 群解散 + Bitable 行软删 | ❌ | ❌ Phase 2 |

### 2.2 合法转移

```
UNBOOTSTRAPPED  ──/create project──→  BOOTSTRAPPING
BOOTSTRAPPING   ──(all 7 steps OK)──→  PROVISIONED
BOOTSTRAPPING   ──(--resume after failure)──→  BOOTSTRAPPING   (幂等重入)
PROVISIONED     ──/archive project──→  ARCHIVED          (Phase 2)
ARCHIVED        ──/decommission project──→ DECOMMISSIONED  (Phase 2)
```

- BOOTSTRAPPING 超过 24 小时未推进到 PROVISIONED → 群内告警卡（可手工 `/create project --resume <name>`）
- 无"回退"路径（失败 = `--resume` 从断点续跑，不是状态回退）

### 2.3 持久化字段（`project_configs` Bitable 表）

在现有 `ProjectConfig` 基础上**新增**：

```python
@dataclass
class ProjectConfig:
    # 现有字段 ...
    category: str
    template_version: str
    architecture_doc_id: str
    architecture_doc_url: str
    tech_stack: dict[str, str] = field(default_factory=dict)
    design_system_doc_id: str | None = None
    github_repo_url: str = ""
    github_owner_username: str = ""
    bitable_record_id: str = ""

    # 新增字段
    bootstrap_status: str = "UNBOOTSTRAPPED"      # 值域见 §2.1
    bootstrap_log: list[dict] = field(default_factory=list)  # 每步 {step, ts, status, error_msg}
    bootstrap_completed_at: str | None = None
    project_status: str = "UNBOOTSTRAPPED"        # 同状态机；与 bootstrap_status 并行保留以支持 ARCHIVED 等后续态
    feishu_chat_id: str = ""                       # Bootstrap 创建的群 chat_id
```

`bootstrap_status` 与 `project_status` 的分工：
- `bootstrap_status` 仅覆盖 Bootstrap 内部 7 步（值域 `UNBOOTSTRAPPED` / `BOOTSTRAPPING` / `PROVISIONED` / `FAILED`）
- `project_status` 覆盖整个项目生命周期（加上 ARCHIVED / DECOMMISSIONED，Phase 2 启用）

---

## 三、Bootstrap 触发与流程

### 3.1 触发入口：`/create project` 固化命令

**唯一触发路径**：用户在 Feishu IM 中发送命令：

```
/create project <name> --category <c> --owner <uid>
```

参数：
- `<name>`：项目名，校验正则 `^[a-z][a-z0-9-]{2,30}$`，且不与现有 `project_configs` 行重名、不与 `Snowziio` org 现有 repo 重名
- `--category`：`enterprise-app` / `enterprise-bot` / `miniprogram` / `public-web-site` / `saas-ai-automation` 之一
- `--owner`：飞书 `open_id`，自动作为 GitHub collaborator（若该 open_id 已绑定 GitHub 用户名）

授权：**无 gating**（E-Q1/a 决策）——加了 bot 的飞书用户均可触发。Phase 2 可加白名单。

Coordinator 解析命令后返回**固化卡片**：
- 卡片显示 Bootstrap 7 步进度（初始全部 pending）
- Bootstrap 推进时实时更新卡片状态
- 失败时卡片变红 + 显示断点步骤 + `--resume` 提示

### 3.2 Bootstrap 7 步

每步都**幂等**；失败后 `--resume` 从断点重入，跳过已完成步骤。

| 步 | 动作 | 产出 / 状态字段 | 幂等方式 |
|---|---|---|---|
| 1 | 校验输入（name 正则 + uniqueness；category 合法；owner 非空）| —— | 纯检查，无副作用；失败不写任何状态 |
| 2 | Upsert `project_configs` 行，`bootstrap_status=BOOTSTRAPPING` | `project_configs` 行落地 | 按 project 主键 upsert；已有行则更新而非报错 |
| 3 | `create_repo_from_template(Snowziio/Template-repository → Snowziio/{project})` | repo 存在 + `github_repo_url` 回写 | repo 已存在则跳过（通过 `get_repo` 查探）|
| 4 | Populate：一次 commit 到 main，渲染并写入所有 per-project 文件（D-Q1/c 决策，无 PR）。包含 `docs/ARCHITECTURE.md`、`project/README.md`、`project/req-registry.yaml`、`project/environments.yaml`、`project/SECRETS-TODO.md`、`CLAUDE.md`、`SKILL.md` | 所有 per-project 文件落盘 | 按文件 SHA 对比，缺则补、已存在则跳过 |
| 5 | `create_architecture_document()` → Feishu doc + 写入渲染后的 ARCHITECTURE 内容 | `architecture_doc_id/url` 回写 | 若 `architecture_doc_id` 已有则跳过 |
| 6 | 创建 Feishu 群 + 拉入 owner + 拉入机器人 | `feishu_chat_id` 回写 | 若 `feishu_chat_id` 已有则跳过 |
| 7 | `bootstrap_status=PROVISIONED` + 群内欢迎卡 + 进度卡更新为"全部绿" | 状态机终态 | —— |

每步执行后 append 一条 `bootstrap_log` 条目：`{step: <1-7>, ts: "...", status: "ok"/"error", error_msg: null/"..."}`。

说明：`SECRETS-TODO.md` 已折叠到 Step 4 的单次 populate commit 内，避免多次小 commit 噪声。

### 3.3 失败处理与重入

- 任一步失败 → `bootstrap_status=BOOTSTRAPPING`（不推进）；`bootstrap_log` 记录错误；卡片显示断点
- 24 小时无进展 → 自动群告警
- `/create project --resume <name>` → 从 `bootstrap_log` 的最后成功步+1 开始重跑；每步入口先做幂等检查

### 3.4 GitHub Generate API 机制

Bootstrap Step 3 使用 GitHub 原生 Template Generate：

```python
# Layer 4 primitive (existing: github_gateway.py:82-104)
POST /repos/Snowziio/Template-repository/generate
{
  "owner": "Snowziio",
  "name": "<project>",
  "private": true,
  "include_all_branches": false
}
```

- 新 repo 有独立 git history（非 fork；无 upstream 关系）
- 首次 commit 作者为 Bot（token 对应 GitHub 用户）
- Template 仓库必须在 GitHub 设置中勾选 "Template repository" 开关
- Generate API **不支持生成时改文件**——Step 4 必须在独立 commit 中覆盖/新增

---

## 四、Template 仓库结构（最小骨架）

**设计原则**：Template 仓库 = **纯基础设施骨架**（与 category / project 无关）；所有 per-project / per-category 内容由 Bootstrap Step 3-6 渲染。

### 4.1 Template-repository 内容

```
Snowziio/Template-repository/
├── README.md                  # "这是模板仓库，由 Bootstrap 使用" + 链接到方法论
├── LICENSE                    # 统一 license（可选；MVP 可略）
├── .gitignore                 # 多语言宽泛 ignore（py + node + go + 常见 IDE）
└── .github/
    └── workflows/
        └── ci.yml             # 通用占位 CI（lint 步骤 + 空 test job）
```

注意：连 `docs/` 和 `project/` 文件夹都**不在** template 里——Bootstrap Step 3 populate 阶段一次性创建。

### 4.2 Bootstrap Populate 阶段写入的文件（Step 4 一次 commit 到 main）

| 路径 | 内容来源 | 说明 |
|---|---|---|
| `docs/ARCHITECTURE.md` | `architecture_templates.render_template(category, project)` | category 专属渲染，同步写 Feishu doc（Step 4）|
| `project/README.md` | Python 静态常量 | req-registry 格式说明 for human+AI，所有项目一致 |
| `project/req-registry.yaml` | 初始化为 `{project: <name>, requirements: []}` | 每个 REQ 创建时 service 自动 append 一行 |
| `project/environments.yaml` | category 默认骨架（stub + 注释）| MVP 只留占位；演化通道 stub |
| `project/SECRETS-TODO.md` | category 默认清单 | 给人看的提示文件，不自动填 |
| `CLAUDE.md` | 通用占位 + `{project}/{pkg}/{date}` 替换 | 给 Claude Code session 使用 |
| `SKILL.md` | 通用占位 + 同上 | 给 Claude Agent SDK / OpenClaw 使用 |

commit message：`project bootstrap: populate initial project-level files`

### 4.3 req-registry.yaml 格式（human+AI 可读）

```yaml
# project/req-registry.yaml
#
# 本文件是项目级 REQ 索引。写入方：coordinator service（非 plan-author）。
# 更新时机：每次 REQ 状态变迁时 append / update 对应行。
# 所有 REQ 必须在 Bootstrap 完成后通过 /create req 命令创建，自动挂入此表。
#
# Schema:
#   project:      项目名（与 project_configs.project 一致）
#   requirements: REQ 条目数组，每条 record 字段如下
#     req_id:      REQ-YYYY-MM-DD-NNN
#     title:       REQ 名称
#     status:      DRAFTING | APPROVED | PLANNING | SPEC_DRAFTING | MERGED | ABANDONED
#     plan_id:     null（未进入 planning）或 PLAN-YYYY-MM-DD-NNN
#     spec_pr:     null 或 PR number (#123)
#     created_at:  ISO 时间戳

project: <name>
requirements: []
```

---

## 五、REQ 创建流程硬切换

### 5.1 `/create req` 固化命令

**唯一触发路径**（F-Q2/a 决策）：

```
/create req <project> <name>
```

可选参数：
- `--summary "..."`：一行摘要
- `--category <c>`：校验时必须与 `project_configs.<project>.category` 一致，不一致直接拒（防止挂错项目）

### 5.2 自由文本入口**下线**

- 当前 `create_requirement_from_group` 仍读取 `CreationRequest`；保留此签名作为下层，但**入口解析器**只识别 `/create req ...` 固化命令
- 非命令消息 → 固化提示卡：「REQ 创建已改用 `/create req <project> <name>`，请重新发送」
- 不保留兼容窗口（硬切换）

### 5.3 前置校验

Service 层在 `create_requirement_from_group` 入口处新增校验链：

1. `project_configs.<project>` 存在？否则拒
2. `project_configs.<project>.bootstrap_status == PROVISIONED`？否则拒（含提示"项目 Bootstrap 尚未完成，当前状态 BOOTSTRAPPING"）
3. 若命令带 `--category`，与 `project_configs.<project>.category` 一致？否则拒

### 5.4 废除 `_initialize_project_for_first_req`

`service_app.py:319-345` 的 `_initialize_project_for_first_req` **完全删除**。原本在首 REQ 时做的三件事已全部上提到 Bootstrap：
- 渲染 ARCHITECTURE 模板 + 写 Feishu doc → Bootstrap Step 4/5
- 写 `project_configs` 行 → Bootstrap Step 2
- 填充 `architecture_doc_id/url` / `template_version` / `tech_stack` → Bootstrap Step 2/5

对应 `_provision_requirement_after_creation` 简化为只做 REQ 级工作：绑定文档 / 绑定 Bitable 行 / 发 IM 卡片 / append `project/req-registry.yaml` 一行。

### 5.5 req-registry 自动 append

REQ 创建成功后，service 直接对 GitHub repo 的 `project/req-registry.yaml` 做**非 gate** append：

- 走 Layer 4 primitive：`fetch_file_sha` → 构造新内容 → `commit_files`
- commit message：`req-registry: append <req_id>`
- 失败 → 记告警 log 但**不**阻塞 REQ 创建返回（属于索引维护，非状态机关键路径）

---

## 六、统一 `project_context_change` gate

### 6.1 从 `architecture_change` 泛化

当前 Planning 层的 `architecture_change` 只处理 ARCHITECTURE 单一 artifact。本次设计将其**统一泛化**为 `project_context_change`：

```json
{
  "req_id": "REQ-...",
  "event": "plan_submit",
  "payload": {
    "plan_md_content": "...",
    "project_context_change": {
      "summary": "高层描述本次项目级变更",
      "authorized": false,
      "changes": [
        {
          "artifact": "architecture" | "environments" | "skill_md",
          "section_path": "...",
          "before": "...",
          "after": "...",
          "rationale": "Dn"
        }
      ]
    }
  }
}
```

### 6.2 分派策略（D-Q2/b 决策）

Coordinator 在 `apply_project_context_changes` 执行器中按 `artifact` 字段分派：

| `artifact` 值 | 执行器 | MVP 实现？ |
|---|---|---|
| `architecture` | 复用现有 `apply_architecture_changes`（Feishu doc section-patch）| ✅ |
| `environments` | Stub：记录 warning log + 拒绝写入 + 在 commit message 里留痕 | ⚠️ 协议位；执行器 stub |
| `skill_md` | 同上 Stub | ⚠️ 协议位；执行器 stub |

`section_path` 语义由各 artifact 执行器自解释（no 统一 URI 语法）。

### 6.3 授权模型（X-b 统一 gate）

- 批 = 全批：所有 `changes[]` 原子生效
- 拒 = 全拒：整个 plan_submit 打回 DRAFTING
- 不支持"部分批准"（YAGNI）

### 6.4 无 legacy 兼容负担

F-Q1/c 决策硬废弃 `test2`，重建 `test3`——**没有**既存 `architecture_change` 记录需要兼容。plan-author 直接切换到 `project_context_change`，`architecture_change` 字段完全移除（代码 + schema）。

---

## 七、治理与运营

| # | 条目 | 方案 |
|---|---|---|
| E1 | Bootstrap 审计 | `project_configs.bootstrap_log` JSON 列记录每步时间戳 / 状态 / error_msg；`--resume` 读此列续跑 |
| E2 | 失败告警 | `bootstrap_status=BOOTSTRAPPING` 超过 24 小时 → 群内发告警卡；不自动回退 |
| E3 | 并发写保护 | `project_configs` 按 project name 行锁（乐观：`bitable_record_id + version` 字段）|
| E4 | REQ 前置校验 | Service 检查 `bootstrap_status=PROVISIONED`，非终态直接拒 |
| E5 | 归档只读 | ARCHIVED 项目的 req-registry 冻结；可读不可 append；MVP 不实现 |
| E6 | 模板版本化 | `template_version` 字段记录 Bootstrap 时 template repo commit SHA；模板升级不回溯已建项目 |
| E7 | Bot 入群 | Bootstrap Step 5 创建群后自动拉 bot |
| E8 | 观测口径 | Bootstrap 事件走 `project_bootstrap_event` 子通道（与 REQ callback 并列）|
| E-Q1 | `/create project` 授权 | 无 gating；bot 加入即授权（MVP）|
| E-Q2 | 项目名规则 | `^[a-z][a-z0-9-]{2,30}$` + uniqueness；不禁用保留词 |
| E-Q3 | GitHub 初始权限 | 自动把 owner 加为 collaborator（write）；无团队继承 |

---

## 八、MVP 范围

### 8.1 IN（本 spec 对应的实现计划覆盖）

- Bootstrap 7 步全流程
- 统一 `project_context_change` schema
  - `architecture` 执行器（复用现有逻辑）
  - `environments` / `skill_md` 执行器 stub（记录 + 拒写）
- `/create project` 固化命令 + 固化卡片（含进度 + resume 提示）
- `/create req` 固化命令（替换自由文本入口）
- Service 前置校验 `PROVISIONED`
- req-registry.yaml 自动 append（非 gate）
- 废除 `_initialize_project_for_first_req`
- `ProjectConfig` 字段扩展
- Template 仓库精简到最小骨架
- **test2 硬切换废弃**，重建 `test3` 跑 Phase 1 冒烟

### 8.2 OUT（只留抽象位或 Phase 2）

- `environments.yaml` 演化执行器实际生效（MVP 只 stub）
- `skill_md` 演化执行器实际生效（MVP 只 stub）
- `design-system.md` 生成与演化（随 needs_ui 整体延后）
- `/archive project` / `/decommission project` 命令（Phase 2）
- 白名单 / owner 授权链（Phase 2）
- SECRETS 自动填充（MVP 只生成 TODO 清单）
- 存量项目迁移脚本（F-Q1/c 硬废弃）
- 归档状态的 req-registry 只读保护（Phase 2）

---

## 九、代码落位

### 9.1 新增模块 `project_bootstrap/`（Layer 2 orchestrator）

```
src/requirement_workflow_v12/project_bootstrap/
├── __init__.py
├── service.py                 # ProjectBootstrapService（编排 7 步）
├── state.py                   # bootstrap_status 机 + resume 逻辑
├── templates/                 # category 相关骨架（environments / skill_md 占位）
│   ├── environments_defaults.py
│   ├── skill_md_template.py
│   └── secrets_checklist.py
└── types.py                   # BootstrapResult / BootstrapStep dataclasses
```

### 9.2 修改现有模块

| 文件 | 变更 |
|---|---|
| `project_repo/tools.py` | Protocol 新增 verb：`bootstrap_project_repo(project, category, ...)` → `BootstrapResult` |
| `project_repo/github_impl.py` | 实现 `bootstrap_project_repo`（调用 Layer 4 primitives：`create_repo_from_template` / `commit_files`）|
| `project_repo/types.py` | `RepoRef` 启用（已 reserved）；新增 `BootstrapResult`（含 repo / doc_id / chat_id / log）|
| `project_config.py` | 新增字段见 §2.3 |
| `service_app.py` | 删除 `_initialize_project_for_first_req`；`_provision_requirement_after_creation` 精简；新增 `/create project` / `/create req` 解析入口 |
| `coordinator_service.py` | 前置校验 `PROVISIONED`；`create_requirement_from_group` 入口仅接受结构化 `CreationRequest`（命令解析产出）|
| `protocols.py` | `CreationRequest` 新增 `category` 可选字段用于 cross-check |

### 9.3 Agent / 方法论文档

| 文件 | 变更 |
|---|---|
| `docs/superpowers/methodology.md`（v2.0 → v2.5）| 插入 §5.0 Project 层 |
| `docs/superpowers/planning-harness-layer.md` | 前置依赖段；`architecture_change` → `project_context_change` 泛化说明 |
| `docs/superpowers/specs/2026-04-19-planning-phase-design.md` | addendum：schema 升级到 `project_context_change` |
| `docs/agents/plan-author/SKILL.md` | Step 3 判定逻辑更新；组装统一 payload |
| `docs/agents/plan-author/callback-schema.json` | schema 升级；artifact 字段引入 |
| `docs/agents/project-bootstrap/SKILL.md`（新增）| Bootstrap 的 agent 化占位（MVP 由 CLI 驱动，Phase 2 agent 化扩展位）|

---

## 十、测试计划

### 10.1 单元

- `project_bootstrap.service` 每步幂等测试（跑两次结果一致）
- `--resume` 从各个断点续跑的正确性
- `ProjectConfig.bootstrap_log` append 正确性
- `/create project` 命令解析 + 参数校验错误路径
- `/create req` 命令解析 + `category` 一致性校验
- `project_context_change` 分派器：`architecture` 路径通、`environments`/`skill_md` stub 返回预期警告

### 10.2 集成

- 端到端：`/create project` 建起 test3 全链路（实际打 GitHub / Feishu / Bitable）
- 失败注入：模拟 GitHub API 429 在 Step 2；验证 `--resume` 能续
- REQ 前置拒绝：`BOOTSTRAPPING` 状态下发 `/create req` 返回拒绝卡
- 自由文本发 REQ 请求 → 返回"请使用 `/create req`"提示卡
- req-registry 自动 append 失败不阻塞 REQ 创建

### 10.3 冒烟

Phase 1 `test3` 新建冒烟跑通的判定条件：
- `/create project test3 --category saas-ai-automation --owner <open_id>` 后 PROVISIONED
- GitHub `Snowziio/test3` 存在 + 包含 Bootstrap populated 文件
- Feishu ARCHITECTURE doc 可访问
- Feishu 群存在且 bot + owner 均在
- 发 `/create req test3 "first requirement"` → REQ 成功创建 + req-registry.yaml 多一行
- 整条需求 → planning → spec 链路无"项目未初始化"错误

---

## 十一、风险与权衡

### 11.1 已知风险

**R1 - Template 仓库 Generate API 的"template 开关"**  
必须在 `Snowziio/Template-repository` 的 GitHub Settings 里显式勾选 "Template repository"，否则 `create_repo_from_template` 返回 404。  
**缓解**：Bootstrap Step 0 启动前做一次 `get_repo` 探测响应中的 `is_template` 字段；若未开启，卡片报错 + 人工去 GitHub 开关。

**R2 - Feishu 群创建 API 配额**  
批量 Bootstrap（未来 Phase 2 可能有）可能触发飞书群创建 API rate limit。  
**缓解**：MVP 单次手动触发，不担心；Phase 2 加 rate limit 兼容层。

**R3 - architecture_doc_url 仍是飞书长链接**（遗留风险）  
容器重启后 Feishu OAuth token 可能失效，doc_url 失效不影响数据（doc_id 持久），但 URL 格式变化可能导致卡片链接失效。  
**缓解**：沿用现有处置——Spec 测试完成后再解决（见 memory `project_architecture_url_persistence_risk.md`）。

**R4 - req-registry 写冲突**  
多个 REQ 在极短时间内创建可能导致 race。  
**缓解**：Layer 4 `commit_files` 基于 `fetch_file_sha` 的 CAS 语义；失败重试最多 3 次；仍失败只告警不阻塞。

### 11.2 刻意偏离直觉的决策

**D1 - 统一 gate 而非分拆 gate**（X.1/b 选择 X-b）  
直觉：每 artifact 一个独立 gate 粒度更细。实际：MVP 只有 `architecture` 真的生效，其它是占位；统一信封扩字段比加端点便宜；单一 REQ 同时改多 artifact 时原子语义更清晰。

**D2 - 废弃存量项目而非补齐 Bootstrap**（F-Q1/c）  
直觉：应该写迁移脚本让 test2 继续用。实际：MVP 阶段存量项目价值低；硬废弃更干净；未来真正的生产项目再谈迁移。

**D3 - 自由文本 REQ 入口硬下线无兼容窗**（F-Q2/a）  
直觉：留一个降级窗口更温和。实际：自由文本没法安全推断 `project` 挂载目标；一旦 Bootstrap 引入硬性前置，保留自由文本会在项目归属推断上出现灰区。

**D4 - Template 仓库精简到极简**（G/a）  
直觉：在 template 里放多占位文件便于浏览。实际：占位文件会被 Bootstrap 覆盖，template 里的等于"短命 noise"；所有 per-project / per-category 内容集中在 Python 模板更易维护。

**D5 - Bootstrap Step 3 直接 commit main 不走 PR**（D-Q1/c）  
直觉：所有 commit 都该走 PR。实际：Bootstrap 阶段项目还没别的 commit，PR 没有 reviewer / 没有对比价值，徒增步骤。首 REQ 起再开始 PR 流程。

---

## 十二、上线节奏

1. **本 spec 批准** → writing-plans 产出实施计划
2. **实施**：按 writing-plans 产出的任务顺序落地
3. **集成测试**：`test3` 端到端冒烟通过
4. **Phase 1 解锁**：原 Phase 1 Task 11（GitHub repo 冒烟）由 `test3` 的 Bootstrap 流程代偿完成
5. **方法论升级**：methodology.md v2.0 → v2.5 发布
6. **记忆更新**：已有的 `project_pending_state_migration` 等相关 memory 项更新状态

---

## 十三、Open Questions（留给 writing-plans 阶段细化）

1. Bootstrap Step 5 创建飞书群时，`owner` 参数若 open_id 未在飞书通讯录 → 返回什么错误？是否阻塞 Bootstrap？（建议：不阻塞，群先建出来，后续 owner 自加）
2. `category` 新增项的扩展路径（未来新增"IoT device"类别）——当前 5 个硬编码，是否需要一个 registry pattern？（倾向：Phase 2 再说）
3. `project/environments.yaml` 的 category 默认骨架具体内容——需要在 writing-plans 阶段逐 category 敲定
4. Bootstrap 卡片 UI 细节（进度条 / 断点展示 / resume 按钮）——writing-plans 阶段和 Feishu card schema 结合细化
