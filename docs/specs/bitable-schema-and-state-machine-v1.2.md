# Bitable 字段方案与状态机流转表 v1.2

## 1. 目标

本文档用于固化需求构造工作流 v1.2 的两个核心接口面：

- Bitable 新字段方案
- v1.2 状态机流转表

这两部分是后续改造 Coordinator Service、author/reviewer、飞书 Workflow / Automation 的统一基线。

## 2. 设计原则

- 会话状态必须显式持久化
- 字段命名尽量贴近业务含义
- 关键布尔门禁必须可直接被自动化读取
- 状态机必须可审计、可拒绝非法流转
- 字段要兼顾人读、机器人写、Workflow 判断

## 3. Bitable 字段方案

## 3.1 继续保留的现有字段

继续保留当前已经落地的生命周期字段：

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

## 3.2 v1.2 新增字段清单

### A. 会话状态字段

#### `当前阶段`

- 类型：单行文本
- 示例值：`需求构造`、`人工确认`、`正式审查`
- 写入方：Coordinator Service
- 用途：
  - 给人直接看当前工作所处阶段
  - 给 Workflow 做轻量条件判断

#### `当前轮次`

- 类型：数字
- 默认值：`0`
- 写入方：Coordinator Service
- 用途：
  - 记录当前是第几轮构造
  - 支持每轮 review 追踪

#### `当前讨论字段`

- 类型：单行文本
- 示例值：`问题描述`
- 写入方：Coordinator Service
- 用途：
  - 标记当前聚焦主题
  - 支持断点恢复

#### `已完成字段`

- 类型：多行文本
- 建议格式：JSON 数组字符串
- 示例值：`["问题描述","使用场景","输入"]`
- 写入方：Coordinator Service
- 用途：
  - 支持完整度重算
  - 支持查看状态

#### `待补字段`

- 类型：多行文本
- 建议格式：JSON 数组字符串
- 示例值：`["输出","边界","验收标准","非功能要求"]`
- 写入方：Coordinator Service
- 用途：
  - 支持 author 下一轮聚焦
  - 支持 Workflow 判断是否接近完成

### B. 角色接手字段

#### `当前Owner`

- 类型：单行文本
- 示例值：`author`、`reviewer`、`human`、`coordinator-service`
- 写入方：Coordinator Service
- 用途：
  - 标识当前应该由谁接手
  - 便于通知和催办

#### `当前接手角色`

- 类型：单行文本
- 示例值：`需求构造Agent`、`审查Agent`、`人工确认`
- 写入方：Coordinator Service
- 用途：
  - 面向人类的可读表达
  - 用于群消息/卡片文案

### C. 质量门禁字段

#### `最近一次review结论`

- 类型：多行文本
- 示例值：`草稿仍需继续打磨，当前验收标准缺少量化指标。`
- 写入方：reviewer 输出，Coordinator Service 持久化
- 用途：
  - 给用户直接看最新质量判断
  - 给 Workflow / 通知提供上下文

#### `AI Ready`

- 类型：复选框或布尔
- 默认值：`false`
- 写入方：Coordinator Service
- 用途：
  - 表示 reviewer 是否认为已达到人工确认门槛
  - 作为进入 `HUMAN_CONFIRM` 的硬门禁

#### `Human Confirmed`

- 类型：复选框或布尔
- 默认值：`false`
- 写入方：Coordinator Service
- 用途：
  - 表示人工是否确认当前需求准确
  - 作为进入 `FINAL_REVIEW` 的硬门禁

### D. 追踪与恢复字段

#### `最近一次提问`

- 类型：多行文本
- 示例值：`请继续补充“验收标准”，并尽量给出可量化表达。`
- 写入方：author 输出，Coordinator Service 持久化
- 用途：
  - 会话中断后恢复上下文
  - 支持查看状态

#### `最近一次写回时间`

- 类型：单行文本
- 写入值：ISO 8601 时间戳字符串
- 写入方：Coordinator Service
- 用途：
  - 审计最近一次正式文档写回
  - 用于 Workflow 超时催办

## 3.3 字段类型建议汇总表

| 字段 | 类型 | 默认值 | 主要写入方 | 主要用途 |
|---|---|---|---|---|
| 当前阶段 | 单行文本 | 需求构造 | Coordinator Service | 阶段观测 |
| 当前轮次 | 数字 | 0 | Coordinator Service | 轮次追踪 |
| 当前讨论字段 | 单行文本 | 问题描述 | Coordinator Service | 会话恢复 |
| 已完成字段 | 多行文本(JSON) | `[]` | Coordinator Service | 完整度 |
| 待补字段 | 多行文本(JSON) | 全字段列表 | Coordinator Service | 下一轮聚焦 |
| 当前owner | 单行文本 | coordinator-service | Coordinator Service | 接手人 |
| 当前接手角色 | 单行文本 | 需求协调服务 | Coordinator Service | 面向人类展示 |
| 最近一次review结论 | 多行文本 | 空 | Coordinator Service | 质量结论 |
| AI Ready | 布尔 | false | Coordinator Service | AI 门禁 |
| Human Confirmed | 布尔 | false | Coordinator Service | 人工门禁 |
| 最近一次提问 | 多行文本 | 空 | Coordinator Service | 上下文恢复 |
| 最近一次写回时间 | 日期时间 | 空 | Coordinator Service | 审计/催办 |

## 3.4 默认初始化建议

创建需求成功后，建议默认写入：

- `状态 = DRAFTING`
- `当前阶段 = 需求构造`
- `当前轮次 = 0`
- `当前讨论字段 = 问题描述`
- `已完成字段 = []`
- `待补字段 = ["问题描述","使用场景","输入","输出","边界","验收标准","非功能要求"]`
- `当前owner = author`
- `当前接手角色 = 需求构造Agent`
- `最近一次review结论 = ""`
- `AI Ready = false`
- `Human Confirmed = false`
- `最近一次提问 = "请先澄清问题本质，我们会逐轮完成需求构造。"`

### 3.5 状态字段值约定

`状态` 字段现在统一只允许以下 5 个值：

- `DRAFTING`
- `AI_REVIEW`
- `HUMAN_CONFIRM`
- `FINAL_REVIEW`
- `APPROVED`

如果线上 Bitable 里仍有旧值：

- `DISCUSSION_ROUTING`
- `DISCUSSING`
- `AI_REVIEWING`
- `HUMAN_CONFIRMING`
- `REVIEWING`
- `REQ_APPROVED`

需要先执行状态迁移，再继续用新版本 Coordinator。

## 4. v1.2 状态机

## 4.1 状态定义

- `CREATED`
  - 记录已创建，但尚未进入构造流程

- `DRAFTING`
  - author 正在进行某一轮需求构造

- `AI_REVIEW`
  - reviewer 正在审当前轮草稿

- `HUMAN_CONFIRM`
  - reviewer 已判定达到门槛，等待人工确认

- `FINAL_REVIEW`
  - 已结束需求构造，进入正式需求审查

- `APPROVED`
  - 需求层通过

## 4.2 触发事件列表

- `create_requirement`
- `author_submit`
- `ai_review_reject`
- `ai_review_pass`
- `human_confirm_yes`
- `human_confirm_no`
- `final_review_pass`
- `final_review_reject`

## 4.3 状态流转表

| 当前状态 | 触发事件 | 条件 | 下一状态 | 写入动作 |
|---|---|---|---|---|
| CREATED | create_requirement | 创建成功 | DRAFTING | 初始化草稿态字段 |
| DRAFTING | author_submit | author 通知可进入 AI review | AI_REVIEW | current_round 更新为当前文档迭代轮次（如有） |
| AI_REVIEW | ai_review_reject | AI Ready = false | DRAFTING | 写 review 结论，更新下一轮问题 |
| AI_REVIEW | ai_review_pass | AI Ready = true | HUMAN_CONFIRM | owner=human，写确认提示 |
| HUMAN_CONFIRM | human_confirm_no | 人工不满意 | DRAFTING | Human Confirmed=false，退回继续打磨 |
| HUMAN_CONFIRM | human_confirm_yes | 人工确认满意 | FINAL_REVIEW | Human Confirmed=true，进入正式审查 |
| FINAL_REVIEW | final_review_pass | 审查通过 | APPROVED | 写通过结果 |
| FINAL_REVIEW | final_review_reject | 审查要求修改 | DRAFTING | 清空门禁，回退继续打磨 |

## 4.4 非法流转规则

以下情况必须拒绝：

- `DRAFTING` 直接进入 `FINAL_REVIEW`，但 `AI Ready` 和 `Human Confirmed` 不满足
- `HUMAN_CONFIRM` 之前执行人工确认
- `APPROVED` 后再次执行通过
- 非 `FINAL_REVIEW` 状态下执行正式批准

拒绝时要求：

- 不修改 Bitable
- 返回当前状态
- 返回可执行下一步动作

## 4.5 门禁规则

### AI 门禁

仅当 reviewer 明确判断当前草稿达到人工确认门槛时：

- `AI Ready = true`
- 允许进入 `HUMAN_CONFIRM`

否则：

- `AI Ready = false`
- 强制回到 `DRAFTING`

### 人工门禁

仅当人工确认当前需求准确表达意图时：

- `Human Confirmed = true`
- 允许进入 `FINAL_REVIEW`

否则：

- `Human Confirmed = false`
- 回到 `DRAFTING`

## 4.6 退回策略

### 构造阶段退回

从 `AI_REVIEW` 或 `HUMAN_CONFIRM` 退回 `DRAFTING` 时：

- 保留当前轮次
- 保留已完成字段
- 更新待补字段
- 更新最近一次提问
- 清空不再有效的门禁状态

### 正式审查退回

从 `FINAL_REVIEW` 被打回 `DRAFTING` 时：

- `AI Ready = false`
- `Human Confirmed = false`
- 保留正式文档已有结构化内容
- 以 review 修改意见作为下一轮起点

## 5. Workflow 适配建议

这些字段和状态适合直接给飞书 Workflow / Automation 使用：

- `状态`
- `当前阶段`
- `当前owner`
- `AI Ready`
- `Human Confirmed`
- `最近一次写回时间`

推荐的 Workflow 条件判断：

- `状态 = HUMAN_CONFIRM` 且 `Human Confirmed = false`
  - 发送人工确认提醒

- `状态 = DRAFTING` 且超过阈值未更新 `最近一次写回时间`
  - 发送催办提醒

- `状态 = FINAL_REVIEW`
  - 触发正式审查相关通知

## 6. 第一阶段验收点

- 新字段已在 Bitable 中创建并可正常写入
- 状态机所有合法流转都可执行
- 非法流转会被拒绝且不污染数据
- `AI Ready` 与 `Human Confirmed` 可直接作为 Workflow 条件
- 会话中断后可通过 Bitable 字段恢复当前上下文
