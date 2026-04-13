# 项目 Onboarding 与项目级上下文管理 — 设计文档

> 日期：2026-04-14
> 状态：已批准，待实现
> 关联方法论：[harness-engineering-methodology-v2.0.md](../../context/harness-engineering-methodology-v2.0.md) §3.2 项目级上下文

---

## 一、问题背景

Spec 转化服务（工具5）依赖四类项目级上下文：

| 上下文 | 文件位置 |
|---|---|
| ARCHITECTURE.yaml | GitHub 仓库根目录 |
| ACM 注册表 | `spec/registry/consolidated.yaml` |
| 设计系统文档 | 飞书文档（ProjectConfig.design_system_doc_id） |
| 设计系统快照 | `specs/design-system-snapshot.yaml` |

在首个需求启动前，这四类文件均不存在。需要设计一套机制，确保它们在合适的时机自动生成并注入后续流程。

---

## 二、架构原则约束

Coordinator Service 是纯规则化的流程驱动器，**不直接调用 AI**。三层分离必须守住：

```
Workflow Service（Coordinator）  ← 纯规则、状态机、事件派发
        ↓ Hook
Hook 实现层                      ← 调度能力层
        ↓
能力层（OpenClaw / 独立脚本）     ← 做 AI 工作，结果回调给 Coordinator
```

路径 C（新项目模板生成）：Coordinator 直接做，无 AI 调用，纯模板填充。
路径 B（已有代码库 AI 扫描）：AI 调用移到独立脚本，Coordinator 只验证文件存在。

---

## 三、新增数据模型

### ProjectConfig

```python
@dataclass
class ProjectConfig:
    github_repo_url: str                    # https://github.com/org/repo
    is_new_project: bool                    # true = 全新项目，false = 已有代码库
    tech_stack: dict[str, str]              # language/framework/database/test_framework
    architecture_yaml_initialized: bool = False
    acm_registry_initialized: bool = False
    design_system_doc_id: str | None = None # 飞书设计系统文档 ID，None = 未创建
    pending_onboarding_step: str | None = None  # 中断恢复用：当前等待哪个问题的回答
```

存储在 `CoordinatorService.project_configs: dict[str, ProjectConfig]`，随 `JsonStateStore` 持久化。

### Requirement 模型新增字段

```python
needs_ui: bool = False
github_repo_url: str = ""           # 从 ProjectConfig 复制，供 Spec 服务直接读
hifi_prototype_url: str = ""        # Bitable 高保真原型链接
hifi_prototype_confirmed: bool = False
```

**`needs_ui` 收集时机**：在创建群"新建需求"指令解析时，作为可选标记收集。
格式：`新建需求 [项目名] [需求名] [简述] [--ui]`，有 `--ui` 标记则 `needs_ui=true`，默认 false。
不在 Onboarding 阶段问，而是和需求本身一起声明，因为同一个项目的不同需求可以有不同值。

### config.py 新增

```python
github_token: str                   # GitHub API 写权限（contents: write）
github_default_branch: str = "main"
```

---

## 四、Onboarding 对话流程

### 触发条件

创建群收到"新建需求"指令，且 `project_configs` 中无该项目记录。

### 对话序列（创建群内进行）

```
用户：新建需求 [项目名] [需求名] [简述]

Coordinator：「检测到 [项目名] 是新项目，先完成项目初始化（3 个问题）。」

  问题1：「GitHub 仓库地址？（格式：https://github.com/org/repo）」
  → 格式校验，失败重问

  问题2：「全新项目还是已有代码库？
           A. 全新项目（从零开始，无现有代码）
           B. 已有代码库（需先运行初始化脚本，见下方说明）」

  问题3：「技术栈？（如：Python/FastAPI/PostgreSQL/pytest）」

Coordinator：「信息收集完成，正在初始化项目上下文…」
  （后台异步执行 bootstrap）

bootstrap 完成后通知：
  「[项目名] 初始化完成 ✓
    · ARCHITECTURE.yaml 已创建
    · ACM 注册表已创建（spec/registry/consolidated.yaml）
    · 需求 REQ-PROJ-001 开始进入讨论阶段。」
```

### 中断恢复

- Onboarding 进行中途用户离开：`pending_onboarding_step` 保存当前进度
- 下次创建群消息到来时，从断点继续提问，不重头开始

### Requirement 阻塞规则

- Requirement 对象在收集完前三个问题后立即创建（`status = CREATED`）
- Bootstrap **完成前**，不发送 Author 私聊邀请，不触发 DISCUSSING
- Bootstrap 完成后，才触发 DISCUSSING，通知 Author

---

## 五、Bootstrap 机制

### 路径 C：全新项目（快速路径，Coordinator 直接执行）

```
输入：tech_stack + github_repo_url

动作：
  1. 渲染 ARCHITECTURE.yaml 骨架（tech_stack 填入，services/modules/data_models 留空）
  2. 创建空 ACM 注册表（last_updated + registry: []）
  3. GitHub API 提交两个文件到 default branch
     commit message: "chore: initialize project context (ARCH + ACM registry)"
  4. 更新 ProjectConfig（initialized = true），保存状态

无 AI 调用，纯模板填充。
```

### 路径 B：已有代码库（半自动，移出 Coordinator 边界）

```
Coordinator 动作：
  发创建群提示：
  「已有代码库需要先生成架构快照。请运行：
    python scripts/bootstrap_architecture.py --repo [url] --branch main
    完成后回复"初始化完成"继续。」

  等待用户回复"初始化完成" → 调用 GitHub API 验证文件存在
  验证通过 → 继续 bootstrap（只创建 ACM 注册表）
  验证失败 → 提示重试

独立脚本 scripts/bootstrap_architecture.py 做：
  1. 读取仓库目录树（深度2）+ 关键文件（routes/models 等）
  2. 调用 Claude API 生成 ARCHITECTURE.yaml 草稿
  3. 展示草稿供人工确认，确认后提交 GitHub

升级路径：Phase 2 OpenClaw Skills（github-bridge + architecture-scanner）建好后，
路径 B 的 AI 调用从脚本迁移到 OpenClaw，Coordinator 改为触发 Hook，其余不变。
```

---

## 六、UI 设计系统生命周期

### Create（首次创建）

```
触发：项目内第一个 needs_ui=true 的需求进入 APPROVED 状态
条件：ProjectConfig.design_system_doc_id is None

动作：
  1. 飞书 Docx API 从模板复制新文档，标题："{项目名} 设计系统"
  2. 文档 ID 写入 ProjectConfig.design_system_doc_id
  3. 保存 Coordinator 状态
```

### Append（追加设计决策）

```
触发：高保真原型在项目群确认（hifi_prototype_confirmed = true）

动作：
  1. 从 Requirement 提取 UI 设计信息（组件列表 + 设计决策）
  2. 飞书 Docx API Append 到设计系统文档对应 section：
     · 新增组件 → 追加到"组件库" section
     · 设计决策 → 追加到"设计决策日志" section（带时间戳 + REQ ID）
  3. 更新 Bitable 高保真原型链接字段

约束：Append-only，不修改历史记录，每条带 REQ ID 可追溯。
```

### Export（导出快照）

```
触发：Spec 转化服务调用前（由 Spec 转化服务主动调用）

动作（在 Spec 转化服务内，非 Coordinator）：
  1. 读 ProjectConfig.design_system_doc_id
  2. 飞书 Docx API 读取全文，解析成结构化 YAML
  3. 写入 GitHub：specs/design-system-snapshot.yaml

跳过条件：
  · needs_ui=false → 跳过，不生成 design-ui.md
  · design_system_doc_id is None → 跳过，记录警告日志
```

---

## 七、上下文完备性汇总

| 上下文 | 生成时机 | 执行者 | 存储位置 |
|---|---|---|---|
| ARCHITECTURE.yaml | 项目 Onboarding（路径C 自动 / 路径B 脚本） | Coordinator / 脚本 | GitHub 根目录 |
| ACM 注册表 | 项目 Onboarding | Coordinator | `spec/registry/consolidated.yaml` |
| ACM 注册表追加 | 卡点1a 通过 | checkpoint-handler | 同上（append） |
| 设计系统文档 | 首个 UI 需求 APPROVED | Coordinator | 飞书文档 |
| 设计系统追加 | 高保真原型确认 | Coordinator | 飞书文档（append） |
| 设计系统快照 | Spec 生成前 | Spec 转化服务 | `specs/design-system-snapshot.yaml` |

---

## 八、实现范围（本设计文档覆盖）

**在 Coordinator Service 内：**
- 新增 `ProjectConfig` 数据模型
- `CoordinatorService` 新增 `project_configs` 字典 + onboarding 方法
- `JsonStateStore` 序列化/反序列化 `ProjectConfig`
- `CoordinatorRuntimeApp` 新增创建群 Onboarding 对话处理分支
- `ProjectBootstrapper` 新增类（路径C 模板填充 + GitHub API 写文件）
- `Requirement` 模型新增 `needs_ui` / `github_repo_url` / `hifi_prototype_url` / `hifi_prototype_confirmed`
- `config.py` 新增 `github_token` / `github_default_branch`
- UI 设计系统 Create / Append 逻辑

**独立脚本（新增）：**
- `scripts/bootstrap_architecture.py`（路径B AI 扫描，独立运行）

**不在本设计范围内：**
- Spec 转化服务（下一个设计文档）
- 高保真原型生成 Agent（工具14，Phase 2）
- 设计系统 Export（由 Spec 转化服务负责）
- checkpoint-handler ACM 追加逻辑（Phase 2/3）
