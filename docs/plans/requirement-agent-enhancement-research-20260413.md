# 需求生成与 Review Agent 强化方案调研

日期：2026-04-13

## 1. 现状判断

结合当前仓库设计与实现，现有边界其实已经比较合理：

- `Coordinator Service` 负责状态机、Bitable、流程事件与卡点通知
- `author agent` 负责需求澄清与正式文档撰写
- `review agent` 负责质量门与回流意见
- OpenClaw 只承接智能能力，不承担流程真相源

这条边界在以下文档中已经明确：

- [README.md](/Users/daxin/work/requirement-workflow-feishu/README.md)
- [agent-contracts-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/agent-contracts-v1.2.md)
- [openclaw-skill-implementation-guide-v1.2.md](/Users/daxin/work/requirement-workflow-feishu/docs/specs/openclaw-skill-implementation-guide-v1.2.md)

所以后续不建议把系统重构成“一个大而全的多 agent 黑盒”。更合适的方向是：

1. 保留现有 `Coordinator + author + reviewer` 主流程
2. 把增强放在 `author/reviewer` 内部能力层
3. 用 MCP 给 agent 提供稳定上下文、外部知识和文档读写能力
4. 用 eval / rubric / trace 机制把“需求质量”从主观感受变成可观测对象

## 2. 当前缺口

从现有仓库能力看，主流程已经跑通，但智能层还缺 4 类关键能力：

### 2.1 缺少可复用的“需求采集与澄清 skill”

当前 author 契约已经定义了输入输出，但还没有一套稳定的：

- 追问策略
- 需求结构化提取 schema
- 缺口检测规则
- 章节级 rewrite 策略

这会导致 author 容易退化成“聊天式记录员”。

### 2.2 缺少可执行的 review rubric

当前 reviewer 契约定义了 review 维度，但还没有形成：

- 固定评分维度
- 通过 / 退回阈值
- 缺陷分类
- 可验证性检查项

结果是 review 质量不稳定，难以比较不同 prompt / 模型 / skill 版本。

### 2.3 缺少外部上下文汇聚层

需求生成天然依赖跨系统上下文，例如：

- 历史需求与历史 review 记录
- 项目代码库现状
- GitHub issue / PR
- 飞书文档、Notion、Confluence、Jira

当前 `fetch-context` 已经覆盖流程上下文，但尚未形成统一的“知识接入层”。

### 2.4 缺少评测与可观测性

当前架构能推进状态，但还不够方便回答这些问题：

- 哪类需求最容易在 AI review 被打回
- 哪一版 author prompt 让通过率更高
- reviewer 的 reject 是否真的提升了最终通过质量
- 不同模型在“边界清晰度 / 可测试性”上谁更稳

## 3. 外部方案调研

## 3.1 MCP：最值得直接引入

### A. 官方 MCP 基础能力

MCP 官方把能力分成 `resources`、`prompts`、`tools`，非常适合你现在这种“Coordinator 管状态，Agent 消费上下文”的架构。

适合本项目的关键点：

- `resources`：暴露需求上下文、历史需求、schema、review rubric
- `prompts`：暴露标准化的 author / reviewer 模板
- `tools`：提供文档读写、检索、比对、提交 review 结果等操作
- `sampling`：允许 MCP server 触发受控的二次 LLM 调用，适合做 server 侧小型 judge / summarizer

参考：

- MCP Resources: <https://modelcontextprotocol.io/docs/concepts/resources>
- MCP Prompts: <https://modelcontextprotocol.io/docs/concepts/prompts>
- MCP Tools: <https://modelcontextprotocol.io/specification/2025-03-26/server/tools>
- MCP Sampling: <https://modelcontextprotocol.io/docs/concepts/sampling>

### B. GitHub MCP

如果需求 review 想增强“实现可行性”和“与现有代码一致性”，GitHub MCP 很有价值。

可以让 reviewer 在 review 时直接拉取：

- 当前 repo 结构
- 历史 issue / PR
- 相关模块代码
- 已知讨论与变更记录

参考：

- GitHub MCP 概览: <https://docs.github.com/en/copilot/concepts/context/mcp>
- GitHub MCP 使用说明: <https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/use-the-github-mcp-server>

### C. Atlassian Rovo MCP

如果你们后续需求真相源不只在飞书，而是会落到 Jira / Confluence，那么 Rovo MCP 很适合作为“企业知识侧上下文源”。

它的意义不是替代 Coordinator，而是让 author / reviewer 能读取：

- Jira epic / issue
- Confluence 既有方案文档
- 团队历史决策上下文

参考：

- Rovo MCP GA: <https://www.atlassian.com/blog/announcements/atlassian-rovo-mcp-ga>
- Rovo MCP 生态扩展: <https://www.atlassian.com/blog/announcements/rovo-mcp-gallery>

### D. 官方参考 MCP server

`modelcontextprotocol/servers` 已有若干很适合你们做原型或直接复用：

- `filesystem`
- `git`
- `memory`
- `fetch`
- `docs`

其中最值得借鉴的是：

- `memory`：可做需求历史、review 结论、术语/约束图谱
- `git`：辅助 reviewer 判断需求与现有实现的偏差
- `docs` / `fetch`：用于拉取远端规范、已有文档

参考：

- 官方 reference servers: <https://github.com/modelcontextprotocol/servers>

## 3.2 Skill：最适合直接补齐 author/reviewer

当前 session 已有几个本地 skill 思路是可直接借鉴的：

- `notion-spec-to-implementation`
- `notion-research-documentation`
- `github:gh-address-comments`
- `skill-creator`

对本项目的启发是：

### A. Author Skill 应拆成 3 个子 skill

1. `requirement-intake`
   负责把零散输入收敛成结构化需求骨架
2. `requirement-gap-hunter`
   专门找缺失信息、冲突、不可验证项
3. `requirement-compiler`
   负责把对话结果编译成正式章节

这样可以避免一个 prompt 同时兼顾“采访、分析、写作、结构化输出”而失稳。

### B. Review Skill 应拆成 2 个子 skill

1. `requirement-rubric-review`
   对完整性、一致性、可测试性、边界清晰度打分
2. `requirement-implementation-sanity-review`
   结合代码库 / issue / 历史方案判断需求是否违背现实约束

### C. 再补一个“变更摘要 skill”

建议增加：

- `requirement-delta-summary`

用于输出本轮相较上轮：

- 新增了什么
- 删除了什么
- 哪些风险被消除
- 哪些阻塞仍未解决

这会显著提升 reviewer 的效率。

## 3.3 开源框架：适合选配，不建议替代 Coordinator

### A. LangGraph

LangGraph 最适合你们的点不是“多 agent 很炫”，而是：

- 持久化状态
- 可恢复执行
- human-in-the-loop
- interrupt / approve / reject

这些能力和你们现在的需求工作流非常贴合。

但建议它只承接 `author/reviewer` 内部子流程，不替换现有 Coordinator 状态机。

参考：

- LangGraph overview: <https://docs.langchain.com/oss/python/langgraph/overview>
- LangGraph persistence: <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph HITL: <https://docs.langchain.com/oss/python/langchain/human-in-the-loop>

### B. CrewAI

CrewAI 的 `Flows` 很适合做“多步内容生成 + 条件路由 + 状态共享”的轻量流程。

优点：

- 上手快
- 事件驱动和状态流比较直观
- 对“先提取，再追问，再编译，再审查”这种流水线比较友好

缺点：

- 若直接拿来替代现有 Coordinator，会导致规则边界变模糊

参考：

- CrewAI intro: <https://docs.crewai.com/en/introduction>
- CrewAI flows: <https://docs.crewai.com/en/concepts/flows>

### C. AutoGen

AutoGen 适合做多 agent 对话实验，但我不建议把它作为当前主方案。

原因：

- 多 agent 自由对话很容易重新退化成黑盒
- 对你们这种“规则编排 + 显式流转”的产品形态，不是最优先

参考：

- AutoGen multi-agent conversation: <https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat>

### D. Spec Kit

Spec Kit 对你们最有价值的不是直接拿来运行 agent，而是拿它的“spec-first artifact discipline”。

特别适合借鉴：

- 先规格化，再实现
- 用标准 artifact 管住 prompt 漂移
- 把需求、计划、评审、实现关联起来

建议把它的方法论借到你们的需求文档模板和 review rubric，而不是整套照搬 CLI 工作流。

参考：

- GitHub repo: <https://github.com/github/spec-kit>
- 文档站: <https://github.github.com/spec-kit/index.html>

## 3.4 记忆与评测：非常值得补

### A. Memory

如果 author / reviewer 后续要长期跟踪同一项目、同一产品线，建议补“压缩后的长期记忆层”。

可选：

- 官方 MCP `memory` server
- Mem0

用途：

- 存储稳定约束，而不是原始长对话
- 记录术语、系统边界、历史被 reject 的模式
- 给下一轮需求生成提供 project memory

参考：

- MCP reference servers: <https://github.com/modelcontextprotocol/servers>
- Mem0 OSS: <https://docs.mem0.ai/open-source>

### B. Evals / Tracing

这部分我认为是必须补的，不然需求 agent 很难持续变好。

推荐：

- Langfuse：trace、dataset、score、annotation queue
- OpenAI eval-driven 方法：先定义质量标准，再驱动 prompt / flow 演进

参考：

- Langfuse docs: <https://langfuse.com/docs>
- Langfuse scores: <https://langfuse.com/docs/evaluation/scores/overview>
- Langfuse datasets: <https://langfuse.com/docs/evaluation/experiments/overview>
- OpenAI eval-driven system design: <https://cookbook.openai.com/examples/partners/eval_driven_system_design/receipt_inspection>

### C. Structured Outputs

无论 author 还是 reviewer，都建议改成 schema-first 输出。

特别适合要求模型稳定输出：

- 当前需求骨架
- 缺失项列表
- 风险列表
- review scorecard
- callback payload

参考：

- OpenAI Structured Outputs 介绍: <https://openai.com/index/introducing-structured-outputs-in-the-api/>
- OpenAI Structured Outputs 文档: <https://platform.openai.com/docs/guides/json-mode>

## 4. 推荐强化架构

建议采用“Coordinator 不动，Author/Reviewer 内部升级”的方案。

```text
Feishu / OpenClaw
    -> Coordinator Service
        -> Requirement Context MCP
        -> Requirement Knowledge MCP
        -> Document MCP
        -> GitHub / Jira / Confluence / Notion MCP
    -> Author Agent Runtime
        -> intake skill
        -> gap-hunter skill
        -> compiler skill
    -> Review Agent Runtime
        -> rubric-review skill
        -> implementation-sanity-review skill
        -> delta-summary skill
    -> Trace / Eval Layer
        -> Langfuse
        -> dataset + score + human annotation
```

## 5. 最推荐的 3 个新增 MCP

## 5.1 `requirement-context-mcp`

这是最应该自研的一个。

建议暴露：

- `resource://requirements/{req_id}/snapshot`
- `resource://requirements/{req_id}/history`
- `resource://requirements/{req_id}/latest-review`
- `resource://requirements/rubrics/author-ready`
- `resource://requirements/rubrics/review-scorecard`

建议工具：

- `get_requirement_snapshot(req_id)`
- `list_requirement_rounds(req_id)`
- `get_latest_document(req_id)`
- `submit_author_ready(req_id, payload)`
- `submit_review_result(req_id, payload)`

价值：

- agent 不再依赖拼接上下文文本包
- prompt 更短、更稳定
- 与现有 callback / context query 契约天然兼容

## 5.2 `requirement-knowledge-mcp`

定位是“需求知识侧检索与记忆层”。

建议收录：

- 历史高质量需求样本
- 历史 review 反例
- 产品术语表
- 系统约束与非功能要求模板
- 常见需求缺陷模式

建议工具：

- `search_requirement_examples(query)`
- `search_review_failures(query)`
- `get_product_constraints(project)`
- `save_requirement_memory(req_id, memory_item)`

## 5.3 `document-bridge-mcp`

把飞书文档、Notion、Confluence 统一封成文档接口。

建议工具：

- `read_document(uri)`
- `append_review_notes(uri, notes)`
- `rewrite_section(uri, section_id, content)`
- `diff_document_versions(uri, from, to)`

价值：

- 把文档读写从 prompt 层剥离
- 后续切换文档载体时对 agent 更透明

## 6. 最推荐的 5 个 skill

## 6.1 `requirement-intake`

输入：

- 用户本轮表达
- requirement snapshot
- 历史约束

输出：

- 当前目标
- 已知事实
- 未决问题
- 推荐追问列表

## 6.2 `requirement-gap-hunter`

固定查找：

- 缺 actor
- 缺场景
- 缺边界
- 缺非功能要求
- 缺验收标准
- 存在术语歧义
- 存在相互矛盾陈述

## 6.3 `requirement-compiler`

职责：

- 把结构化骨架编译成正式需求文档
- 优先 rewrite 指定 section，而不是整篇重写
- 输出章节级变更摘要

## 6.4 `requirement-rubric-review`

固定输出 scorecard：

- completeness
- consistency
- testability
- boundary_clarity
- implementation_alignment
- decision: pass / reject

## 6.5 `requirement-implementation-sanity-review`

通过 GitHub MCP 或 repo context 检查：

- 当前需求是否违背现有架构
- 是否忽略已有实现
- 是否引入高风险隐含迁移成本
- 是否缺少与代码结构对应的落点

## 7. 评测设计

建议从第一天就建立数据集，而不是等 agent 不稳定后再补。

至少建 3 类数据集：

### 7.1 `requirement-intake-dataset`

样本内容：

- 用户原始需求表达
- 期望抽取骨架
- 期望追问点

### 7.2 `review-rubric-dataset`

样本内容：

- 需求文档
- 人工评分
- 是否应 reject
- reject 原因标签

### 7.3 `revision-delta-dataset`

样本内容：

- 上一版文档
- 当前版文档
- 真实变更摘要

建议观测指标：

- AI review reject precision
- author-ready 命中率
- 每轮澄清新增有效信息数
- 最终人工通过率
- 平均 review 轮次
- 不同模型 / prompt 版本的 score 变化

## 8. 推荐落地顺序

## Phase 1：两周内最小增强

1. 保留现有 Coordinator 与 callback 契约
2. 增加 schema-first 的 author / reviewer 输出对象
3. 把 reviewer 固化为 rubric scorecard
4. 增加 `requirement-context-mcp`
5. 接 Langfuse 做 trace 与 score

这是性价比最高的一步。

## Phase 2：一个月内增强

1. 增加 `requirement-gap-hunter` 和 `requirement-delta-summary`
2. 接 GitHub MCP，补“实现一致性 review”
3. 建第一批 review dataset
4. 把被 reject 的案例沉淀到 knowledge MCP / memory

## Phase 3：后续演进

1. 按需接 Jira / Confluence / Notion MCP
2. 给 author / reviewer 内部子流程引入 LangGraph 或 CrewAI Flow
3. 引入长期记忆层
4. 做 prompt / model A/B eval

## 9. 最终建议

最值得做的不是“换一个更强的 agent 框架”，而是把当前系统从“能流转”升级成“能稳定地产生高质量需求并可被评测”。

因此推荐优先级如下：

1. 自研 `requirement-context-mcp`
2. 把 author / reviewer 改成 skill 化、schema 化
3. 建立 reviewer rubric + eval 数据集
4. 接 GitHub MCP 做实现一致性检查
5. 视你们知识库现状，再接 Jira / Confluence / Notion 类 MCP

一句话总结：

不要推翻现在的 Coordinator 架构，应该在它之上补“上下文接入层 + skill 分层 + rubric review + eval 闭环”。
