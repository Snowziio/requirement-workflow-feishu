# requirement-workflow-feishu

## 目录

- `docs/context`
  - 方法论、环境与全景上下文
- `docs/plans`
  - 工作目标确认稿与实施拆解
- `docs/specs`
  - v1.2 设计、Bitable 字段、状态机、agent 契约、callback 契约、上下文查询契约、callback 请求模板、文档 rewrite 规则、OpenClaw session/交互策略
- `services/coordinator-service`
  - 按 `harness-scaffold` 形态组织的可部署飞书协调服务
- `docker`
  - 部署编排文件
- `.github/workflows`
  - 对齐 `harness-scaffold` 的 `CI -> Staging -> Deploy` 工作流
- `src/requirement_workflow_v12`
  - 可复用的需求工作流核心、状态机、存储与运行时适配层

## 当前阶段

本仓库是 **Harness Engineering 方法论 v1.3 的首个参考实现**，架构边界：

- `Coordinator Service`：独立飞书应用后台，负责事件监听、状态机、Bitable、工作流卡点与通知
- OpenClaw：只承接 `author agent` 与 `review agent` 两类智能能力
- 交互模型：创建群创建需求，author 私聊构造，项目群同步状态与结果

当前实现已按 `harness-scaffold` 方向收敛：

- 服务入口使用飞书官方 Python SDK `lark_oapi`
- 采用长连接事件订阅模式监听飞书消息事件
- 服务配置全部收敛到环境变量 / 配置对象
- 部署路径按 `Docker + GitHub Actions + customer deploy` 标准流组织

注意：

- 仓库内不保存真实飞书凭据
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 必须由部署环境注入有效值
- `FEISHU_CREATION_GROUP_CHAT_ID` 可在第一条真实群消息联调时自动识别

## 运行骨架

- 长连接入口：`services/coordinator-service/main.py`
- 运行时编排：`src/requirement_workflow_v12/service_app.py`
- 核心规则引擎：`src/requirement_workflow_v12/coordinator_service.py`
- 本地状态存储：`src/requirement_workflow_v12/store.py`
- OpenClaw callback helper：`scripts/send_openclaw_callback.py`
- OpenClaw smoke test：`scripts/run_openclaw_smoke.py`

## 标准发布流

- `ci.yml`：PR 校验
- `staging.yml`：`main` 分支构建镜像并部署到 staging
- `deploy.yml`：按 customer 配置做正式部署
- `bootstrap-bitable-app.yml`：创建新的 Bitable app 与 Requirements 表
- `sync-bitable-schema.yml`：按 v1.3 规范自动补齐当前 Bitable 字段

当前不再把 `coordinator-service` 走单独的旁路部署流，而是回到 `harness-scaffold` 标准 git 驱动发布方式。

## 当前已实现

- 监听飞书文本消息事件
- 在需求创建群接收 `@CoordinatorService 创建需求` 并返回结构化创建卡片
- 支持卡片回调 `POST /callbacks/card`，由表单提交后再正式创建需求
- 在配置齐全时尝试自动创建项目需求群
- 在配置齐全时尝试创建 Bitable 记录
- 在配置齐全时可记录需求文档链接，但不参与正文撰写
- 生成 `REQ-{PROJECT}-{NNN}` 并建立私聊启动指令
- 在项目群发送需求创建卡片，展示需求文档/多维表格链接和“开始需求构造”入口
- 若未预置 `FEISHU_CREATION_GROUP_CHAT_ID`，可从第一条创建需求群消息自动识别创建群
- 提供给 OpenClaw skill / agent 的结果上报接口：
  - `POST /callbacks/openclaw/author-turn`
  - `POST /callbacks/openclaw/review-result`
- 若配置 `OPENCLAW_CALLBACK_SECRET`，上述接口要求携带：
  - `X-OpenClaw-Timestamp`
  - `X-OpenClaw-Signature`
- 签名算法：`hex(hmac_sha256(secret, timestamp + "." + raw_body))`
- `Coordinator Service` 在收到上报后负责：
  - 推进状态机
  - 更新 Bitable 与工作流状态
  - 输出人工确认 / 正式审查所需状态
- 在 author 私聊中处理：
  - `开始需求构造 REQ-ID`
  - `确认开始`
  - `切换需求 REQ-ID`
  - `查看状态`
- 上述私聊入口当前仍保留用于兼容联调，但不再是推荐的长期主路径
- 当前推荐主路径是：agent 私聊完成文档构造/审查，再通过 callback 仅上报流程事件
- 在人工确认阶段处理：
  - `确认需求`
  - `继续修改`
- 在正式审查阶段处理：
  - `确认通过`
  - `需要修改`
- 通过本地 JSON 快照恢复运行状态

## 仍待补齐

- OpenClaw author / reviewer skill 的真实 callback 联调
- 更完整的正式审查记录与卡片化交互
- 将卡片回调地址与飞书应用配置联通，并补上直接跳转需求构造助手的 deeplink

## 联调参考

- callback 契约：
  [openclaw-callback-contracts-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/openclaw-callback-contracts-v1.2.md)
- 上下文查询契约：
  [openclaw-context-query-contract-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/openclaw-context-query-contract-v1.2.md)
- callback 请求模板与命令示例：
  [openclaw-callback-request-examples-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/openclaw-callback-request-examples-v1.2.md)
- OpenClaw skill 实现指引：
  [openclaw-skill-implementation-guide-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/openclaw-skill-implementation-guide-v1.2.md)
- 本地联调脚本：
  [send_openclaw_callback.py](/Users/daxin/work/requirement-workflow-feishu/scripts/send_openclaw_callback.py)
- 最小闭环 smoke 脚本：
  [run_openclaw_smoke.py](/Users/daxin/work/requirement-workflow-feishu/scripts/run_openclaw_smoke.py)

## Bitable Schema 约定

- Bitable 字段的唯一真相源是 [bitable_schema_v12.json](/Users/daxin/work/requirement-workflow-feishu/bitable_schema_v12.json)
- Coordinator 的写入字段映射由 [bitable_schema.py](/Users/daxin/work/requirement-workflow-feishu/src/requirement_workflow_v12/bitable_schema.py) 从 schema 派生
- 建表与补字段脚本统一读取同一份 schema：
  - [bootstrap_bitable_app_v12.py](/Users/daxin/work/requirement-workflow-feishu/scripts/bootstrap_bitable_app_v12.py)
  - [sync_bitable_schema_v12.py](/Users/daxin/work/requirement-workflow-feishu/scripts/sync_bitable_schema_v12.py)
- 给 author / reviewer 使用的只读字段契约由脚本导出，不手写维护：
  - [export_agent_bitable_contract_v12.py](/Users/daxin/work/requirement-workflow-feishu/scripts/export_agent_bitable_contract_v12.py)
  - 产物：[bitable-agent-readable-fields-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/bitable-agent-readable-fields-v1.2.md)

## 修改 Bitable 字段的标准步骤

1. 先修改 [bitable_schema_v12.json](/Users/daxin/work/requirement-workflow-feishu/bitable_schema_v12.json)
2. 执行 `python3 scripts/export_agent_bitable_contract_v12.py`
3. 执行 `python3 -m unittest discover -s tests -v`
4. 如果需要创建或补齐线上字段，执行 schema sync 工作流或运行 [sync_bitable_schema_v12.py](/Users/daxin/work/requirement-workflow-feishu/scripts/sync_bitable_schema_v12.py)
5. 同步远端 author / reviewer 模板，确保它们只引用 [bitable-agent-readable-fields-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/bitable-agent-readable-fields-v1.2.md) 中定义的字段

禁止事项：

- 不要只改 `FeishuGateway._record_fields()` 而不改 schema
- 不要只改 Bitable 线上表结构而不回写 schema
- 不要在 agent 的 `SKILL.md` / `TOOLS.md` 中手写新的 Bitable 字段名而不先更新 schema
