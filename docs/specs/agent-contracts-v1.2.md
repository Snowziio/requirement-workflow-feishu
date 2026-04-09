# Agent 契约说明 v1.2

## 1. 目标

本文档用于定义需求构造工作流 v1.2 中三类核心角色的输入、输出、职责边界与协作方式：

- Coordinator Service
- author agent
- review agent

目标是确保：

- Coordinator Service 规则化
- author 专注需求构造
- reviewer 专注质量把关
- 多 agent 协作对用户透明，但不混乱

## 2. 总体协作原则

- Coordinator Service 不做深度需求推理
- author 不直接推进状态机
- reviewer 不直接写正式文档
- 所有关键状态都由 Coordinator Service 持久化
- 对用户的交互采用“创建群 + author 私聊 + 项目群同步”的三段式模型

## 3. Coordinator Service 契约

## 3.1 定位

Coordinator Service 是独立飞书应用后台中的规则优先流程执行器，不是内容作者。

## 3.2 职责

- 创建 REQ
- 初始化 Bitable 讨论态字段
- 维护状态机
- 维护当前 owner
- 维护当前轮次 / 当前讨论字段 / 门禁状态
- 调用 author / reviewer
- 将结构化结果写回正式文档
- 对外发送下一步操作消息

## 3.3 输入

Coordinator Service 可接收：

- 用户命令
  - 在创建群中的 `创建需求`
  - `查看状态`
  - `确认通过`
  - `需要修改`
- 飞书 Workflow / Automation 触发
- 文档事件或记录变更事件
- author 输出
- reviewer 输出
- 人工确认动作

## 3.4 输出

Coordinator Service 输出包括：

- Bitable 记录更新
- 状态机切换
- owner 切换
- 正式文档写回
- 面向用户的状态说明
- 对 author / reviewer 的下一步调用
- 项目群同步消息
- 创建群到 author 私聊的启动协议

## 3.5 不负责

Coordinator Service 不负责：

- 深度需求写作
- 业务判断
- 高自由度方案生成
- 最终质量裁定

## 3.6 输出格式建议

对用户的消息建议保持短、明确、可执行：

```text
REQ-HARNESS-001 已创建。
请私聊需求构造 Agent，并发送：
开始需求构造 REQ-HARNESS-001
```

## 4. Author Agent 契约

## 4.1 定位

author agent 是需求构造的主角，负责显式接手需求共创过程。
它的主要对话表面是与用户的私聊，而不是项目群。

## 4.2 职责

- 引导用户逐轮澄清需求
- 将自然语言归一化为结构化草稿
- 推动需求从模糊表达走向高质量方案
- 识别需要继续追问的点

## 4.3 输入

author 输入必须至少包含：

- `req_id`
- 当前正式需求草稿
- `当前轮次`
- `当前讨论字段`
- `已完成字段`
- `待补字段`
- `最近一次review结论`
- 用户本轮输入
- 用户私聊身份信息

可选输入：

- 历史约束摘要
- UI 设计上下文
- 历史审查意见

## 4.4 输出

author 每轮必须输出：

- `updates`
  - 本轮结构化字段更新
- `normalized_summary`
  - 对用户本轮输入的归一化表达
- `unresolved_questions`
  - 当前仍未解决的问题
- `current_field_completed`
  - 当前字段是否可以视为完成
- `next_field`
  - 下一轮建议聚焦字段
- `next_question`
  - 下一轮建议问题

## 4.5 author 的工作标准

author 不应把工作退化成填字段，而应完成：

- 澄清问题本质
- 明确使用场景
- 识别边界和约束
- 推动 AC 量化
- 识别不完整或模糊表达

## 4.6 author 不负责

author 不负责：

- 直接更新 Bitable
- 直接推进状态机
- 最终决定是否可流转
- 直接自由写正式文档全篇

## 4.7 author 输出示例

```json
{
  "updates": {
    "问题描述": "当前需求讨论流程缺少多轮会话状态管理，导致讨论只能执行一次，后续输入无法持续补全文档。"
  },
  "normalized_summary": "已将问题本质归一化为会话状态缺失导致的需求构造中断。",
  "unresolved_questions": [
    "当前流程中断后，是否需要支持跨天恢复？"
  ],
  "current_field_completed": true,
  "next_field": "使用场景",
  "next_question": "请说明谁会发起需求讨论，以及希望通过这一流程得到什么结果。"
}
```

## 5. Review Agent 契约

## 5.1 定位

review agent 是每轮质量门，不是末尾一次性的审查器。

## 5.2 职责

- 每轮检查草稿质量
- 输出缺失、弱项、矛盾和不可验证项
- 判断是否达到 `AI Ready`
- 给出下一轮聚焦建议

## 5.3 输入

reviewer 输入必须至少包含：

- `req_id`
- 当前正式需求草稿
- `当前轮次`
- `已完成字段`
- `待补字段`
- 本轮 author 更新内容

## 5.4 输出

reviewer 每轮必须输出：

- `ready_for_human_confirmation`
- `summary`
- `findings`
- `weak_fields`
- `conflicts`
- `non_testable_acceptance_criteria`
- `next_focus`

## 5.5 review 维度

每轮 review 至少覆盖：

- 完整性
- 一致性
- 可测试性
- 边界清晰度
- 当前轮内容是否足以推进下一步

## 5.6 reviewer 不负责

reviewer 不负责：

- 直接改写正式文档
- 直接切换状态
- 直接对用户做复杂编排

## 5.7 reviewer 输出示例

```json
{
  "ready_for_human_confirmation": false,
  "summary": "草稿仍需继续打磨。",
  "findings": [
    {
      "dimension": "可测试性",
      "summary": "验收标准仍缺少可量化表达。",
      "severity": "high"
    }
  ],
  "weak_fields": [
    "验收标准"
  ],
  "conflicts": [],
  "non_testable_acceptance_criteria": [
    "系统应明显更稳定"
  ],
  "next_focus": "请补充明确的验收阈值、布尔条件或错误码。"
}
```

## 6. 协作时序

推荐时序：

```text
用户在创建群发起创建
-> Coordinator Service 创建 req_id 并返回私聊启动指令
-> 用户私聊 author，并发送“开始需求构造 REQ-ID”
-> Coordinator Service 读取当前状态
-> author 生成本轮结构化草稿
-> Coordinator Service 写回正式文档和 Bitable
-> reviewer 审当前轮草稿
-> Coordinator Service 写 review 结果
-> Coordinator Service 决定：
   继续讨论 / 等待人工确认 / 进入正式审查
```

## 7. 对用户可见的表达规范

建议使用“三段式入口、显式角色签名”的方式：

- 创建群：`需求协调服务：REQ 已创建，请私聊需求构造 Agent`
- author 私聊：`需求构造 Agent：我已接手 REQ-HARNESS-001`
- 项目群：`审查 Agent：当前草稿仍缺少可量化 AC`

要求：

- 不让用户在群里直接和多个 agent 混聊
- 让用户清楚当前 `req_id` 是什么
- 让用户清楚当前是谁在工作
- 让用户清楚为什么流程没有流转

## 8. 契约落地建议

后续实现时建议把三方输出收敛成结构化对象，而不是仅靠自然语言：

- coordinator_service snapshot
- author turn result
- review result

这样可以：

- 降低 prompt 偶发漂移
- 提升幂等性
- 便于 Workflow / Webhook / UI 卡片复用
