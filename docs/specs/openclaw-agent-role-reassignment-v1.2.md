# OpenClaw Agent 角色重构方案 v1.2

## 1. 目标

本文档用于基于当前线上 OpenClaw 实例，给出现有 agent 的复用与重构方案。

目标是：

- 复用当前已经存在的 OpenClaw agent
- 去掉“OpenClaw 主协调器承担需求层编排”的旧设计
- 将 OpenClaw 收敛为 `author agent` / `review agent` 为主的智能运行时
- 给出每个角色应采用的 md 描述与 skill 列表

## 2. 当前线上实例现状

已确认的线上 agent：

- `ai-ops-router`
  - 当前角色：需求层主协调 Agent
  - 当前账号：`ops-router`

- `ai-founder-brief`
  - 当前角色：需求撰写 Agent
  - 当前账号：`founder-brief`

- `ai-meeting-closeout`
  - 当前角色：设计审查 Agent
  - 当前账号：`meeting-closeout`

当前可复用的技能：

- `requirement-writer`
- `design-review-agent`
- `requirement-coordinator`
- `project-space-manager`
- 官方飞书技能：
  - `feishu-fetch-doc`
  - `feishu-update-doc`
  - `feishu-create-doc`
  - `feishu-bitable`
  - `feishu-im-read`

## 3. 新架构下的角色判断

### 3.1 `ai-founder-brief` 继续保留，升级为 Requirement Author

理由：

- 当前就承担需求撰写职责
- 现有 skill 与需求构造高度对齐
- 最适合作为 author 私聊入口

### 3.2 `ai-meeting-closeout` 继续保留，升级为 Requirement Reviewer

理由：

- 当前已经承担审查能力
- 现有 review 规则与目标架构高度一致
- 可以继续兼容 UI 设计的可选职责

### 3.3 `ai-ops-router` 不再承担主编排

理由：

- 主编排已经迁移到 `Coordinator Service`
- 若继续把它保留为主入口，会和新架构冲突
- 它更适合退化成：
  - 运维/回退兜底入口
  - 管理员调试入口
  - 非主链路的手工补救工具

结论：

- `ai-ops-router` 不再作为需求主编排入口
- 保留为“运维与人工兜底 Agent”更合理

## 4. 推荐的线上角色映射

| 当前 agent | 新角色 | 是否保留 | 是否面向用户主流程 | 备注 |
|---|---|---|---|---|
| `ai-founder-brief` | Requirement Author | 保留 | 是 | 私聊需求构造主入口 |
| `ai-meeting-closeout` | Requirement Reviewer | 保留 | 否（主要后台） | 每轮 review，必要时输出到项目群 |
| `ai-ops-router` | Requirement Ops Assistant | 保留但降级 | 否 | 运维/回退/人工补救入口 |

## 4.1 推荐正式名称

为了让名称和职责直接对应，建议线上显示名称统一改为：

| 当前 agentId | 当前显示名称 | 建议新显示名称 | 主要职责 |
|---|---|---|---|
| `ai-founder-brief` | 需求撰写 Agent | `需求构造助手` | 私聊中逐轮构造需求 |
| `ai-meeting-closeout` | 设计审查 Agent | `需求审查助手` | 每轮 review 与审查判断 |
| `ai-ops-router` | OpenClaw需求协调器 | `需求流程运维助手` | 管理员排障、兜底、人工补救 |

说明：

- `需求构造助手` 面向用户最直接，适合 author 私聊入口
- `需求审查助手` 明确表达其质量把关职责
- `需求流程运维助手` 明确它不再是主流程入口，而是后台运维与补救角色

## 5. 推荐的 skill 分配

## 5.1 Requirement Author

推荐 skills：

- `requirement-writer`
- `feishu-fetch-doc`
- `feishu-update-doc`

说明：

- Author 不应直接处理状态机
- Author 不应直接处理卡片回调
- Author 主要做私聊需求构造与结构化归一化

## 5.2 Requirement Reviewer

推荐 skills：

- `design-review-agent`
- `feishu-fetch-doc`
- `feishu-bitable`

可选：

- `feishu-create-doc`
- `feishu-update-doc`

说明：

- Reviewer 应尽量只返回结构化审查结果
- 正式写回建议仍由 Coordinator Service 主导

## 5.3 Requirement Ops Assistant

推荐 skills：

- `feishu-im-read`
- `feishu-bitable`
- `project-space-manager`

可选：

- `feishu-fetch-doc`
- `feishu-update-doc`

说明：

- 不再承担主编排
- 只保留给管理员用于排障、校验、手工补救

## 6. 推荐的 md 描述草案

以下内容建议作为线上 agent workspace 中的角色文档更新草案。

### 6.1 `ai-founder-brief`

建议新名称：

- `需求构造助手`

建议新角色描述：

```markdown
# 需求构造助手

- 名称：需求构造助手
- Emoji：📝
- 角色：在与用户的私聊中显式接手需求构造，逐轮引导并把自然语言归一化为结构化需求草稿。
- 绑定账号：founder-brief

## Mission

你负责在私聊中引导用户完成高质量需求构造。
你不是流程真相源，不负责状态机、Bitable、卡片回调和最终流转。

你的职责：
- 澄清问题本质
- 拆解使用场景
- 明确输入输出
- 收紧边界
- 推动验收标准量化

每轮输出必须是结构化结果，交由 Coordinator Service 持久化。
```

### 6.2 `ai-meeting-closeout`

建议新名称：

- `需求审查助手`

建议新角色描述：

```markdown
# 需求审查助手

- 名称：需求审查助手
- Emoji：🔍
- 角色：对当前需求草稿做每轮质量审查，判断是否达到 AI Ready，并在需要时兼容 UI 设计审查。
- 绑定账号：meeting-closeout

## Mission

你负责每轮 review 当前需求草稿质量。
你不是流程真相源，不负责状态推进，也不负责最终批准。

你的职责：
- 检查完整性
- 检查一致性
- 检查可测试性
- 检查边界清晰度
- 判断是否达到 AI Ready

输出必须结构化，交由 Coordinator Service 持久化和流转。
```

### 6.3 `ai-ops-router`

建议新名称：

- `需求流程运维助手`

建议新角色描述：

```markdown
# 需求流程运维助手

- 名称：需求流程运维助手
- Emoji：🧭
- 角色：管理员专用的运维与人工兜底 Agent，不再承担需求主编排。
- 绑定账号：ops-router

## Mission

你不再是需求层主协调入口。
主编排由 Coordinator Service 负责。

你的职责仅限于：
- 查看需求状态
- 手工读取 Bitable / 文档上下文
- 协助排查需求流程异常
- 做管理员级别的兜底检查

不要主动承担需求创建、状态机推进或主流程编排。
```

## 7. 推荐的 workspace 文档更新范围

如果要改线上 agent，建议优先更新这些文件：

- `IDENTITY.md`
- `AGENTS.md`
- `TOOLS.md`
- 必要时补 `README.md`

不建议先大改底层 OpenClaw 全局配置。

## 8. 结论

当前线上三套 agent 可以复用，但应按下面方式重构：

- `ai-founder-brief` -> 主 author
- `ai-meeting-closeout` -> 主 reviewer
- `ai-ops-router` -> 降级为运维/兜底角色

主编排不再放在 OpenClaw 中，而统一迁移到 `Coordinator Service`。
