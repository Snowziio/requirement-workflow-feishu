# 自研工具清单

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) 的工具实现细节文档。
> 列出所有需要自研的工具，包含用途、输入/输出规格和当前状态。

---

## 层间工作流服务（最高优先级）

### W1：Coordinator Service（需求层 Workflow Service）
**状态**：✅ 完成（参考实现：`Snowziio/requirement-workflow-feishu`）
**用途**：需求层状态机驱动、Hook 派发、飞书侧项目级上下文管理
**输入**：飞书 IM 事件（群消息、私聊消息、卡片按钮回调）
**输出**：状态迁移 + Hook 执行结果 + Bitable 写入 + 飞书消息推送
**部署**：独立服务，飞书 WebSocket 长连接，端口 8004（staging）

### W2：checkpoint-handler（Harness 层 → 交付层 Workflow Service）
**状态**：✅ 完成
**用途**：卡点1b/2/3 的卡片按钮回调处理，GitHub API 操作，ACM 注册表维护
**输入**：飞书卡片按钮回调事件
**输出**：GitHub API 操作（合并 PR / 触发 workflow）+ Bitable 状态更新
**部署**：独立服务，端口 8002（稳定运行）

---

## 脚本与 CI 工具

### 工具1：飞书通知脚本（`scripts/notify_feishu.py`）
**状态**：✅ 完成
**用途**：GitHub Actions 调用，发送结构化卡点通知到飞书
**输入**：--event（事件类型）、--pr（PR 编号）、--report（报告摘要 JSON 路径）
**输出**：飞书消息卡片（含操作按钮）

### 工具2：AI 失败分析脚本（`scripts/analyze_failure.py`）
**状态**：✅ 完成
**用途**：CI 失败时，自动调用 Claude API 分析测试日志，生成人类可读的失败摘要
**输入**：测试失败日志（stdin 或文件路径）
**输出**：结构化失败分析（原因 + 建议修复方向），写入 PR 评论

### 工具3：客户部署脚本（`deploy/deploy.sh`）
**状态**：✅ 完成
**用途**：参数化部署到任意客户环境，含健康检查和自动回滚
**输入**：客户名称（对应 `deploy/customers/{name}.env`）
**输出**：已运行的客户生产环境

### 工具4：项目交付回顾生成器
**状态**：□ 待建
**用途**：项目交付时，从 Bitable 决策记录表拉取本项目所有记录，生成回顾报告初稿
**输入**：项目名称（从 Bitable 拉取数据）
**输出**：结构化 Markdown 回顾文档初稿

### 工具5：Spec 转化服务
**状态**：□ 待建（Phase 2 关键任务）
**用途**：接收"创建 Spec"指令，将飞书需求文档 + 项目级上下文转化为四层 Spec，提交 GitHub
**输入**：REQ ID + 需求文档飞书 ID + ARCHITECTURE.yaml + ACM 注册表 + 设计系统快照
**输出**：GitHub commit（spec/REQ-{PROJECT}-{NNN}/ 下四层文件）+ 兼容性检查报告
**复杂度**：中（AI 调用 + 多文件生成 + GitHub API 操作）

### 工具6：Harness 生成 workflow（`spec-to-harness.yml`）
**状态**：□ 待建（Phase 3 关键任务）
**用途**：卡点1a 确认后，自动触发 Claude Code CLI 读取 ACM 生成 harness/tests/ 测试代码
**输入**：REQ ID + spec/REQ-{PROJECT}-{NNN}/acceptance.yaml + 历史 harness 目录
**输出**：Harness PR + 覆盖率矩阵文档 + ACM 回填（test_file / test_function）

### 工具7：实现触发 workflow（`harness-confirmed.yml`）
**状态**：□ 待建（Phase 3 关键任务）
**用途**：卡点1b 确认后，合并 harness PR，创建 impl 分支，触发 Claude Code CLI 生成实现代码
**输入**：Harness PR 编号 + REQ ID + 四层 Spec 路径
**输出**：实现 PR（src/ 代码）

### 工具8：ACM 兼容性检查脚本
**状态**：□ 待建（Phase 2）
**用途**：对比新版 ACM 与 ACM 注册表，生成兼容性报告（新增/变更/删除的 AC，breaking changes 列表）
**输入**：新 ACM YAML 文件路径 + spec/registry/consolidated.yaml
**输出**：兼容性报告（JSON），注入卡点1a 飞书卡片

---

## OpenClaw Skills（Agent 能力层）

### 工具9：requirement-writer Skill
**状态**：□ 待建（Phase 2）
**用途**：Author Agent 核心 Skill，引导用户逐字段补全需求，实时写入飞书文档，检查完整度
**输入**：当前需求快照 + 字段进度 + 本轮 author 发言
**输出**：下一引导语 / 下一字段问题 / 是否等待用户
**注意**：需从 ARCHITECTURE.yaml 拉取模块列表供技术范围声明填写

### 工具10：requirement-reviewer Skill
**状态**：□ 待建（Phase 2）
**用途**：Reviewer Agent 核心 Skill，五维度审查（完整性/一致性/可测试性/技术范围/历史冲突）
**输入**：完整需求快照 + 历史约束参考（ACM 注册表摘要）
**输出**：`ai_ready: bool` + 结论摘要 + 各维度打分 + 具体退回原因（ai_ready = false 时）
**退回条件**：输入/输出无字段名；验收标准无可测试格式；技术范围声明任意项为空

### 工具11：ui-design-bridge Skill
**状态**：□ 待建（Phase 2）
**用途**：桥接 UI 设计工具（design.md / UIUX ProMax 等），基于需求生成低保真线框图
**输入**：需求文档 8 字段（含技术范围声明）
**输出**：低保真线框图描述（Markdown），写入飞书文档
**注意**：此 Skill 只负责低保真；高保真原型由工具13 负责

### 工具12：github-bridge Skill
**状态**：□ 待建（Phase 2）
**用途**：在 OpenClaw 中操作 GitHub（创建分支、提交文件、创建 PR、读取 ARCHITECTURE.yaml）
**输入**：操作类型 + 参数（仓库/分支名/文件内容等）
**输出**：GitHub API 操作结果

---

## 项目级上下文基础设施（v1.4 新增）

### 工具13：设计系统文档管理器
**状态**：□ 待建（Phase 2）
**用途**：管理飞书侧项目设计系统文档：创建初始文档、append 新设计决策、导出快照到 GitHub
**操作类型**：
  - create：新建设计系统文档（首个 UI 需求时触发）
  - append：追加新组件记录或设计决策日志
  - export：导出快照到 GitHub `specs/design-system-snapshot.yaml`
**输入**：项目名称 + 操作类型 + 内容
**输出**：飞书文档更新结果 + GitHub 快照文件（export 时）
**触发时机**：UI 设计第二阶段确认（append）；卡点1a 通过（export）

### 工具14：高保真 UI 原型生成 Agent
**状态**：□ 待建（Phase 2）
**用途**：REQ APPROVED 后（needs_ui = true）生成可在浏览器运行的高保真前端原型
**输入**：需求文档 8 字段 + 低保真线框图 + 设计系统文档（Coordinator 注入）
**输出**：可运行前端组件代码（React/Vue），覆盖所有关键视图和状态 + 设计决策说明
**交付**：原型代码写入飞书文档，更新 Bitable 高保真原型链接
**注意**：属于能力层，可替换（v0 / Figma Make / design.md 等）

### 工具15：ACM 注册表维护服务
**状态**：□ 待建（集成到 checkpoint-handler，Phase 2/3）
**用途**：维护 `spec/registry/consolidated.yaml`：追加条目、更新状态、提供兼容性查询接口
**操作**：
  - append：卡点1a 通过时追加新 AC 条目（status: locked）
  - finalize：卡点1b 通过时回填 test_file/test_function，status → finalized
  - query：新 Spec 生成时，返回与技术范围有重叠的历史 AC 条目

### 工具16：视觉回归测试生成器
**状态**：□ 待建（Phase 3）
**用途**：基于 design-ui.md 自动生成 Playwright 视觉回归测试代码
**输入**：design-ui.md（组件树 + 关键视图定义）+ 高保真原型代码（基线来源）
**输出**：`harness/tests/REQ-{PROJECT}-{NNN}/visual/` 下的 Playwright 测试脚本 + 初始截图基线目录

---

## 完成状态汇总

| 分类 | 工具 | 状态 |
|---|---|---|
| 工作流服务 | W1 Coordinator Service | ✅ |
| 工作流服务 | W2 checkpoint-handler | ✅ |
| CI 脚本 | 飞书通知脚本 | ✅ |
| CI 脚本 | AI 失败分析脚本 | ✅ |
| CI 脚本 | 客户部署脚本 | ✅ |
| CI 脚本 | 项目回顾生成器 | □ |
| Spec 生成 | Spec 转化服务 | □ Phase 2 |
| Spec 生成 | ACM 兼容性检查脚本 | □ Phase 2 |
| CI workflow | spec-to-harness.yml | □ Phase 3 |
| CI workflow | harness-confirmed.yml | □ Phase 3 |
| Agent Skills | requirement-writer | □ Phase 2 |
| Agent Skills | requirement-reviewer | □ Phase 2 |
| Agent Skills | ui-design-bridge | □ Phase 2 |
| Agent Skills | github-bridge | □ Phase 2 |
| 项目上下文 | 设计系统文档管理器 | □ Phase 2 |
| 项目上下文 | 高保真 UI 原型生成 Agent | □ Phase 2 |
| 项目上下文 | ACM 注册表维护服务 | □ Phase 2/3 |
| 项目上下文 | 视觉回归测试生成器 | □ Phase 3 |
