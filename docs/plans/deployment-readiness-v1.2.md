# 部署就绪与资源清单 v1.2

## 1. 目标

本文档用于明确三件事：

- 当前距离“可正式部署”还差哪些能力
- 部署需要哪些资源与权限
- 联调按什么顺序推进最快

本清单面向当前架构：

- `Coordinator Service`：独立飞书应用后台
- OpenClaw：仅承接 `author agent` / `review agent`
- 交互模型：创建群创建需求，author 私聊构造，项目群同步状态与结果
- 发布流程：遵循 `harness-scaffold` 的 `CI -> Staging -> Customer Deploy`

## 2. 当前进度判断

当前已经具备：

- v1.2 目标架构与交互模型文档
- Bitable 字段与状态机设计
- author/reviewer/coordinator 契约
- OpenClaw session 与多需求上下文策略
- 本地 `CoordinatorService` 原型
- 创建群创建需求与 author 私聊启动协议的本地骨架
- `harness-scaffold` 风格的 `services/coordinator-service` 服务目录
- 基于飞书官方 Python SDK `lark_oapi` 的长连接接入骨架
- Docker / compose / GitHub Actions 部署骨架
- 飞书消息发送、项目群创建、Bitable 建记录、文档创建的 SDK 封装骨架
- 与 `harness-scaffold` 对齐的 `ci.yml`、`staging.yml`、`deploy.yml`

当前尚未具备：

- 真实 Bitable 持久化
- 真实正式文档 section rewrite 写回
- 真实 OpenClaw author/reviewer 调用
- 项目群自动创建与映射持久化
- 幂等、权限、错误恢复机制

## 3. 进入测试环境联调的门槛

满足以下条件后，可以进入测试环境部署：

### 3.1 CoordinatorService 真实入口

- 长连接服务已部署并成功连接飞书
- 能接收飞书创建群消息事件
- 能接收 author 私聊消息事件
- 能识别并校验 `req_id`
- 能把事件映射到状态机

### 3.2 真实持久化

- Bitable 新字段已创建
- `req_id` 与用户、群、私聊 chat 的映射可持久化
- active req 绑定可恢复

### 3.3 OpenClaw 调用

- Coordinator Service 能向 author/reviewer 提交单轮上下文包
- 能稳定收到结构化结果

### 3.4 正式文档写回

- 能创建正式需求文档
- 能按 section rewrite 更新文档
- 不再 append 聊天摘要

## 4. 正式部署前还差的能力

### P0 必须完成

- 飞书事件订阅接入
- Bitable 字段升级
- 正式文档真实写回
- OpenClaw author/reviewer 调用链
- 项目群映射与私聊绑定持久化
- 幂等控制
- 权限校验

### P1 强烈建议完成

- 超时催办
- 错误重试
- 操作审计日志
- review 结果同步到项目群
- 人工确认按钮或明确的确认命令

### P2 可后补

- 项目群自动创建的完善治理
- 更友好的消息卡片
- 表单辅助入口
- 更细粒度的运营看板

## 5. 你需要提供的部署资源

## 5.1 Coordinator Service 运行环境

至少需要：

- 一台可常驻运行的主机
- 能运行 Python 服务或 Docker
- 可保存配置与日志

当前实现优先走飞书事件长连接方案，因此：

- 不强依赖公网回调 URL
- 不强依赖额外开放入站端口
- 健康检查端口仅供容器/主机自检

建议你提供：

- 主机地址：`47.251.81.45`
- 登录方式：`admin@47.251.81.45`
- 运行目录
- Python 版本
- 是否有反向代理/Nginx
- 是否已有域名或公网入口

## 5.2 飞书应用资源

需要提供：

- 飞书自建应用的 `App ID`
- `App Secret`
- 事件订阅配置入口
- 机器人可入群
- 能发送消息

当前已提供：

- `App ID`：已提供
- `App Secret`：已提供

说明：

- 本文档不重复明文记录敏感密钥
- 后续部署时通过服务端环境变量注入

## 5.3 飞书业务资源

需要提供或确认：

- 固定“需求创建群”
- 每项目一个“项目群”的策略
- 需求文档模板
- 审查报告模板
- 生命周期 Bitable

如果项目群尚未存在，需要确认：

- 是否允许由 Coordinator Service 自动创建项目群

当前状态：

- 需求创建群：已建立，后续联调时由服务自动识别或写入配置
- 生命周期 Bitable：已存在，可从现网配置复用
- 模板资源：已存在，可从现网配置复用

补充说明：

- `FEISHU_CREATION_GROUP_CHAT_ID` 可以在第一轮真实群消息联调时由服务自动观察并记录
- 因此创建群已建立后，不要求先在飞书 UI 中手工获取群 ID

## 5.4 OpenClaw 运行环境

需要提供：

- 现有 OpenClaw 实例可访问方式
- author/reviewer 对应 agent 标识
- 是否允许 Coordinator Service 通过内部接口调用 OpenClaw
- 如果有 API / CLI / webhook 调用方式，也需要一起确认

当前已确认：

- OpenClaw 实例：`admin@47.251.81.45`
- 可复用 agent：
  - `ai-founder-brief`
  - `ai-meeting-closeout`
  - `ai-ops-router`（建议降级为运维/兜底角色）

## 5.5 持久化资源

第一阶段最少需要一个稳定持久化方案来保存：

- `req_id -> creator_user_id`
- `req_id -> project_group_id`
- `req_id -> author_dm_chat_id`
- `user_id -> active_req_id`
- 当前轮次与门禁状态

建议方案：

- 第一阶段：Bitable + 本地小型持久化
- 更稳妥：Bitable + 独立数据库

如果你能提供数据库，建议同时告知：

- 类型（SQLite / PostgreSQL / MySQL）
- 连接方式
- 是否允许我直接建表

## 6. 需要的飞书权限清单

Coordinator Service 至少需要：

- 接收事件订阅
- 读取群消息或消息事件
- 发送群消息
- 发送私聊消息
- 获取会话信息
- 创建群或管理群（如果项目群自动创建）
- 文档创建
- 文档读取
- 文档更新
- 多维表格读取
- 多维表格写入
- 字段创建
- 字段更新
- `offline_access`

如果需要消息卡片交互，还需要：

- 交互式卡片回调能力

## 7. 需要的 OpenClaw 能力清单

OpenClaw author/reviewer 侧需要：

- author agent 可被稳定调用
- review agent 可被稳定调用
- 输入支持结构化上下文包
- 输出能稳定返回结构化结果

建议：

- 不让 OpenClaw 负责真相源
- 不让 OpenClaw 负责群级主编排
- 仅让它负责单轮推理与私聊表面

## 8. 联调顺序

建议按下面顺序推进，最快：

### Step 1：部署 Coordinator Service 基础服务

- 起服务
- 配配置
- 打日志
- 健康检查
- 建立飞书长连接

当前建议：

- staging 使用 `8004`
- customer/prod 默认使用 `8003`

这样可以避免与线上已存在的：

- `harness-scaffold-app-1` (`8001`)
- `checkpoint-handler` (`8002`)

发生端口冲突。

### Step 2：接飞书创建群消息事件

- 在创建群 `@CoordinatorService`
- 成功创建 REQ
- 成功写 Bitable
- 成功返回 author 私聊启动命令

### Step 3：接 author 私聊启动

- 用户发送 `开始需求构造 REQ-ID`
- 成功绑定 `active_req_id`
- 成功完成“确认开始”协议

### Step 4：打通正式文档写回

- 创建正式需求文档
- 按 section rewrite 更新

### Step 5：打通 OpenClaw author/reviewer

- author 返回结构化草稿
- reviewer 返回 review 结果
- Coordinator Service 更新状态机

### Step 6：同步到项目群

- 项目群看到需求创建结果
- review / 审查状态同步
- 最终通过结果同步

## 9. 我建议你优先准备的信息

为了让我最快进入“可部署实现”，你优先给我这些：

1. Coordinator Service 部署主机信息
2. 飞书应用 `App ID / Secret`
3. 需求创建群 ID 或可用群
4. 当前 Bitable 与模板资源
5. OpenClaw author/reviewer 的可调用方式

## 10. 结论

现在已经到了“可以开始部署准备并很快进入测试环境联调”的阶段。

离正式部署还差的核心能力主要集中在四块：

- 真实飞书入口
- 真实持久化
- 真实文档写回
- 真实 OpenClaw 调用

你一旦提供部署资源，我这边就可以按照本文档的联调顺序继续往前推。
