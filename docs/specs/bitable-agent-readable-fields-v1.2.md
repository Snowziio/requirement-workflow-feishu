# Bitable Agent Read Contract v1.2

> 本文档由 `bitable_schema_v12.json` 派生，用于约束 author / reviewer 可依赖的 Bitable 字段。

## 1. 规则

- author / reviewer 只读这些字段，不自行假设额外字段存在。
- Coordinator 是这些字段的唯一写入方。
- skill 模板、TOOLS.md、方法论文档引用字段时，应以这份清单和 `bitable_schema_v12.json` 为准。

## 2. Author 可读字段

| 字段名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| REQ ID | text | 是 | 需求唯一主键。 |
| 需求名称 | text | 是 | 需求标题。 |
| 项目代号 | text | 是 | 需求所属项目。 |
| 需求简述 | text | 是 | 创建需求时的简要背景。 |
| 状态 | text | 是 | 状态机主状态。 |
| 当前阶段 | text | 是 | 面向人的当前阶段展示。 |
| 当前轮次 | number | 是 | 当前需求构造或 review 的轮次。 |
| 当前讨论字段 | text | 是 | 当前聚焦的讨论字段。 |
| 当前Owner | text | 是 | 当前流程接手者。 |
| 当前接手角色 | text | 是 | 当前接手角色的人类可读标签。 |
| 已完成字段 | text | 是 | 已完成字段的 JSON 数组字符串。 |
| 待补字段 | text | 是 | 待补字段的 JSON 数组字符串。 |
| 最近一次提问 | text | 否 | 当前轮对用户的最新追问。 |
| 最近一次review结论 | text | 否 | 最近一次 review 的摘要结论。 |
| AI Ready | checkbox | 是 | 是否达到人工确认门槛。 |
| Human Confirmed | checkbox | 是 | 人工确认是否已通过。 |
| 需求文档链接 | text | 否 | 需求文档的唯一复用链接。 |
| 最近一次写回时间 | text | 否 | Coordinator 最近一次成功写回状态的 ISO 时间戳。 |

## 3. Reviewer 可读字段

| 字段名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| REQ ID | text | 是 | 需求唯一主键。 |
| 需求名称 | text | 是 | 需求标题。 |
| 项目代号 | text | 是 | 需求所属项目。 |
| 需求简述 | text | 是 | 创建需求时的简要背景。 |
| 状态 | text | 是 | 状态机主状态。 |
| 当前阶段 | text | 是 | 面向人的当前阶段展示。 |
| 当前轮次 | number | 是 | 当前需求构造或 review 的轮次。 |
| 当前讨论字段 | text | 是 | 当前聚焦的讨论字段。 |
| 当前Owner | text | 是 | 当前流程接手者。 |
| 当前接手角色 | text | 是 | 当前接手角色的人类可读标签。 |
| 已完成字段 | text | 是 | 已完成字段的 JSON 数组字符串。 |
| 待补字段 | text | 是 | 待补字段的 JSON 数组字符串。 |
| 最近一次提问 | text | 否 | 当前轮对用户的最新追问。 |
| 最近一次review结论 | text | 否 | 最近一次 review 的摘要结论。 |
| AI Ready | checkbox | 是 | 是否达到人工确认门槛。 |
| Human Confirmed | checkbox | 是 | 人工确认是否已通过。 |
| 需求文档链接 | text | 否 | 需求文档的唯一复用链接。 |
| 最近一次写回时间 | text | 否 | Coordinator 最近一次成功写回状态的 ISO 时间戳。 |

## 4. 使用方式

- author / reviewer 先按 `req_id` 调 context query，再按这里的字段理解状态。
- 如果 `需求文档链接` 非空，author 必须复用，不得新建第二份文档。
- 如果后续要新增字段，先改 `bitable_schema_v12.json`，再同步 Bitable 和 skill 文档。

