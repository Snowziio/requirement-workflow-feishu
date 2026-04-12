# 顶层与全景设计上下文

本次开发最终目标：在新的项目里落地三层架构方案，形成一套可执行的上下文文档包，支持从现有 OpenClaw/飞书环境无缝启动实现工作。

本文档给新项目提供顶层架构、系统边界和全景设计视图，帮助后续设计、拆解和实现保持一致。

## 1. 顶层目标

构建一个面向需求构造的工作流系统，使飞书中的需求讨论从“消息往来”升级成“被编排、被审查、被正式写入”的高质量共创过程。

最终效果：

- 飞书工作流负责触发与编排
- Coordinator Service 负责规则执行
- author/reviewer agents 负责内容质量
- Bitable 提供状态机与观测面
- 飞书文档保存正式需求产物

## 2. 三层架构

### 第一层：Feishu Workflow / Automation

职责：

- 触发器
- 简单条件分支
- 通知
- 调 Webhook / HTTP
- 基础状态推进

适合承载：

- 新建记录触发
- 状态变更触发
- owner 变化通知
- 审查准备完成提醒
- 超时催办

不适合承载：

- 深度需求讨论
- 多轮推理
- 复杂质量判断
- 结构化文档编译

## 3. 第二层：Coordinator Service

定位：

- 独立飞书应用后台中的规则化、可审计流程执行器

职责：

- 创建 REQ
- 更新 Bitable
- 维护 owner
- 维护当前阶段 / 当前轮次 / 当前讨论字段
- 接收 author / reviewer 的流程事件
- 推动工作流状态流转

原则：

- 尽量不用自由生成完成关键状态推进
- 所有状态变更可审计
- 所有写入可幂等重放

## 4. 第三层：Author / Reviewer Agents

### author agent

职责：

- 显式接手需求构造
- 使用复合 skill 引导用户逐轮澄清
- 形成结构化需求草稿

它要做的不是填表，而是：

- 提炼问题
- 拆场景
- 识别边界
- 强化约束
- 推动 AC 量化

### review agent

职责：

- 每轮 review 当前草稿质量
- 输出缺失、歧义、矛盾、不可验证项
- 判断是否可以进入下一轮或流转下一阶段

## 5. 建议的运行闭环

```text
Feishu 触发器
  -> Coordinator Service 建立/更新流程状态
  -> Author 显式接手需求文档构造
  -> Author 通知 Coordinator 进入 AI review
  -> Reviewer 审当前文档并与 author 循环协作
  -> Reviewer 通知 Coordinator 流转结果
  -> Coordinator 更新 Bitable / 工作流状态
```

## 6. 系统边界

### 本项目负责

- 需求层创建、讨论、审查
- 飞书工作流与 OpenClaw 协作
- Bitable 状态机
- 需求文档正式编译

### 本项目暂不负责

- Spec/Harness 自动生成
- GitHub contract PR 自动化
- 完整的 checkpoint handler 扩展
- 实现层与 CI 层联动

## 7. 文档体系设计

推荐在新项目里维护 4 类文档：

1. `context/`
   - 环境上下文
   - 方法论上下文
   - 顶层与全景设计

2. `specs/`
   - 需求文档工作流 spec
   - 状态机
   - Bitable schema
   - author/reviewer 接手机制

3. `decisions/`
   - 关键架构决策
   - 与共享基础设施的边界

4. `reference/`
   - 现场验证记录
   - 环境实例配置

## 8. 关键设计判断

### 判断一：协调层必须规则化

如果 Coordinator Service 太智能，系统会重新退化成“单 agent 包打天下”，最终变得不稳定、不可审计。

### 判断二：内容质量必须由专职 agent 负责

如果没有 author/reviewer 分工，需求讨论一定会退化成形式化填空。

### 判断三：文档必须是正式产物，不是聊天记录附录

讨论的结果应被编译成结构化需求文档，而不是简单 append 到文档尾部。

### 判断四：review 必须前移

review 不应只是阶段末尾的最终审查，而应成为每轮写作的组成部分。

## 9. 关联来源

本设计吸收了三类来源：

- Harness Engineering 方法论 v1.3（本仓库为 v1.3 首个参考实现）
- 分阶段契约工作流设计
- 本次 HARNESS 环境的实际联调和缺陷观察
