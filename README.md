# requirement-workflow-feishu

## 目录

- `docs/context`
  - 方法论、环境与全景上下文
- `docs/plans`
  - 工作目标确认稿与实施拆解
- `docs/specs`
  - v1.2 设计、Bitable 字段、状态机、agent 契约、文档 rewrite 规则、OpenClaw session/交互策略
- `services/coordinator-service`
  - 按 `harness-scaffold` 形态组织的可部署飞书协调服务
- `docker`
  - 部署编排文件
- `.github/workflows`
  - 对齐 `harness-scaffold` 的 `CI -> Staging -> Deploy` 工作流
- `src/requirement_workflow_v12`
  - 可复用的需求工作流核心、状态机、存储与运行时适配层

## 当前阶段

当前仓库已完成 v1.2 的设计收敛，架构边界已经更新为：

- `Coordinator Service`：独立飞书应用后台，负责事件监听、状态机、Bitable、正式文档写回
- OpenClaw：只承接 `author agent` 与 `review agent` 两类智能能力
- 交互模型：创建群创建需求，author 私聊构造，项目群同步状态与结果

当前实现已经开始向 `harness-scaffold` 模版对齐：

- 服务入口使用飞书官方 Python SDK `lark_oapi`
- 采用长连接事件订阅模式监听飞书消息事件
- 服务配置全部收敛到环境变量 / 配置对象
- 部署路径按 `Docker + GitHub Actions + customer deploy` 标准流组织

注意：

- 仓库内不保存真实飞书凭据
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 必须由部署环境注入有效值
- 业务侧 Feishu API 现已优先支持 `FEISHU_USER_ACCESS_TOKEN`（UAT）模式
- `FEISHU_CREATION_GROUP_CHAT_ID` 可在第一条真实群消息联调时自动识别

## 运行骨架

- 长连接入口：`services/coordinator-service/main.py`
- 运行时编排：`src/requirement_workflow_v12/service_app.py`
- 核心规则引擎：`src/requirement_workflow_v12/coordinator_service.py`
- 本地状态存储：`src/requirement_workflow_v12/store.py`

## 标准发布流

- `ci.yml`：PR 校验
- `staging.yml`：`main` 分支构建镜像并部署到 staging
- `deploy.yml`：按 customer 配置做正式部署
- `sync-bitable-schema.yml`：按 v1.2 规范自动补齐当前 Bitable 字段

当前不再把 `coordinator-service` 走单独的旁路部署流，而是回到 `harness-scaffold` 标准 git 驱动发布方式。

## 当前能力

- 监听飞书文本消息事件
- 在需求创建群解析 `创建需求` 指令
- 在配置齐全时尝试自动创建项目需求群
- 在配置齐全时尝试创建 Bitable 记录
- 在配置齐全时尝试创建正式需求文档
- 在配置齐全时按稳定 section 结构重写正式需求文档
- 生成 `REQ-{PROJECT}-{NNN}` 并建立私聊启动指令
- 若未预置 `FEISHU_CREATION_GROUP_CHAT_ID`，可从第一条创建需求群消息自动识别创建群
- 在 author 私聊中处理：
  - `开始需求构造 REQ-ID`
  - `确认开始`
  - `切换需求 REQ-ID`
- 在 author 私聊中按当前讨论字段推进多轮需求构造
- 每轮补充后自动执行规则化 review，并决定继续讨论还是进入人工确认
- 在人工确认阶段处理：
  - `确认需求`
  - `继续修改`
- 通过本地 JSON 快照恢复运行状态

下一步将继续补齐：

- OpenClaw author / reviewer 的真实结构化调用接入
- 基于新仓库的正式 CI/CD 部署
