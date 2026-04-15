# Spec Context 端点与 ARCHITECTURE.yaml 注入（P0-1）设计文档

**日期**：2026-04-15
**范围**：Pre-Phase-2 路线图的 P0-1 任务
**目标读者**：实施本方案的工程师 / Code Review

---

## 1. 目标

在 Coordinator Service 新增 HTTP 查询端点 `/queries/openclaw/spec-context`，让 spec-author Agent 在每轮 Spec 撰写启动时通过 Coordinator 拿到项目级上下文（需求文档 URL、ARCHITECTURE.yaml 原文、needs_ui 等），替代目前"agent 只靠文档 URL 自行决定上下文来源"的薄弱链路。

同时引入**运行时防绕过机制**（context_token 握手 + architecture_commit_sha 回证），防止 agent 跳过 Coordinator 直接操作飞书/GitHub 导致上下文漂移。

---

## 2. 非目标（P0-1 明确不做）

- **Coordinator 内结构化 8 字段**：现阶段 Coordinator 不解析飞书需求文档结构。agent 仍通过 `feishu_fetch_doc` 用 spec-context 返回的 `requirement_document_url` 去飞书拉 8 字段内容。此项列为 P1 技术债。
- **design_system_snapshot**：spec-context 响应 payload 保留该字段，P0-1 恒为 `null`；spec-author 在 `needs_ui=true` 且快照为空时走降级处理（在 Spec 中明确标注 UI 约束需人工确认）。
- **GitHub API 客户端的缓存 / 重试 / 速率治理**：每次请求实时打 `api.github.com`，异常直接映射 HTTP 状态码，不做本地缓存。
- **需求回炉 fallback**：APPROVED → DRAFTING 的回炉机制不在本次实现。但数据模型为其预留字段，方便后续 P1-2 零改 schema 落地。
- **Spec 子状态机扩展**：复用现有 `WorkflowStatus`（`APPROVED → SPEC_DRAFTING → SPEC_LOCKED` 已就绪）。不新增 `SPEC_REJECTED` 等状态，reject / fallback 留给 P1。

---

## 3. 架构

### 3.1 组件

**新增模块**：

- `src/requirement_workflow_v12/github_client.py`
  `GitHubClient(token: str).fetch_file(repo_url, path, ref="HEAD") -> FetchedFile(content: str, commit_sha: str)`
  纯标准库 `urllib` 调 GitHub Contents API，无第三方依赖。异常分 `GitHubAuthError` / `GitHubNotFoundError` / `GitHubTransientError`，方便端点分类映射状态码。

- `src/requirement_workflow_v12/spec_context.py`
  `SpecContextBuilder(service, github_client).build(req_id) -> SpecContextResult`
  负责：状态门禁 → 组装 payload → 调 GitHubClient → 生成 context_token → 写回 Requirement → 返回响应体。

**修改模块**：

- `models.py`：`Requirement` 新增两个字段
  - `active_spec_context_token: str = ""`
  - `spec_context_snapshot_sha: str = ""`
  - Spec 子状态**复用现有 `Requirement.status`**（`WorkflowStatus.SPEC_DRAFTING` / `SPEC_LOCKED` 已存在，`state_machine.apply_event` 已经支持 `APPROVED → SPEC_DRAFTING`、`SPEC_DRAFTING → SPEC_LOCKED`）。
- `store.py`：`_requirement_from_payload` 读两个新字段，给默认值兼容旧数据。
- `service_app.py`：
  - 路由表新增 `/queries/openclaw/spec-context` → `handle_openclaw_spec_context_query`
  - `handle_openclaw_spec_turn_callback` 增加 token 校验 + sha 回证 + spec_status 推进
- `docs/agents/spec-author/SKILL.md`：
  - Step 1 替换为"调 spec-context"，Step 2 基于返回值读飞书需求文档
  - 新增 context_token / architecture_commit_sha 强制回传约束
  - 新增"禁止直接调用 feishu_fetch_doc 读取非 requirement_document_url 中 doc_token 的文档"

**环境变量**：

- `GITHUB_TOKEN`：fine-grained PAT，仓库级只读
- `ARCHITECTURE_YAML_PATH`：可选，默认 `ARCHITECTURE.yaml`

### 3.2 数据流（spec_start 正常路径）

```
ai-ops-router 触发 spec-author
  ↓
spec-author: POST /queries/openclaw/spec-context {req_id}
  ↓
Coordinator:
  - HMAC 校验
  - 状态门禁：status == APPROVED 且 spec_status ∈ {NONE, SPEC_DRAFTING, SPEC_REJECTED}
  - 读 ProjectConfig.github_repo_url
  - GitHubClient.fetch_file(repo_url, ARCHITECTURE_YAML_PATH)
  - 生成 context_token，写入 requirement.active_spec_context_token
  - save_snapshot
  - 返回 {context, context_token, architecture_commit_sha}
  ↓
spec-author 写 Spec，完成一轮后:
  POST /callbacks/openclaw/spec-turn {
    req_id, event: "spec_start",
    context_token, architecture_commit_sha,
    summary, spec_document_url
  }
  ↓
Coordinator:
  - HMAC 校验
  - token 校验：payload.context_token == requirement.active_spec_context_token
  - 写 requirement.spec_context_snapshot_sha
  - spec_status: NONE → SPEC_DRAFTING
  - save_snapshot
  - 返回 {ok: true}
```

`spec_submit` 路径类似，额外：校验 `spec_status == SPEC_DRAFTING` → 推进到 `SPEC_LOCKED` → 清空 `active_spec_context_token`。

### 3.3 防绕过三层约束

| 层级 | 机制 | 作用 |
|------|------|------|
| 文字约束 | spec-author SKILL.md 显式禁止绕过 spec-context | 告诉 agent 应该怎么做 |
| token 握手 | Coordinator 对 spec-turn callback 校验 context_token | 强制 agent 必须先调 spec-context |
| sha 回证 | spec_submit 回传 architecture_commit_sha，写入 Requirement 审计字段 | 为 Reviewer 提供基准版本溯源 |

### 3.4 响应 payload

```json
{
  "ok": true,
  "context": {
    "req_id": "REQ-xxx",
    "name": "…",
    "project": "…",
    "status": "APPROVED",
    "spec_status": "NONE",
    "needs_ui": true,
    "hifi_prototype_url": "…",
    "design_system_snapshot": null,
    "requirement_document_url": "https://feishu…",
    "spec_document_url": "",
    "spec_document_id": "",
    "architecture_yaml": "<raw yaml text>",
    "architecture_commit_sha": "abc123…",
    "github_repo_url": "https://github.com/org/repo",
    "latest_review_summary": "…"
  },
  "context_token": "spec_ctx_REQ-xxx_1713230000_a8f2",
  "expires_hint": "valid until spec_status transitions to SPEC_LOCKED or a newer token is issued"
}
```

---

## 4. 错误映射

### 4.1 spec-context 查询端点

| 场景 | HTTP | 响应 error |
|------|------|-----------|
| HMAC 失败 | 401 | `unauthorized` |
| payload 非法 / 缺 req_id | 400 | `invalid_payload` |
| 需求不存在 | 404 | `not_found` |
| 状态门禁失败 | 409 | `invalid_state` |
| `github_repo_url` 未配置 | 500 | `project_misconfigured` |
| `GITHUB_TOKEN` 未配置 | 500 | `github_auth_missing` |
| GitHub 401/403 | 502 | `github_auth_failed` |
| GitHub 404（文件缺失） | 502 | `architecture_yaml_missing` |
| GitHub 超时 / 5xx | 503 | `github_transient` |

### 4.2 spec-turn callback 新增校验

| 场景 | HTTP | 响应 error |
|------|------|-----------|
| 缺 context_token | 400 | `missing_context_token` |
| context_token 不匹配 | 409 | `stale_context_token` |
| spec_submit 缺 architecture_commit_sha | 400 | `missing_commit_sha` |

---

## 5. 状态门禁

| 当前 requirement.status | spec-context 可调？ | spec_start 可调？ | spec_submit 可调？ |
|------------------------|-------------------|------------------|-------------------|
| 非 `APPROVED` / `SPEC_DRAFTING` | 否（409） | 否 | 否 |
| `APPROVED` | **是** | **是**（推进到 `SPEC_DRAFTING`） | 否（必须先 start） |
| `SPEC_DRAFTING` | **是**（签发新 token） | 否（已开始） | **是**（推进到 `SPEC_LOCKED`） |
| `SPEC_LOCKED` | 否（409） | 否 | 否 |

---

## 6. 并发语义

- 多次 spec-context 查询：token 覆盖写，最后一次生效，之前 token 作废
- spec-turn callback 的 token 校验 + spec_status 推进 + save_snapshot 必须在同一临界区内完成（复用 service 已有的锁/串行机制）
- 需求层并发与本端点无耦合：本端点只读 Requirement + 写三个 Spec 相关字段，与需求讨论字段无交叉

---

## 7. 测试策略

### 7.1 单元测试

- **`github_client.py`**
  - `fetch_file` 成功 → 返回 content + sha（mock `urllib` 响应）
  - 401 → `GitHubAuthError`
  - 404 → `GitHubNotFoundError`
  - 超时 / 5xx → `GitHubTransientError`
  - repo_url 解析：`https://github.com/org/repo` / `https://github.com/org/repo.git` 都正确提取 owner/repo

- **`spec_context.py`**
  - 需求不存在 → 抛 `ValueError`
  - 状态门禁：APPROVED+NONE 允许；APPROVED+LOCKED 抛 `SpecContextGateError`；非 APPROVED 抛 `SpecContextGateError`
  - 正常路径：返回 payload 结构完整，token 已写入 requirement
  - GitHub 异常沿透出

### 7.2 集成测试

- **`service_app.handle_openclaw_spec_context_query`**
  - HMAC 缺失 → 401
  - 未知 req_id → 404
  - 状态门禁失败 → 409
  - GitHub 故障 → 502/503
  - 正常 → 200 + payload 含所有必填字段 + token 已落盘

- **`service_app.handle_openclaw_spec_turn_callback`（token 校验增量）**
  - spec_start 不带 token → 400
  - spec_start token 不匹配 → 409
  - spec_start 正常 → spec_status 推进到 SPEC_DRAFTING，snapshot_sha 落盘
  - spec_submit 缺 sha → 400
  - spec_submit 正常 → spec_status 推进到 SPEC_LOCKED，active_spec_context_token 清空

### 7.3 回归

- 确认 `handle_openclaw_requirement_context_query` 行为未变（新字段不返回）
- 确认 `store.load_snapshot` 对缺少新字段的旧 state.json 能正常读回（默认值生效）

---

## 8. 后续路线图联动

- **P0-2**（`github_repo_url` 绑定机制）：本方案假设 `ProjectConfig.github_repo_url` 已配置。P0-2 要补全 Onboarding 流程强制采集该字段。
- **P1-1**（SPEC_DRAFTING 超时催办）：依赖 `spec_status` 字段，本方案已落。
- **P1-2**（需求回炉 fallback）：依赖 `spec_status == SPEC_REJECTED` 语义，本方案已落字段。
- **P2**（Coordinator 飞书文档结构化解析）：解决 P0-1 明确不做的"agent 直读飞书"问题，让 spec-context 返回结构化 8 字段，彻底关闭绕过路径。

---

## 9. 上下文契约一致性校验

对照 `docs/context/infra/context-chain-principle.md` Section 五 Spec 层契约：

| 契约项 | 本方案覆盖 |
|--------|-----------|
| 消费：需求文档 8 字段 | ⚠️ 部分（URL + 需 agent 自读） |
| 消费：review_summary | ✅ payload 返回 |
| 消费：ARCHITECTURE.yaml | ✅ payload 返回原文 + sha |
| 消费：tech_stack | 📋 P1-1（ProjectConfig 已有，暂不返） |
| 消费：设计系统快照 | ⚠️ 占位 null |
| 产出：spec_document_url | ✅ 现有 spec_start 流程已覆盖 |
| 产出：spec_review_summary | ✅ 现有 spec_submit 流程已覆盖 |
| 防漂移：需求字段全覆盖 | 📋 留给 spec-reviewer 层（P2） |
| 防漂移：上下文消费声明完整性 | ✅ spec-author SKILL 8.2 强制 |

"⚠️" 项在本文档第 2 节和第 8 节已显式说明为非目标 / 后续路线图项。
