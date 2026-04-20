# `/create` 卡片化交互改造设计

**日期**: 2026-04-20
**作者**: Claude (与 daxin 协同)
**状态**: 待实施

## 背景

当前 `/create project` 与 `/create req` 均走 CLI flag 路径：

- `/create project <slug> --category <x> [--owner <id>] [--github-username <u>]`
- `/create req <slug> <name> [--summary ...] [--priority ...] ...`

问题：

1. 命令行在飞书里不友好（移动端尤其糟糕，flag 难对齐）。
2. 项目创建丢失了需求卡曾经携带的结构化信息（display_name、brief、tech_stack 等），ARCHITECTURE.md 模板只能靠后续人工补全。
3. 老的需求卡 `/create req` 触发时是先发一张空卡；但项目创建一直没卡片交互，一致性差。

本设计把两条命令统一为 **"触发 → 发卡 → 用户填表 → 提交"** 的两阶段模式，并借此顺便把 ARCHITECTURE.md 模板所需的种子信息收齐。

## 目标 & 非目标

**目标**

- `/create project` 弹项目卡，用户在卡里完整填写，提交后跑 Bootstrap。
- `/create req` 弹需求卡，其中 `project` 变为**下拉选择**（来自 `project_configs`），不再手写 slug。
- 统一幂等语义：同一 `project` 重复提交（已存在但未 PROVISIONED）自动 `resume=True`；已 PROVISIONED 直接拒绝并引导到 `/create req`。
- 收齐 ARCHITECTURE.md 种子字段：`display_name` / `brief` / `tech_stack`。
- 卡片回调去重（避免飞书重投造成双跑）。
- **删除**旧 CLI flag 路径，不保留兼容层。

**非目标**

- 不引入任何 schema/持久化层变更。`project_configs` 的 dataclass 不变。
- 不做权限模型（任意 chat / 任意用户都能触发，沿用现状）。
- 不实现两阶段需求 UI 流程（`needs_ui=true` 后续步骤延后到 Phase 2）。
- 不重构 Bootstrap/Coordinator 的内部分层。

## 用户交互流

### 入口

```
/create project          → 空的项目卡（所有字段在卡里填）
/create req              → 空的需求卡
/create                  → 提示：「请用 /create project 或 /create req」
/create project --xxx    → 忽略 flag，按裸 /create project 处理（正则收紧）
/create req --xxx        → 同上
```

正则收紧为 `^/create (project|req)\s*$`；匹配到带多余参数的输入，走「无效命令」分支，回提示文本。

### 项目卡（新）

字段分两组。

**必填**

| 字段 | 类型 | 约束 |
|---|---|---|
| `project` | `input` (single-line) | `^[a-z][a-z0-9-]{1,30}$` |
| `category` | `select_static` | `KNOWN_PROJECT_CATEGORIES` 全集 |

**可选**（不填则 ARCHITECTURE.md 相应占位符留空字符串）

| 字段 | 类型 | 用途 |
|---|---|---|
| `display_name` | `input` | ARCHITECTURE.md `{{display_name}}` |
| `brief` | `input` (multiline) | ARCHITECTURE.md `{{brief}}` |
| `github_username` | `input` | BootstrapRequest.github_username |
| `tech_stack` | `input` (multiline) | ARCHITECTURE.md `{{tech_stack}}` |

Submit action：`submit_create_project`。

### 需求卡（改造）

基于现行 `_build_requirement_creation_card`，两处改动：

1. `project` 字段：`input` → `select_static`；options 由 `project_configs` 动态生成，只列出 `status == PROVISIONED` 的项目。
2. 删除 `category` 字段（项目层已经定好 category，需求层不再重复选择）。

其余字段（`name` / `summary` / `background_links` / `priority` / `due_date` / `needs_ui`）保持不变。

若 `project_configs` 里没有任何 PROVISIONED 项目，`/create req` 直接回文本「尚无已注册项目，请先 `/create project`」，**不发卡**。

## 架构与数据流

### 项目提交

```
card submit (action=submit_create_project)
  ↓
_extract_project_form_payload(card_event)
  → ProjectCreationFormPayload(
      project, category,                              # 必填
      display_name, brief, github_username, tech_stack, # 可选
      owner_user_id = card.operator.open_id,
      creator_chat_id = card.context.open_chat_id,
    )
  ↓
查 project_configs[project]：
  ├─ 不存在             → resume = False
  ├─ 存在, PROVISIONED  → 回拒绝文本（「已完成 Bootstrap，请用 /create req」）
  └─ 存在, 其他状态     → resume = True（静默续跑）
  ↓
ProjectBootstrapService.run(BootstrapRequest(
    project, category, owner_user_id, creator_chat_id,
    resume=resume, github_username=github_username,
))
  ↓ （在 Bootstrap 内部，渲染 ARCHITECTURE.md 时）
render_template(category, project=project,
                seed={display_name, brief, tech_stack})
  ↓
reply: 成功消息 or 失败文本（含续跑提示）
```

### 需求提交

沿用现有路径，仅扩展读取方式：

```
card submit (action=submit_create_requirement)
  ↓
_extract_creation_form_payload(card_event)   # 现有方法
  → CreationFormPayload(
      project, name, summary,
      background_links, priority, due_date, needs_ui,
      # category 字段移除
    )
  ↓
CoordinatorService.create_requirement_from_group(req)   # 现有
  → req-registry append + bitable create + group invite
```

### 代码边界

| 模块 | 动作 | 位置 |
|---|---|---|
| `_build_project_creation_card(context)` | **新增** | `service_app.py` |
| `ProjectCreationFormPayload` dataclass | **新增** | `protocols.py` |
| `_extract_project_form_payload(payload, user_id, user_name)` | **新增** | `service_app.py` |
| `submit_create_project` action branch | **新增** | `_handle_card_action_payload` |
| `_build_requirement_creation_card` | **改造**（project → select_static, 删 category） | `service_app.py` |
| `_extract_creation_form_payload` | **改造**（去掉 category） | `service_app.py` |
| `parse_create_project_command` / `parse_create_req_command` | **改造**（正则收紧为零参） | `service_app.py` |
| `_handle_create_project_command` | **改造**（直接返回卡片，不再调 Bootstrap） | `service_app.py` |
| `_handle_create_req_command` | **改造**（校验项目存在后发卡） | `service_app.py` |
| `render_template` | **改造**（新增 `seed` kwarg） | `architecture_templates.py` |
| 5 个 ARCHITECTURE 模板 | **改造**（加 `{{display_name}}` / `{{brief}}` / `{{tech_stack}}` 占位） | `docs/context/architecture-templates/*.yaml` |
| `_seen_card_action_ids` 去重 LRU | **新增** | `CoordinatorRuntimeApp.__init__` |

## 错误处理 & 边界

### 1. 卡片级验证（客户端）

飞书 v2 form 自带 `required:true`，必填项缺失时「提交」按钮由飞书灰掉，**服务端不需要兜底分支**。

### 2. 服务端校验（submit handler）

| 场景 | 回复 |
|---|---|
| `project` 不匹配 `^[a-z][a-z0-9-]{1,30}$` | 「项目代号格式不合法：...」 |
| `project` 存在且 `status != PROVISIONED` | `resume=True` 静默续跑；成功后回「项目 X 已就绪：...」 |
| `project` 存在且 `status == PROVISIONED` | 「项目 X 已经完成 Bootstrap，请用 `/create req`」 |
| `category` 不在 `KNOWN_PROJECT_CATEGORIES` | 理论上不会发生（下拉锁死），兜底 `raise` |
| Bootstrap 中途失败（`BootstrapStepError`） | 「中断于 Step N (名)：...<br>点 `/create project` 重新提交同样的项目代号即可自动续跑」 |
| 需求卡 submit 时 `project_configs[project].status != PROVISIONED` | 「项目 X 正在初始化 (状态:BOOTSTRAPPING)，暂不可新建需求」 |
| 需求卡 submit 时项目下拉为空（无任何已注册项目） | 卡片构造时直接回「尚无已注册项目，请先 `/create project`」；不发卡 |

### 3. 幂等与去重

- 飞书 IM 重投：沿用已有 `_seen_message_ids`。
- 飞书卡片回调重投：**新增** `_seen_card_action_ids`，去重键 = `open_message_id + action.value.action`（同一条卡片消息 + 同一个 action 按钮只处理一次）。结构同 `_seen_message_ids`：`OrderedDict`，bounded LRU ≤ 1024，满了 popitem(last=False)。
- 双击提交按钮：飞书 form 提交成功后按钮自动禁用 ~2s，加服务端去重足以覆盖。
- Bootstrap 本身幂等（已验证 test4 双投产生两份相同消息的根因已于上一轮修复）。

### 4. 权限边界

沿用现行策略：**任意 chat（DM / 创建群 / 任意群）** 都能触发；project owner 默认取 `card.operator.open_id`。本迭代不加额外权限检查。

## 测试 & 交付

### 新增 / 改造测试（pytest）

- **`tests/test_project_creation_card.py`**（新增）
  - 卡片结构：必填字段、下拉类目选项齐全、submit 按钮 `action=submit_create_project`
  - `_extract_project_form_payload`：正常提取、可选字段缺省、项目代号 trim

- **`tests/test_service_app_card_submit_project.py`**（新增，集成）
  - 首次提交 → `Bootstrap.run(resume=False)` → 成功消息
  - 重复提交同一名（BOOTSTRAPPING）→ `run(resume=True)` → 仍成功
  - 重复提交同一名（PROVISIONED）→ 不调用 Bootstrap，回拒绝消息
  - Bootstrap 抛 `BootstrapStepError` → 错误文本含 step 名

- **`tests/test_service_app_card_submit_req.py`**（改造）
  - `project` 下拉选项来自 `project_configs`
  - 无 PROVISIONED 项目 → `/create req` 直接回拒绝文本（不发卡）
  - 选中的项目 `status != PROVISIONED` → 拒绝

- **`tests/test_service_app_slash_create_project.py`**（调整）
  - 带 flag 的老用例**删除**（CLI flag 路径不再支持）
  - 新增：`/create project` → 返回项目卡（而非直接跑 Bootstrap）
  - 新增：`/create project test5 --category x` → 带参数也视作无效，回提示

- **`tests/test_card_dedupe.py`**（新增）
  - 同一 `open_message_id + action.value.action` 的重复卡片回调：只处理一次

### 冒烟验证（staging）

1. `/create project` → 出项目卡 → 填 `test5` / saas-ai-automation → 提交 → Bootstrap 成功消息
2. `/create project` → 出项目卡 → 填 `test5`（已 PROVISIONED）→ 提交 → 拒绝消息
3. `/create req` → 出需求卡 → 下拉里能看到 `test5` → 填名称/简述 → 提交 → REQ 消息 + bitable 写入 + req-registry 追加
4. `/create` → 提示「请用 /create project 或 /create req」

### 向前迁移

- **破坏性变更**：旧 CLI flag 路径删除。内部冒烟脚本、测试里凡是 `/create project xxx --category yyy` 的用法，需要重写为卡片提交或直接调用 `CoordinatorRuntimeApp._handle_card_action_payload`。
- ARCHITECTURE 模板占位：5 个分类模板都要加 `{{display_name}}` / `{{brief}}` / `{{tech_stack}}` 占位；可选字段缺省则替换为空字符串。
- 所有现存项目（`test3` / `test4`）不受影响——已 PROVISIONED 的项目新卡片会直接被拒，用户走 `/create req`。

### 工作量估算

| 模块 | 规模 |
|---|---|
| 新卡 + payload + extractor | ~200 行 |
| `/create` 路由正则收紧 + 旧处理器删除 | ~50 行净删 |
| 需求卡改造（下拉） | ~30 行 |
| ARCHITECTURE 模板占位（5 个文件） | ~50 行 |
| `render_template` seed 参数 | ~20 行 |
| 卡片回调去重 | ~30 行 + 测试 |
| 测试 | ~400 行（含改造） |

## 开放问题

无。所有决策已在 brainstorm 阶段敲定：

- Q1: 入口 = 直接发卡（不做菜单）
- Q2: 项目卡字段 = A 必填 + C 可选；种子信息**只**注入 ARCHITECTURE.md，不改 schema
- Q3: 需求卡 = project 下拉 + 其余字段不变
- Q4: 旧 CLI flag 路径**完全删除**，不保留兼容
