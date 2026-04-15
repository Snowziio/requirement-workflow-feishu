> ⚠️ **已归档 — 请勿再更新或引用**（2026-04-15）
>
> 本文件已废弃。其信息已按下述方式分散到现行文档：
>
> - **远端主机、服务端口、Bitable token、OpenClaw Agent 部署** → `docs/context/remote-deploy-env-snapshot-20260413.md`（含历史警告 §8）
> - **Bitable 字段清单与状态机** → `docs/context/layers/requirement-layer.md`
> - **Agent 角色与分工** → `docs/agents/*/SKILL.md` 与方法论 §4.1
> - **方法论适用范围与当前阶段目标** → `docs/context/harness-engineering-methodology-v2.0.md`（§1.0、§六 Pre-Phase-2）
>
> 保留本文件仅用于追溯早期三层架构的设计意图，内容不再维护。

# 当前环境上下文 [ARCHIVED]

本次开发最终目标：在新的项目里落地三层架构方案，形成一套可执行的上下文文档包，支持从现有 OpenClaw/飞书环境无缝启动实现工作。

本文档记录当前已经存在且可复用的部署环境、飞书资源、角色分工和已验证能力，供新项目直接继承。

## 1. OpenClaw 部署环境

- OpenClaw 主机：`<openclaw-host>`
- OpenClaw 服务：`<openclaw-service>`
- 运行要求：配置修改后统一使用进程重启，不使用热更新

## 2. 当前飞书资源

### Bitable

- 名称：`<bitable-name>`
- URL：`<bitable-url>`
- `app_token`：`<bitable-app-token>`
- `table_id`：`<bitable-table-id>`

### 模板文档

- 需求文档模板：`<requirement-doc-template-url>`
- UI 设计简报模板：`<ui-brief-template-url>`
- 需求审查报告模板：`<review-report-template-url>`

## 3. Bitable 设计现状

当前表采用“全生命周期 Bitable”，已建立需求层及后续阶段预留字段。

### 已有主要字段

- `req_id`
- `名称`
- `项目`
- `状态`
- `创建人`
- `创建时间`
- `当前负责人`
- `需求文档`
- `UI设计稿`
- `审查报告`
- `需求版本`
- `历史版本链接`
- `Spec版本`
- `Spec PR`
- `Harness PR`
- `Impl PR`
- `当前卡点`
- `卡点1a时间`
- `卡点1b时间`
- `卡点2时间`
- `卡点3时间`
- `备注`

### 已配置单选值

`状态`：

- `CREATED`
- `DRAFTING`
- `AI_REVIEW`
- `HUMAN_CONFIRM`
- `FINAL_REVIEW`
- `APPROVED`
- `SPEC_DRAFTING`
- `SPEC_LOCKED`
- `HARNESS_GENERATING`
- `HARNESS_READY`
- `IMPLEMENTING`
- `CI_PENDING`
- `STAGING`
- `DEPLOYED`

`当前卡点`：

- `无`
- `1a`
- `1b`
- `2`
- `3`

### 已知问题

- 远端 author / reviewer 模板仍需持续校验，避免旧事件名或旧状态名回流
- Bitable 线上旧记录需要执行状态值迁移，统一到简化后的 5 态
- `创建时间` 的确定性写入尚未形成稳定实现

## 4. 现有角色与分工

新项目中只保留“角色”，不固化现场机器人实例名。

### 规则/编排层

- `coordinator service`
  - 创建 REQ
  - 更新 Bitable
  - 维护 owner
  - 维护当前阶段/当前轮次
  - 接收 author/reviewer 流程事件
  - 推动工作流状态流转
  - 发送状态流转通知

### 内容构造层

- `author agent`
  - 显式接手需求构造
  - 与需求提出者多轮沟通并持续撰写需求文档
  - 在文档达到门槛后上报 `author_submit`

### 质量把关层

- `review agent`
  - 每轮审当前草稿质量
  - 标出缺失、矛盾、模糊点和不可验证项
  - 只上报 `ai_review_reject` / `ai_review_pass`

## 5. 已验证能力

已跑通的最小闭环包括：

1. 在飞书群里创建需求
2. 生成 REQ ID
3. 创建需求文档
4. 写入 Bitable
5. `CREATED -> DRAFTING`
6. `DRAFTING -> AI_REVIEW`
7. reviewer 读取上下文并上报审查结论
8. Coordinator 根据事件推进到 `DRAFTING` 或 `HUMAN_CONFIRM`

## 6. 不应直接继承的旧方案

以下设计属于过渡形态，不应作为新项目目标：

- 主协调能力与深度需求写作耦合在同一个 agent 中
- 让 Coordinator 参与需求文档正文编写
- reviewer 直接推进人工确认或正式审查
- 把项目专属逻辑塞进共享模板基础设施

## 7. 参考材料

- `docs/reference/validated-run-20260409.md`
- [飞书/OpenClaw 设置记录](/Users/daxin/work/requirement-workflow-scaffold/docs/reference/feishu-openclaw-setup-20260409.md)
- [HARNESS 实例配置](/Users/daxin/work/requirement-workflow-scaffold/docs/reference/harness-instance/feishu_project_space.harness.json)
