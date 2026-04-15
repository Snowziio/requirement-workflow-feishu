# ARCHITECTURE.yaml 作为 Spec 层产出的重新定位设计

**日期**：2026-04-15
**范围**：推翻 2026-04-15 P0-1（spec-context 端点 + GitHub 注入）的假设前提，重新定位 ARCHITECTURE.yaml 为 Spec 层的项目级产出物。同步拆除 onboarding / Bootstrapper / GitHub 绑定。
**前置阅读**：
- `docs/context/infra/context-chain-principle.md`
- `docs/context/harness-engineering-methodology-v2.0.md`
- `docs/superpowers/specs/2026-04-15-spec-context-endpoint-design.md`（本方案部分推翻）

---

## 1. 问题陈述

当前实现（P0-1 已交付）将 ARCHITECTURE.yaml 视为 Spec 层的**输入**：在项目 bootstrap 时创建空 YAML 推到 GitHub 仓库，Spec 撰写时从 GitHub 实时拉回注入 agent。这依赖两个前置假设：

1. 项目已有 GitHub 仓库可推
2. bootstrap 阶段能产出有意义的 YAML 初版

两个假设都站不住：
- 当前项目的产出边界只到 Spec 文档，不触及 Impl；GitHub 仓库可能根本不存在
- bootstrap 时尚无任何需求已沉淀，YAML 只是个空骨架，Spec 层拿到这份空骨架做架构决策毫无价值

**正确定位**：ARCHITECTURE.yaml 是 Spec 层的**产出物**之一，随项目每条 REQ 的 Spec 迭代而演化。它是项目级持久文档，不绑定任何单一 REQ 生命周期。

---

## 2. 目标

- 把 ARCHITECTURE.yaml 从"前置基础设施"重新定位成"Spec 层核心产出之一"
- 拆除 GitHub 绑定 / Bootstrapper / Onboarding 对话流程（它们都是错误假设的延伸）
- 定义 ARCHITECTURE 飞书文档的生命周期（per-project，跨 REQ 演化）
- 把类目模板从"bootstrap 产物"重新定位成"Spec 撰写骨架"
- 保留 spec-context 端点 + context_token 握手，重构 payload 语义

---

## 3. 非目标

- **不做** GitHub 绑定 / 仓库创建 / PR 生成。当前项目完全运行在飞书侧
- **不做** 跨项目 ARCHITECTURE 关联（继承、复用模块引用等）
- **不做** Spec 描述的新模块到实现代码的一致性校验（意图 vs 事实的对账留给 Phase 2）
- **不做** ARCHITECTURE 与实现 PR 的事件联动（checkpoint-handler 是 Phase 2 命题）
- **不做** 多项目 ARCHITECTURE 统计、类目看板等观测能力

---

## 4. 上下文契约变化

### 4.1 Spec 层契约（按 context-chain-principle §二）

```markdown
## 项目级上下文契约（Spec 层，新）

### 消费（来自上层）
| 上下文产物 | 来源 | 读取机制 |
|-----------|------|---------|
| 需求文档 8 字段 | 飞书需求文档 | feishu_fetch_doc(requirement_document_url) |
| latest_review_summary | Coordinator state | spec-context 端点 |
| **类目模板骨架** | Coordinator 内置模板 | spec-context 端点（文本字段） |
| **当前项目 ARCHITECTURE 状态** | 飞书项目级文档 | feishu_fetch_doc(architecture_doc_url) |
| 设计系统快照 | （needs_ui=true 时） | Phase 2 |

### 产出（传递给下层）
| 上下文产物 | 内容 | 存储位置 | 更新策略 |
|-----------|------|---------|---------|
| Spec 文档 | 9 节技术规格 | 飞书 Spec 文档 | 每节覆盖写 |
| **ARCHITECTURE 演化版本** | 本轮增量合并后的全量 YAML | **同一份项目级飞书文档** | **覆盖写**（保留飞书原生版本历史） |
| spec_review_summary | 审查结论 | Coordinator state | spec-review pass 时写入 |
```

### 4.2 ARCHITECTURE 生命周期（新增跨层契约）

- **诞生**：项目首条 REQ 的创建表单提交时（非 bootstrap），Coordinator 以类目模板为骨架创建项目级飞书文档
- **演化**：项目每条 REQ 的 Spec 阶段，spec-author 读当前 YAML → 决策增量 → 写回更新版
- **消费**：本项目只有 Spec 层消费。未来 Harness/Impl 层消费留给 Phase 2
- **冻结**：无。ARCHITECTURE 永远随项目演进

---

## 5. 数据模型变化

### 5.1 `ProjectConfig` 字段增删

```python
@dataclass
class ProjectConfig:
    # 删除（GitHub 绑定的延伸）
    # github_repo_url: str
    # is_new_project: bool
    # architecture_yaml_initialized: bool
    # acm_registry_initialized: bool
    # onboarding_state: OnboardingState

    # 新增
    category: str                  # e.g. "saas-ai-automation"
    template_version: str          # e.g. "saas-ai-automation.v1"
    architecture_doc_id: str       # 飞书 document_id
    architecture_doc_url: str      # 飞书文档 URL

    # 保留
    tech_stack: dict[str, str]
    design_system_doc_id: str      # UI 快照未来挂点
```

### 5.2 `Requirement` 字段增删

```python
@dataclass
class Requirement:
    # 删除（GitHub 绑定的延伸）
    # github_repo_url: str
    # spec_context_snapshot_sha: str

    # 重命名 & 新语义
    spec_context_snapshot_revision: str  # 飞书文档 revision，spec_submit 时回证用

    # 保留
    active_spec_context_token: str
    ...
```

### 5.3 `OnboardingState` 枚举

**整个枚举 + `onboarding_state` 字段删除**。`ProjectConfig` 的存在性本身替代"是否完成初始化"语义：首条 REQ 创建时自动生成 ProjectConfig，此后即视为已初始化。

---

## 6. 类目模板

### 6.1 存放位置

`docs/context/architecture-templates/{category}.v{N}.yaml`，版本化文件名。模板更新走 PR；新 bootstrap 的项目读最新版，已有项目的飞书文档不回溯。

### 6.2 类目清单

| category | 模板文件 | 定位 |
|---------|---------|------|
| `public-web-site` | `public-web-site.v1.yaml` | 面向 C 端 Web |
| `miniprogram` | `miniprogram.v1.yaml` | 小程序 |
| `enterprise-bot` | `enterprise-bot.v1.yaml` | IM 驱动的企业内 Bot/Agent |
| `enterprise-app` | `enterprise-app.v1.yaml` | 企业内部管理应用 |
| `saas-ai-automation` | `saas-ai-automation.v1.yaml` | SaaS 对接 + AI 增强/自动化 |

### 6.3 模板内容

沿用之前讨论的粒度 b（tech_stack + 空模块骨架）。每个模板：
- 顶部注释 `# Generated from template: {category}.v{N}`
- `version: "{date}"` / `project: {project}` / `status: bootstrap`
- `tech_stack` 含类目典型默认值
- `modules` 含 3-5 个空骨架（name / description / repo_path / 空 public_api / status: bootstrap）
- `services: []` / `data_models: []` / `external_dependencies: [...]`

### 6.4 占位符

模板中唯一开放给用户的占位符是 `{pkg}`。渲染时：
- 用户填入的 project 名 → 小写化 → 非字母数字转下划线 → 作为 `pkg` 值
- 例：project `MyApp` → `pkg = my_app`
- 模板中出现的 `src/{pkg}/coordinator` 渲染为 `src/my_app/coordinator`

`{project}` 和 `{date}` 为 Bootstrapper 内部替换，不作为用户配置点。

---

## 7. 创建需求表单字段变化

现有表单字段：`project` / `name` / `summary` / `needs_ui`（复选）

**新增**：

| 字段 | 类型 | 可见性 |
|------|------|--------|
| `category` | 下拉 5 选 1 | **仅项目首条 REQ 时显示**。后续 REQ（project 已有 ProjectConfig）隐藏 |

**表单渲染逻辑**：
- `_build_requirement_creation_card(context)` 检查 project 是否在 `project_configs`
- 若不在 → 卡片包含类目下拉
- 若已在 → 卡片不含类目下拉

**提交处理**：
- 如果是首条 REQ，`submit_create_requirement` 分支读取 category 字段，创建 ProjectConfig 并以模板初始化飞书 ARCHITECTURE 文档
- 如果是后续 REQ，复用已有 ProjectConfig

---

## 8. 工作流

### 8.1 首条 REQ（含项目初始化）

```
用户在创建群发「创建需求 MyProj ...」
  ↓ 无匹配 ProjectConfig
Coordinator 返回含类目下拉的创建卡片
  ↓ 用户填完提交（含 category=saas-ai-automation）
Coordinator：
  1. 创建 Requirement（CREATED）
  2. 在 _provision_requirement_after_creation 线程中：
     a) 读模板 docs/context/architecture-templates/saas-ai-automation.v1.yaml
     b) 渲染占位符得到初始 YAML 文本
     c) feishu_create_doc 创建项目级 ARCHITECTURE 文档
     d) feishu_update_doc 写入初始 YAML 内容
     e) 构造 ProjectConfig{category, template_version, architecture_doc_id, architecture_doc_url, tech_stack}
     f) 创建需求飞书文档（已有逻辑）
     g) 创建 Bitable 记录（已有逻辑）
     h) 创建项目群（已有逻辑）
     i) 状态推进到 DRAFTING
```

### 8.2 后续 REQ

```
用户在创建群发「创建需求 MyProj ...」
  ↓ project 已在 project_configs
Coordinator 返回普通创建卡片（不含类目下拉）
  ↓ 用户提交
Coordinator：
  1. 创建 Requirement
  2. 复用 ProjectConfig.architecture_doc_url
  3. 其他照旧
```

### 8.3 Spec 撰写（消费 + 演化）

```
spec-author 启动，调 POST /queries/openclaw/spec-context {req_id}
  ↓
Coordinator：
  - 状态门禁：status ∈ {APPROVED, SPEC_DRAFTING}
  - 并发门禁：检查项目下是否有其他 REQ 处于 SPEC_DRAFTING（不含本 REQ）
     有 → 返 409 `concurrent_spec_in_progress`
  - 读 architecture_doc_url / architecture_doc_revision（当前版本标识）
  - 生成 context_token，写入 Requirement.active_spec_context_token
  - 返回 payload（见 §9）
  ↓
spec-author：
  1. feishu_fetch_doc(requirement_document_url) 读需求 8 字段
  2. feishu_fetch_doc(architecture_doc_url) 读当前 ARCHITECTURE 状态
  3. 撰写 Spec 9 节，§8 引用（不复制）ARCHITECTURE 原文作为背景
  4. 识别本次 REQ 带来的架构增量
  5. 在本地合并：当前 YAML + 增量 → 新版 YAML
  6. feishu_update_doc(architecture_doc_url, 新版 YAML) 覆盖写回
  7. POST /callbacks/openclaw/spec-turn {
       req_id, event: spec_submit,
       context_token, architecture_doc_revision (写后新 revision),
       summary, spec_document_url
     }
  ↓
Coordinator：
  - 验 token
  - 记录 Requirement.spec_context_snapshot_revision
  - 清空 active_spec_context_token
  - 状态保持 SPEC_DRAFTING（等待 spec-reviewer 后续推进到 SPEC_LOCKED）
```

### 8.4 并发控制（方案 C）

**同一项目下，不允许两条 REQ 同时处于 SPEC_DRAFTING**。

- 入口：`spec-context` 端点 + `spec_start` 回调两处都做并发检查
- 检查逻辑：遍历 `self.requirements.values()`，找到 `project == requirement.project` 且 `status == SPEC_DRAFTING` 且 `req_id != current_req_id` 的任何记录
- 有 → 返 409 `concurrent_spec_in_progress`，消息指引用户等待其他 Spec 锁定后再启动
- 后续可以升级到方案 B（乐观并发 + revision 冲突合并），现在不做

**边界**：
- 人工可以同时创建多条 REQ（需求层允许并发）
- 但 APPROVED 后只能一条一条走 Spec
- 若项目一次有多条需求同步推进，管理员需人工排序

---

## 9. spec-context 端点 payload 变化

### 9.1 新 payload 结构

```json
{
  "ok": true,
  "context": {
    "req_id": "REQ-xxx",
    "name": "...",
    "project": "MyProj",
    "category": "saas-ai-automation",
    "status": "APPROVED",
    "needs_ui": false,
    "hifi_prototype_url": "",
    "design_system_snapshot": null,

    "requirement_document_url": "https://feishu.../doc1",
    "architecture_doc_url": "https://feishu.../doc2",
    "architecture_doc_revision": "rev-20260415-001",
    "template_version": "saas-ai-automation.v1",

    "spec_document_url": "",
    "spec_document_id": "",

    "latest_review_summary": "..."
  },
  "context_token": "spec_ctx_REQ-xxx_..._xxxx",
  "expires_hint": "..."
}
```

### 9.2 拆除的字段（与 2026-04-15-spec-context-endpoint-design.md 比）

- `architecture_yaml`（YAML 原文不再由端点返回；agent 自行 feishu_fetch_doc）
- `architecture_commit_sha`（GitHub 概念，换 `architecture_doc_revision`）
- `github_repo_url`（整个 GitHub 绑定删除）

### 9.3 spec-turn callback 字段变化

- 原 `architecture_commit_sha` 参数 → 改为 `architecture_doc_revision`
- 语义：spec_submit 时回传**写入后的** revision，Coordinator 记录为审计字段

---

## 10. 错误码映射

### 10.1 spec-context 查询

| 场景 | HTTP | error |
|------|------|-------|
| HMAC 失败 | 401 | `unauthorized` |
| payload 非法 | 400 | `invalid_payload` |
| 需求不存在 | 404 | `not_found` |
| 状态门禁失败 | 409 | `invalid_state` |
| **同项目有并发 Spec** | **409** | **`concurrent_spec_in_progress`** |
| ProjectConfig 缺失 | 500 | `project_not_initialized` |
| 飞书文档不可访问 | 502 | `architecture_doc_unreachable` |

### 10.2 spec-turn callback

| 场景 | HTTP | error |
|------|------|-------|
| 缺 context_token | 400 | `missing_context_token` |
| token 不匹配 | 409 | `stale_context_token` |
| spec_submit 缺 architecture_doc_revision | 400 | `missing_doc_revision` |

---

## 11. 拆除清单

### 11.1 删除文件

- `src/requirement_workflow_v12/github_client.py`
- `src/requirement_workflow_v12/project_bootstrapper.py`
- `scripts/bootstrap_architecture.py`
- `tests/test_github_client.py`

### 11.2 删除代码

- `service_app.py` 中的 `_onboarding_collect_repo` / `_onboarding_collect_project_type` / `_onboarding_collect_tech_stack` / `_onboarding_wait_arch_confirmation` / `_run_bootstrap_new_project` / `_run_bootstrap_existing_project` / `_finish_onboarding` / `_make_bootstrapper`
- `handle_text_message` → `_handle_creation_group_message` 里对 `is_new_project` 的分支走 onboarding 的部分
- `_pending_onboarding_project` 字段
- `CoordinatorService.register_project_config` / `set_project_type` / `set_tech_stack`（功能合并到新的 `initialize_project`）
- `OnboardingState` 枚举

### 11.3 重构代码

- `SpecContextBuilder.build`：删除 `GitHubClient` 调用，payload 改为 §9.1
- `handle_openclaw_spec_turn_callback`：字段名从 `architecture_commit_sha` 改为 `architecture_doc_revision`
- 创建需求表单（`_build_requirement_creation_card`）：按 project 是否已有 ProjectConfig 决定是否显示类目下拉
- `submit_create_requirement` 动作处理：首条 REQ 分支触发项目级 ARCHITECTURE 文档创建
- `scripts/send_openclaw_callback.py`：`--architecture-commit-sha` 改为 `--architecture-doc-revision`

### 11.4 新增代码

- `src/requirement_workflow_v12/architecture_templates.py`：加载 `docs/context/architecture-templates/` 目录下最新版模板（按类目），提供 `render_template(category, project, pkg) -> str` API
- `CoordinatorService.initialize_project`：首条 REQ 时调用，创建飞书 ARCHITECTURE 文档 + 注册 ProjectConfig
- `FeishuGateway.create_architecture_document` / `fetch_document_revision`：封装飞书 API（复用已有 `create_spec_document` 模式）
- 并发检查辅助函数 `_has_concurrent_spec(project, exclude_req_id)` 放在 `SpecContextBuilder`
- 单元测试：`test_architecture_templates.py` / `test_initialize_project.py` / `test_concurrent_spec_gate.py`

---

## 12. 迁移策略（现有 state.json）

部署新版前：
1. 备份 state.json
2. 手工补齐已有项目的 ProjectConfig：
   - 每个已有 `project` 分配 `category`（运维同学根据实际情况选）
   - 每个 project 在飞书手动创建 ARCHITECTURE 文档，贴入相应模板渲染结果
   - 把 `architecture_doc_id` / `architecture_doc_url` / `category` / `template_version` 写入 state.json
3. 删除 state.json 中已废弃字段（`github_repo_url` / `architecture_yaml_initialized` / `acm_registry_initialized` / `onboarding_state`）
4. 启动新版服务

**允许遗留值存在**：新版 `_requirement_from_payload` / `_project_config_from_payload` 忽略未知字段，不会启动失败。

---

## 13. 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 飞书文档 revision 语义不稳定 | revision 回证不可靠 | 先以 `updated_at` 时间戳兜底，revision 实际能力待联调验证 |
| 类目模板与项目实际形态不符 | 骨架误导 spec-author | 类目字段允许 project 初始化后人工修订（手动改 state.json） |
| 首条 REQ 创建后飞书文档创建失败 | ProjectConfig 半成品 | 创建失败回滚 Requirement；不落 ProjectConfig |
| 并发方案 C 过严 | 小团队并行受阻 | 监听实际使用痛点，痛了升级到 B |
| 拆除 GitHubClient 后 `GITHUB_TOKEN` 字段残留 | 配置困惑 | `Settings.github_token` 字段降级为可选无人用，后续 Phase 2 复用 |

---

## 14. 测试策略

### 14.1 单元

- 模板渲染：5 类目 × 占位符替换正确
- `initialize_project`：创建飞书文档成功路径 + 失败回滚
- 并发门禁：同项目两条 REQ 同时 SPEC_DRAFTING 第二条被拒
- spec-context payload 新字段完整性

### 14.2 集成

- 首条 REQ 创建 → ProjectConfig + ARCHITECTURE 飞书文档均到位
- 后续 REQ 创建 → 不重复创建文档
- spec-context + spec_submit 完整回路（含 revision 回证）

### 14.3 回归

- 老 state.json（含 `github_repo_url` 等）加载不崩
- 需求层所有现有流程（DRAFTING → APPROVED）不受影响

---

## 15. Phase 2 接入点（仅作楔子，不实现）

- 当 Phase 2 引入 Impl 层时，ARCHITECTURE 飞书文档内容可被一次性导出到 GitHub 仓库 `ARCHITECTURE.yaml`
- 之后 GitHub 成为事实源，飞书文档变为历史快照
- 这个"离开飞书上 GitHub"的时机和机制本身是一个独立设计决策，当前不预设

---

## 16. 上下文契约一致性校验

对照 `context-chain-principle.md` Spec 层契约：

| 契约项 | 本方案覆盖 |
|--------|-----------|
| 消费：需求文档 8 字段 | ✅ URL 传递，agent 自读 |
| 消费：review_summary | ✅ payload 返回 |
| 消费：ARCHITECTURE.yaml | ✅ URL 传递（当前项目状态），agent 自读 |
| 消费：tech_stack | ✅ payload 返回（ProjectConfig） |
| 消费：设计系统快照 | ⚠️ 占位 null（Phase 2） |
| 产出：spec_document_url | ✅ 已有 |
| 产出：spec_review_summary | ✅ 已有 |
| **产出：ARCHITECTURE 演化版本** | ✅ **新增**（本方案核心） |
| 防漂移：需求字段全覆盖 | 📋 交 spec-reviewer 层 |
| 防漂移：ARCHITECTURE 演化与 Spec §8 一致 | 📋 **新增验证维度**，spec-reviewer 需校验 |
