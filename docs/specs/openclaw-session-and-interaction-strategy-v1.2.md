# OpenClaw Session 与交互策略 v1.2

## 1. 目标

本文档用于解决两个现实问题：

1. OpenClaw agent 接入多个群时，session 与群绑定，容易出现绑定数量和上下文污染问题。
2. 需求构造 agent 需要同时跟进多个需求，必须有明确的上下文隔离方案。

## 2. 已确认的现状

根据当前线上 OpenClaw 实例：

- session key 以 `agent + channel + chatType + subject` 为核心
- Feishu 群聊会形成 group 级 session
- 现网 `ai-founder-brief` 与 `ai-ops-router` 的 session 元数据都体现出“按群建 session”的模式

这意味着：

- 不能把“项目群 = 需求上下文真相源”
- 也不能让 author agent 靠长期驻留多个群来维护多个需求的真实状态

## 3. 设计判断

### 3.1 真相源必须外置

需求上下文的真相源必须由 `Coordinator Service` 外置维护，而不是依赖 OpenClaw session。

真相源至少包括：

- `req_id`
- 当前轮次
- 当前讨论字段
- 已完成字段
- 待补字段
- 最新正式文档快照
- 最新 review 结论
- AI / Human 门禁
- 用户身份映射

### 3.2 OpenClaw session 只作为推理缓存

OpenClaw session 可以存在，但只能视为：

- 短期推理缓存
- 私聊交互表面
- 模型上下文暂存

不能视为：

- 需求流程真相源
- 唯一状态存储
- 多需求并发隔离方案

## 4. 推荐交互结构

第一阶段采用三段式交互：

### 4.1 创建群

用途：

- 创建需求

形式：

- 用户在固定“需求创建群”中 `@CoordinatorService`

### 4.2 author 私聊

用途：

- 高质量需求构造
- 每轮自然对话引导

形式：

- 用户与 `author agent` 私聊
- 私聊启动时显式带上 `req_id`

### 4.3 项目群

用途：

- 同步需求创建结果
- 同步 review / 审查状态
- 同步最终产物

形式：

- 每个项目一个项目群
- 不要求 author 在项目群中持续深聊

## 5. req_id 绑定策略

### 5.1 私聊启动协议

需求创建后，由 Coordinator Service 返回：

```text
REQ-HARNESS-001 已创建。
请私聊需求构造 Agent，并发送：
开始需求构造 REQ-HARNESS-001
```

用户在 author 私聊中发送：

```text
开始需求构造 REQ-HARNESS-001
```

### 5.2 author 首轮确认协议

author 收到后，先固定执行绑定确认：

```text
我已收到需求构造请求。

请确认：
- 需求ID：REQ-HARNESS-001
- 项目：HARNESS
- 名称：多轮需求构造工作流

如果无误，请回复：
确认开始
```

只有确认后，才进入正式需求构造。

### 5.3 私聊活动需求规则

同一个用户与 author 的私聊，在同一时刻只允许一个 `active_req_id`。

若用户要切换需求，必须显式发：

```text
切换需求 REQ-HARNESS-002
```

这样可避免多个需求在同一私聊 session 中混淆。

## 6. 多需求上下文管理方案

### 6.1 外部上下文存储

每个需求都需要有独立的上下文快照，由 Coordinator Service 管理：

- `req_id`
- `project_code`
- `creator_user_id`
- `project_group_id`
- `author_dm_chat_id`
- `current_round`
- `current_discussion_field`
- `completed_fields`
- `pending_fields`
- `document_snapshot`
- `latest_review_result`
- `latest_user_input_excerpt`
- `latest_author_result`
- `latest_reviewer_result`

### 6.2 单轮交互模型

author / reviewer 的主要工作都在各自的私聊交互面完成。

Coordinator Service 不再组装“单轮任务输入包”驱动 agent，而只消费 agent 回传的流程事件。

### 6.3 结果回收模型

每轮流程结果都必须回到 Coordinator Service：

- author 上报“可进入 AI review”
- reviewer 上报“退回修改 / 进入人工确认 / 通过 / 退回”
- Coordinator Service 更新状态机与 Bitable

## 7. OpenClaw 侧建议

### 7.1 不让 author/reviewer 直接成为群真相源

不要让 author/reviewer 靠“加入多个项目群”来维护需求上下文。

项目群中的消息发送建议统一由 Coordinator Service 对应的飞书机器人完成。

### 7.2 author/reviewer 作为智能 worker

OpenClaw 中的 author/reviewer 更适合被视为：

- 智能 worker
- 私聊交互表面
- 单轮推理执行器

而不是需求流程的真相源。

### 7.3 session 管理建议

建议按下面思路使用 session：

- author 私聊 session：作为该用户当前活动需求的交互缓存
- reviewer session：可以更短，甚至按任务调用
- 真正的上下文隔离由 `req_id` 保证，而不是由 session 保证

## 8. Coordinator Service 的新增职责

采用本方案后，Coordinator Service 需要额外负责：

- 创建群与项目群映射
- `req_id -> creator_user_id` 映射
- `req_id -> project_group_id` 映射
- `user_id -> active_req_id` 映射
- `req_id -> author_dm_chat_id` 映射
- 私聊启动与切换协议校验

## 9. 推荐的第一阶段落地方式

第一阶段建议：

1. 创建群中 `@CoordinatorService` 创建需求
2. Coordinator Service 返回私聊启动指令
3. 用户在 author 私聊中显式带 `req_id` 开始构造
4. author 在文档达到阶段门槛后，把流程事件交回 Coordinator Service
5. Coordinator Service 仅写 Bitable / 工作流状态
6. 项目群只负责同步状态和最终结果

## 10. 结论

为避免 OpenClaw 当前“按群建 session”带来的群绑定和上下文污染问题：

- 不把项目群当需求上下文容器
- 不让 author/reviewer 直接承担流程真相源
- 以 `req_id` 作为唯一上下文主键
- 让用户通过 author 私聊获得可感知、非黑盒的需求构造体验
- 让 Coordinator Service 统一承担状态机与持久化
