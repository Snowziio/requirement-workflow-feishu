# 当前环境上下文

本次开发最终目标：在新的项目里落地三层架构方案，形成一套可执行的上下文文档包，支持从现有 OpenClaw/飞书环境无缝启动实现工作。

本文档记录当前已经存在且可复用的部署环境、飞书资源、角色分工和已验证能力，供新项目直接继承。

## 1. OpenClaw 部署环境

- OpenClaw 机器：`admin@47.251.81.45`
- OpenClaw 服务：`openclaw-gateway.service`
- 运行要求：配置修改后统一使用进程重启，不使用热更新

## 2. 当前飞书资源

### Bitable

- 名称：`OpenClaw 项目生命周期表`
- URL：`https://my.feishu.cn/base/RGBbbeTPTafgtCsrm89cxP9Mncg`
- `app_token`：`RGBbbeTPTafgtCsrm89cxP9Mncg`
- `table_id`：`tbl0npgebbogMaT1`

### 模板文档

- 需求文档模板：`https://www.feishu.cn/docx/J3WxdaBAYo1nT1x3QrccLVBVnEf`
- UI 设计简报模板：`https://www.feishu.cn/docx/C71Qdjh8lo3G4IxUfhqcq8GdnIc`
- 需求审查报告模板：`https://www.feishu.cn/docx/UdDLdJOvTo7SUhxx4tAcheeKnGe`

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
- `DISCUSSING`
- `UI_DESIGNING`
- `REVIEWING`
- `REQ_APPROVED`
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

- 当前讨论阶段缺少显式持久化会话状态
- 当前文档写回容易退化成 append，而不是按 section rewrite
- `创建时间` 的确定性写入尚未形成稳定实现

## 4. 现有角色与分工

新项目中只保留“角色”，不固化现场机器人实例名。

### 规则/编排层

- `coordinator service`
  - 创建 REQ
  - 更新 Bitable
  - 维护 owner
  - 维护当前阶段/当前轮次/当前讨论字段
  - 调 author/reviewer
  - 把结果写回正式文档

### 内容构造层

- `author agent`
  - 显式接手需求构造
  - 通过复合 skill 引导用户逐轮澄清
  - 产出结构化需求草稿

### 质量把关层

- `review agent`
  - 每轮审当前草稿质量
  - 标出缺失、矛盾、模糊点和不可验证项
  - 决定是否继续打磨

## 5. 已验证能力

已跑通的最小闭环包括：

1. 在飞书群里创建需求
2. 生成 REQ ID
3. 创建需求文档
4. 写入 Bitable
5. `CREATED -> DISCUSSING`
6. 进入审查并生成审查报告
7. 通过 @mention fallback 推进到 `REQ_APPROVED`

## 6. 不应直接继承的旧方案

以下设计属于过渡形态，不应作为新项目目标：

- 主协调能力与深度需求写作耦合在同一个 agent 中
- 需求讨论仅靠 7 字段补全
- 每轮讨论结果直接 append 到飞书文档末尾
- 把项目专属逻辑塞进共享模板基础设施

## 7. 参考材料

- [现场验证记录](/Users/daxin/work/requirement-workflow-scaffold/docs/reference/validated-run-20260409.md)
- [飞书/OpenClaw 设置记录](/Users/daxin/work/requirement-workflow-scaffold/docs/reference/feishu-openclaw-setup-20260409.md)
- [HARNESS 实例配置](/Users/daxin/work/requirement-workflow-scaffold/docs/reference/harness-instance/feishu_project_space.harness.json)
