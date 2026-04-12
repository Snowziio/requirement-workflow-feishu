# 需求构造工作流 v1.2 - 实现设计稿

## 1. 设计目标

本设计用于将当前“需求层最小闭环”升级为“可多轮构造、可持续 review、可结构化写回”的需求构造工作流。

本设计只覆盖需求层，止步到 `APPROVED`。

## 2. 设计原则

### 2.1 编排与认知分离

- 编排稳定性由 Workflow + Coordinator Service 保证
- 内容质量由 Author + Reviewer 保证

### 2.2 正式文档与聊天过程分离

- 聊天是交互过程
- 正式文档由 author agent 驱动撰写与维护

### 2.3 重要状态必须持久化

不能仅依赖 prompt 和记忆判断当前讨论进度，必须显式持久化会话状态。

### 2.4 流转必须受双门禁保护

没有 `AI Ready` 和 `Human Confirmed` 双重满足，不允许进入正式审查。

## 3. 角色职责

### 3.1 Feishu Workflow / Automation

适合承载：

- 新建记录触发
- 状态变更触发
- owner 切换通知
- 审查准备完成提醒
- 轮次超时催办
- 调 HTTP / Webhook

不适合承载：

- 深度需求构造
- 多轮需求推理
- 复杂质量判断
- 正式文档编译

### 3.2 Coordinator Service

定位：

- 独立飞书应用后台服务
- 规则优先的流程执行器

职责：

- 创建 `REQ-{PROJECT}-{NNN}`
- 监听需求创建群中的 `@CoordinatorService` 创建消息
- 监听飞书事件、Webhook 和卡片回调
- 维护 Bitable 记录
- 维护状态机
- 维护当前轮次与当前讨论字段
- 接收 author / reviewer 的流程事件
- 宣布当前接手角色
- 管理创建群、项目群、私聊会话与 `req_id` 的映射
- 对外提供可审计的状态推进

约束：

- 尽量不用自由生成决定关键状态变更
- 所有关键写入必须幂等
- 非法状态切换必须被拒绝

### 3.3 Author Agent

职责：

- 显式接手需求构造
- 在与用户的私聊中完成逐轮引导
- 使用复合 skill 引导用户逐轮澄清需求
- 将自然语言讨论归一化为结构化草稿
- 给出未决问题与下一轮提问

关注点：

- 澄清问题本质
- 拆场景
- 明确输入输出
- 约束边界
- 推动 AC 量化

### 3.4 Review Agent

职责：

- 每轮检查当前草稿质量
- 给出缺失、模糊、矛盾、不可验证项
- 判断是否达到 `AI Ready`
- 提供下一轮聚焦建议

## 4. 推荐状态机

```text
CREATED
-> DRAFTING
-> AI_REVIEW
-> HUMAN_CONFIRM
-> FINAL_REVIEW
-> APPROVED
```

### 4.1 状态定义

- `CREATED`
  - 刚创建记录，尚未进入需求构造

- `DRAFTING`
  - author 与用户进行当前轮需求构造

- `AI_REVIEW`
  - reviewer 对当前轮草稿进行审查

- `HUMAN_CONFIRM`
  - AI 已达门槛，等待人工确认是否准确表达意图

- `FINAL_REVIEW`
  - 进入正式需求审查阶段

- `APPROVED`
  - 需求层完成

### 4.2 核心流转规则

- `CREATED -> DRAFTING`
  - 创建 REQ 后直接进入需求构造

- `DRAFTING -> AI_REVIEW`
  - 当前轮草稿写回后自动触发

- `AI_REVIEW -> DRAFTING`
  - review 不通过，继续打磨

- `AI_REVIEW -> HUMAN_CONFIRM`
  - review 通过，等待人工确认

- `HUMAN_CONFIRM -> DRAFTING`
  - 人工不满意，退回继续打磨

- `HUMAN_CONFIRM -> FINAL_REVIEW`
  - 人工确认满意，进入正式审查

- `FINAL_REVIEW -> APPROVED`
  - 正式审查通过

## 5. Bitable 字段设计

## 5.1 保留现有字段

继续保留已落地的 22 个生命周期字段。

## 5.2 新增字段

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

## 5.3 字段用途

- `当前轮次`
  - 记录当前是第几轮构造

- `当前讨论字段`
  - 标明当前聚焦主题，支持会话恢复

- `已完成字段` / `待补字段`
  - 支持完整度重算与状态查询

- `AI Ready`
  - reviewer 是否认为已达到可流转门槛

- `Human Confirmed`
  - 人工是否确认当前内容准确

- `最近一次review结论`
  - 给 Workflow / 通知 / 看板提供直接观测面

## 6. 文档编译与写回规则

## 6.1 正式文档结构

正式需求文档应至少包含：

- 问题描述
- 使用场景
- 输入
- 输出
- 边界
- 验收标准
- 非功能要求

必要时可增加：

- 需求概览
- 历史约束摘要
- 当前 review 摘要

## 6.2 文档边界原则

- 正式文档由 author agent 维护
- Coordinator Service 只记录文档链接，不改写正文
- review agent 负责给 author 反馈修改意见，不直接推进状态机

## 6.3 建议实现方式

将流程事件上报逻辑单独收敛为 callback 契约：

- author 上报“可进入 AI review”
- review 上报“退回修改 / 进入人工确认”
- Coordinator Service 仅消费事件并更新 Bitable / 状态机

这样可以避免 Coordinator 重新介入需求文档撰写。

## 7. 每轮交互闭环

推荐闭环：

```text
用户在 author 私聊中输入
-> author 完成需求文档撰写
-> author 通知 Coordinator 进入 AI review
-> reviewer 与需求提出者完成审查循环
-> reviewer 通知 Coordinator 流转状态
-> Coordinator 更新 Bitable 与工作流
```

每轮都需要产出：

- 最新需求文档
- review 结论
- 最新工作流状态

## 8. 对用户可见的交互策略

第一阶段采用“三段式交互”：

### 8.1 需求创建群

用户在固定“需求创建群”中通过 `@CoordinatorService` 发起需求创建。

示例：

```text
@CoordinatorService 创建需求
名称：多轮需求构造工作流
项目：HARNESS
简述：把一次性讨论升级为多轮需求构造与 review 闭环
```

### 8.2 author 私聊

需求创建完成后，Coordinator Service 返回：

```text
REQ-HARNESS-001 已创建。
请私聊需求构造 Agent，并发送：
开始需求构造 REQ-HARNESS-001
```

用户在 author 私聊中启动需求构造。

### 8.3 项目群同步

Coordinator Service 为每个项目维护一个项目群。

项目群用于：

- 同步需求创建结果
- 广播当前状态
- 发送审查通知
- 发送最终通过结果

不要求用户在项目群中与 author 持续深聊。

## 9. 飞书 Workflow / Automation 的接入点

建议接在以下节点：

- 创建群收到 `@CoordinatorService` 创建消息后触发初始化
- 状态变更后通知 owner
- `AI Ready = true` 后提醒人工确认
- `Human Confirmed = true` 后触发进入正式审查
- 超时未回复时催办
- 关键流转时调用 webhook

不建议让飞书工作流直接承接：

- 多轮追问逻辑
- review 判断
- 正式需求文档撰写

## 10. 第一阶段验收标准

- `开始讨论` 不再只执行一次
- 每轮讨论状态可恢复
- 每轮状态推进都由 agent 明确通知 Coordinator
- 未达到 `AI Ready` 不允许进入人工确认
- 未达到 `Human Confirmed` 不允许进入正式审查
- Coordinator Service 只负责规则化编排，不承担深度需求写作

## 11. 建议实施顺序

1. 固化 v1.2 状态机
2. 设计并补齐 Bitable 新字段
3. 抽离 Coordinator Service 的规则化职责
4. 定义 author / reviewer 输入输出契约
5. 定义 callback 事件契约
6. 接入飞书 Workflow / Automation
7. 做新闭环联调与验证
