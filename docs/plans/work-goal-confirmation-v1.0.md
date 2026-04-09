# 需求构造工作流改造 - 工作目标确认稿

## 1. 背景

当前 OpenClaw + 飞书需求层已经验证通过最小闭环：

- 创建需求
- 生成 REQ ID
- 创建需求文档
- 写入 Bitable
- 进入讨论
- 进入审查
- 推进到 `REQ_APPROVED`

但现状仍存在两个关键问题：

1. `开始讨论` 只会执行一次，缺少显式会话状态与多轮推进能力。
2. 讨论后的需求文档只是 append 聊天内容，没有形成可直接用于后续规格层的正式需求文档。

这说明当前方案完成的是“流程演示”，还不是“可用的需求构造系统”。

## 2. 本次改造目标

将现有最小闭环升级为真正可用的“需求构造工作流 v1.2”，使需求讨论从形式化填表升级为：

- 由 `author agent` 显式接手
- 通过复合 skill 引导人类完成有思路、有细节、有质量的需求方案
- 每一轮构造后自动调用 `review agent` 做质量检查
- 只有 `AI Ready + Human Confirmed` 同时满足才允许流转
- 正式需求文档采用 section rewrite，禁止 append 聊天记录
- `Coordinator Service` 作为规则优先的独立后台服务，与飞书 Workflow / Automation 协同编排

## 3. 第一阶段边界

第一阶段只覆盖需求层闭环，止步到 `REQ_APPROVED`：

- 包含：需求创建、需求构造、每轮 review、人工确认、正式审查、批准流转
- 包含：飞书工作流/自动化与 `Coordinator Service` 的编排分层
- 包含：Bitable 讨论态字段扩展
- 包含：正式需求文档结构化写回
- 包含：创建群 / author 私聊 / 项目群 的交互协议
- 不包含：Spec 自动生成
- 不包含：Harness 自动生成
- 不包含：GitHub PR/CI/Staging 的自动联动
- UI 设计步骤保留接口和状态位，但不是第一优先实现对象

## 4. 核心判断

### 4.1 Coordinator Service 应规则化

`Coordinator Service` 不再承担高质量需求写作，而是作为规则优先的独立后台服务，只负责：

- 创建 REQ
- 更新 Bitable
- 维护 owner
- 维护当前阶段 / 当前轮次 / 当前讨论字段
- 调用 author / reviewer
- 把结果正式写回文档
- 监听事件并推动状态机流转

它不是深度思考的主角，而是稳定的流程执行器。

### 4.2 需求构造必须由 author agent 显式接手

需求讨论不应继续退化为“7 字段填空”，而应由 `author agent` 驱动复合 skill：

- 澄清问题本质
- 拆分使用场景
- 强化边界约束
- 推动验收标准量化
- 形成高质量需求方案

### 4.3 review 必须前移到每轮

`review agent` 不再只在阶段末尾统一审查，而是在每轮 author 输出后立即执行一轮 review，给出：

- 已扎实内容
- 缺失项
- 弱项
- 矛盾点
- 不可验证的 AC
- 是否达到 AI Ready

### 4.4 交互入口要清晰分层，角色接手必须显式可见

第一阶段采用三段式交互模型：

- 创建入口：固定“需求创建群”，由用户 `@CoordinatorService` 创建需求
- 构造入口：用户与 `author agent` 私聊，显式带上 `req_id` 启动需求构造
- 同步入口：每个项目一个项目群，用于状态同步、审查通知与结果广播

系统必须明确声明：

- 当前由谁接手
- 当前对应哪个 `req_id`
- 当前轮次是什么
- review 结论是什么
- 下一步动作是什么

这样既避免后台黑盒转发，也避免用户直接在群里和多个 agent 混聊。

## 5. 目标架构

### 第一层：Feishu Workflow / Automation

负责：

- 触发器
- 条件分支
- 通知
- 调 HTTP / Webhook
- 基础状态推进
- 超时催办

### 第二层：Coordinator Service

负责：

- 规则化流程执行
- Bitable 状态机更新
- owner 切换
- 轮次状态持久化
- 正式文档写回
- 调 author / reviewer
- 管理创建群、项目群与 `req_id` 的映射

### 第三层：Author / Reviewer Agents

`author agent`：

- 显式接手需求构造
- 通过私聊与用户进行逐轮共创
- 引导人类逐轮澄清需求
- 形成结构化需求草稿

`review agent`：

- 每轮 review 当前草稿质量
- 判断是否继续打磨
- 判断是否达到 AI Ready

## 6. 第一阶段目标状态机

```text
CREATED
-> DISCUSSION_ROUTING
-> DISCUSSING
-> AI_REVIEWING
-> HUMAN_CONFIRMING
-> REVIEWING
-> REQ_APPROVED
```

说明：

- `DISCUSSION_ROUTING`：Coordinator Service 创建 REQ 并完成 author 接手准备
- `DISCUSSING`：author 进行当前轮需求构造
- `AI_REVIEWING`：review agent 审当前轮草稿
- `HUMAN_CONFIRMING`：AI 认为已达到门槛，等待人工确认
- `REVIEWING`：进入正式需求审查阶段
- `REQ_APPROVED`：需求层完成

## 7. 第一阶段必须落地的能力

### 7.1 Bitable 讨论态字段

建议新增：

- `当前阶段`
- `当前轮次`
- `当前讨论字段`
- `已完成字段`
- `待补字段`
- `当前owner`
- `当前接手角色`
- `最近一次review结论`
- `AI Ready`
- `Human Confirmed`
- `最近一次提问`
- `最近一次写回时间`

### 7.2 正式文档 section rewrite

正式需求文档必须：

- 保持稳定 section 结构
- 读取整篇文档后按 section 定位替换
- 禁止把聊天摘要 append 到文档末尾
- 将聊天过程与正式文档产物分离

### 7.3 每轮 review 回路

每轮交互闭环应为：

```text
author 写一轮
-> Coordinator Service 写回正式草稿
-> review agent 审一轮
-> 若未达标则继续讨论
-> 若达标则等待人工确认
```

### 7.4 双门禁流转

只有同时满足：

- `AI Ready = true`
- `Human Confirmed = true`

流程才允许从需求构造阶段进入正式审查。

## 8. 本轮交付顺序

1. 输出工作目标确认稿
2. 输出实现级设计稿
3. 基于设计稿进入代码与配置实现
4. 联调飞书工作流 / Bitable / agent 配置
5. 验证从创建需求到 `REQ_APPROVED` 的新闭环

## 9. 成功标准

如果第一阶段改造完成，应满足：

- 需求讨论不再只执行一次
- 每轮讨论状态可恢复、可追踪
- 正式文档不再 append 聊天记录
- author / reviewer 分工清晰
- Coordinator Service 成为稳定的规则化后台
- 飞书 Workflow / Automation 与 Coordinator Service 分层清晰
- 需求层在 `REQ_APPROVED` 前形成真正可用的结构化需求产物
