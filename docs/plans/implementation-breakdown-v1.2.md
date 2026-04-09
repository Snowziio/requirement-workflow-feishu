# 需求构造工作流 v1.2 - 实施拆解

## 1. 实施目标

将当前需求层最小闭环升级为可多轮构造、可持续 review、可结构化写回的需求构造系统，并在第一阶段稳定交付到 `REQ_APPROVED`。

## 2. 实施顺序

建议按下面顺序推进：

1. 固化状态机与领域模型
2. 设计并补齐 Bitable 新字段
3. 定义 author / reviewer / Coordinator Service 契约
4. 实现正式文档 section rewrite
5. 接入飞书 Workflow / Automation 触发点
6. 联调远端飞书后台服务、OpenClaw agent 与项目配置
7. 做端到端验证

## 3. 任务拆解

## 3.1 状态机与领域模型

目标：

- 将 v1 状态机升级为 v1.2 状态机
- 明确每个状态的进入条件、退出条件、拒绝条件

任务：

- 定义目标状态：
  - `CREATED`
  - `DISCUSSION_ROUTING`
  - `DISCUSSING`
  - `AI_REVIEWING`
  - `HUMAN_CONFIRMING`
  - `REVIEWING`
  - `REQ_APPROVED`
- 定义合法流转表
- 定义非法流转的拒绝消息
- 定义 `AI Ready` 与 `Human Confirmed` 的门禁关系

验收：

- 所有状态迁移可审计
- 非法流转不会改写 Bitable

## 3.2 Bitable 字段扩展

目标：

- 让讨论进度不再依赖 prompt 和记忆
- 支持会话恢复、状态查询、自动化触发

新增字段：

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

任务：

- 明确字段类型
- 明确默认值
- 明确哪些字段由 Coordinator Service 写入
- 明确哪些字段用于 Workflow 条件触发

建议字段类型：

- 文本：`当前阶段`、`当前讨论字段`、`当前owner`、`当前接手角色`、`最近一次review结论`、`最近一次提问`
- 数字：`当前轮次`
- 多值文本或 JSON 字符串：`已完成字段`、`待补字段`
- 布尔：`AI Ready`、`Human Confirmed`
- 时间：`最近一次写回时间`

验收：

- 新字段能支持“查看状态”“继续讨论”“人工确认”等操作
- 新字段可被飞书自动化直接读取

## 3.3 Agent 契约

目标：

- 把协调、写作、审查的边界彻底拆清楚

### Coordinator Service 输入输出

输入：

- 用户命令
- 飞书 workflow 触发
- 文档更新事件
- review 结果

输出：

- Bitable 状态更新
- owner 切换
- 正式文档写回
- 下一步动作消息

### Author 输入输出

输入：

- 当前需求草稿
- 当前轮次
- 当前讨论字段
- review 上一轮结论
- 用户本轮输入

输出：

- 本轮结构化字段更新
- 本轮归一化表达
- 未决问题
- 下一轮问题
- 当前字段是否完成

### Reviewer 输入输出

输入：

- 当前正式草稿
- 当前轮次
- 当前完成字段情况

输出：

- review 结论
- 缺失项
- 弱项
- 矛盾项
- 不可验证 AC
- 是否 `AI Ready`
- 下一轮聚焦建议

验收：

- author 不直接负责状态推进
- reviewer 不直接写正式文档
- Coordinator Service 不负责深度需求推理

## 3.4 正式文档 section rewrite

目标：

- 消除 append 聊天记录的退化行为

任务：

- 定义正式需求文档 section 模板
- 定义 section 定位规则
- 定义 block replace 逻辑
- 定义重试幂等规则

建议 section：

- `需求概览`
- `问题描述`
- `使用场景`
- `输入`
- `输出`
- `边界`
- `验收标准`
- `非功能要求`

实现要求：

- 重写目标块时不破坏其他 section
- 同一轮重试不会重复写入
- 保留正式文档的稳定结构

验收：

- 讨论若进行三轮，正式文档仍是整洁结构化文档
- 文档末尾不出现聊天摘要堆积

## 3.5 交互与命令策略

目标：

- 采用“创建群 + author 私聊 + 项目群同步”的交互体验
- 让多角色接手对用户可见

建议支持：

- 创建群中的 `@CoordinatorService 创建需求`
- author 私聊中的 `开始需求构造 REQ-ID`
- `查看状态`
- `确认进入审查`
- `确认通过`
- `需要修改`

建议消息表现：

- 创建群：`需求协调服务：REQ-HARNESS-001 已创建，请私聊需求构造 Agent`
- author 私聊：`需求构造 Agent：我已接手 REQ-HARNESS-001`
- 项目群：`审查 Agent：当前草稿仍缺少可量化 AC`

验收：

- 用户不必在群里直接和多个 agent 混聊
- `req_id` 在交互中始终显式可见
- 角色切换清晰可见

## 3.6 飞书 Workflow / Automation 接入

目标：

- 让飞书原生能力承担触发、通知、催办、条件分支

建议接入点：

- 创建群中的需求创建消息触发初始化
- owner 切换后通知当前接手角色
- `AI Ready = true` 后触发人工确认提醒
- `Human Confirmed = true` 后触发进入正式审查
- 长时间未推进后触发催办

不纳入：

- 多轮推理
- 内容质量判断
- 正式文档编译

验收：

- Workflow 与 Coordinator Service 分层清晰
- 自动化只做编排，不做认知

## 3.7 远端部署与联调

目标：

- 将设计落到当前已存在的 OpenClaw 部署实例

当前已确认远端资源：

- `ai-ops-router`
- `ai-founder-brief`
- `ai-meeting-closeout`
- `config/feishu_project_space.json`
- 审查卡片发送脚本

任务：

- 对齐远端 skills 与 v1.2 设计
- 对齐 Bitable 字段与配置
- 对齐 workflow 回调入口
- 评估现有脚本是否可复用

验收：

- 远端配置与本地设计稿一致
- 不再停留在文档设计层

## 3.8 端到端验证

目标：

- 用真实 REQ 跑通新闭环

最小验证链路：

1. 创建需求
2. author 显式接手
3. 至少两轮 discussion + review
4. `AI Ready = true`
5. 人工确认
6. 进入正式审查
7. 审查通过
8. 状态进入 `REQ_APPROVED`

重点验证：

- 会话状态是否可恢复
- 正式文档是否按 section rewrite
- reviewer 是否每轮执行
- 非法流转是否被拒绝
- 重试是否幂等

## 4. 推荐里程碑

### M1：设计冻结

- 状态机确认
- Bitable 字段确认
- agent 契约确认

### M2：本地实现完成

- 领域模型
- section rewrite
- 多轮 review 闭环

### M3：飞书编排接入完成

- Workflow 触发点
- Coordinator Service 对接
- 基础通知与催办

### M4：远端联调完成

- 真实 agent 配置更新
- Bitable 结构升级
- 真实 REQ 联调通过

## 5. 建议的下一步

建议直接进入以下 3 个优先任务：

1. 输出 Bitable 新字段方案与字段类型清单
2. 输出 v1.2 状态机的事件与流转表
3. 输出 section rewrite 的正式文档模板与写回规则

这三项一旦确认，后续代码与远端联调就可以并行推进。
