# 飞书基础设施配置

> 本文描述方法论所需的飞书侧基础设施配置，包含应用权限、OpenClaw 配置、Bitable 初始化、消息卡片模板等。

---

## 一、飞书自建应用权限清单

Coordinator Service 使用的飞书应用需要以下权限：

| 权限 | 用途 |
|---|---|
| im:message | 发送/接收 IM 消息（群消息、私聊） |
| im:message:send_as_bot | 以机器人身份发送消息 |
| im:chat | 读取群信息 |
| bitable:app | 读写多维表格 |
| docx:document | 读写飞书文档 |
| contact:user.id:readonly | 获取用户 ID |

checkpoint-handler 使用的飞书应用（可复用同一应用）：

| 权限 | 用途 |
|---|---|
| im:message | 发送卡点通知卡片 |
| bitable:app | 更新需求状态字段 |

---

## 二、OpenClaw 配置

### Agent 挂载清单

| OpenClaw Agent | 当前使用角色 | 挂载的 Skills |
|---|---|---|
| ai-ops-router | 需求协调器（coordinator） | requirement-coordinator Skill（路由逻辑） |
| ai-founder-brief | 需求撰写 Agent（author） | requirement-writer Skill |
| ai-meeting-closeout | 设计审查 Agent（reviewer） | requirement-reviewer Skill |

### Skills 安装清单

| Skill 名 | 类型 | 用途 |
|---|---|---|
| feishu-doc | 官方 | 读写飞书文档，Markdown ↔ 飞书格式转换 |
| feishu-bitable-creator | 官方 | 创建和管理 Bitable 表 |
| feishu-automation | 官方 | 文档模板操作、变更通知 |
| requirement-writer | 自定义 | 需求模板引导、完整度检查 |
| requirement-reviewer | 自定义 | 五维度需求审查 |
| ui-design-bridge | 自定义 | UI 设计工具桥接（低保真线框图） |
| github-bridge | 自定义 | GitHub API 封装 |

---

## 三、Bitable 多维表格初始化

### 需求追踪表（主表）

参见 [../layers/requirement-layer.md](../layers/requirement-layer.md) §五 的完整字段清单。

建表步骤：
1. 从 `bitable_schema_v12.json`（仓库根目录）自动创建（如有建表脚本）
2. 创建视图：
   - **看板视图**：按"状态"分组，快速看各状态下的需求
   - **项目视图**：按"项目"筛选，查看单个项目的所有需求
   - **待处理视图**：筛选"当前卡点 ≠ 无"的需求，查看当前阻塞点

### 决策记录表

| 字段 | 类型 | 说明 |
|---|---|---|
| req_id | 文本 | 关联的 REQ ID |
| 卡点类型 | 单选 | 1a 方案门 / 1b Harness 门 / 2 质量门 / 3 发布门 |
| 决策 | 单选 | 通过 / 打回 / 附条件通过 |
| 决策时间 | 日期时间 | |
| 决策人 | 人员 | |
| 理由与背景 | 文本 | |
| AI 干预点 | 文本 | 本次 AI 生成中哪里需要人工修正（CLAUDE.md 改进的输入） |
| 结果反馈 | 文本 | 后续发现这个决策是否正确（交付后填写） |

---

## 四、飞书消息卡片模板清单

### 需求审查通过通知（需求层 → 规格层衔接）

```
REQ-{ID} {需求名称} 审查已通过

需求文档：[查看文档链接]
审查报告：[查看报告链接]
UI 设计稿：[查看链接]（如有）

进入规格层请执行：
@Coordinator 创建Spec REQ-{ID}

或手动创建 Spec 分支并提交 PR。
```

### 卡点1a 方案门卡片

```
[卡点1a · 方案门] REQ-{ID} {需求名称} · Spec PR #{N}

Design 层预览：
  接口：{方法} {路径}
  数据模型变更：{表名}（{字段数}字段）
  架构接合：{模块} {操作}
  兼容性：{无影响 / N 个历史 AC 受影响}

ACM 验收标准（{N} 条，其中 P0：{M} 条）：
  {AC-001} [P0] {标题}
  {AC-002} [P0] {标题}
  ...

[查看完整 Spec PR] [确认提交] [返回修改]
```

### 卡点1b Harness 门卡片

```
[卡点1b · Harness 门] REQ-{ID} {需求名称} · Harness PR #{N}

覆盖率：{N}/{M} AC 全覆盖
  {AC-001} [P0] → {测试文件}::{测试函数} ✅
  {AC-002} [P0] → {测试文件}::{测试函数} ✅
  ...

历史回归：{N/A（首版）/ N 个历史 REQ 全通过}
视觉回归：{N/A / {N} 个视图已建立基线}

[查看 Harness PR] [确认 Harness] [打回重生成]
```

### 卡点2 质量门卡片（CI 通过）

```
[卡点2 · 质量门] REQ-{ID} {需求名称} · Impl PR #{N}

CI 结果：全绿 ✅
  P0 测试：{N}/{N} 通过
  历史回归：全部通过
  覆盖率：{N}%

[查看 Impl PR] [合并 PR] [拒绝并注释]
```

### 卡点2 质量门卡片（CI 失败）

```
[卡点2 · 质量门] REQ-{ID} {需求名称} · Impl PR #{N}

CI 结果：失败 ❌
失败摘要（AI 分析）：
  {AI 生成的失败原因摘要，2-3 句}

自修复状态：已尝试 {N}/3 轮
下一步建议：{AI 建议的修复方向}

[查看 CI 报告] [查看 Impl PR] [通知 AI 继续修复]
```

### 卡点3 发布门卡片

```
[卡点3 · 发布门] REQ-{ID} {需求名称}

Staging 环境已就绪：
  地址：{Staging URL}
  Smoke Test：全通过 ✅

[访问 Staging] [发布到客户环境] [打回修改]
```

---

## 五、飞书文档空间初始化

参见 [../layers/requirement-layer.md](../layers/requirement-layer.md) §七 的飞书文档目录结构。

初始化步骤：
1. 创建项目文档空间，按需求文档目录结构建立文件夹
2. 创建需求文档模板（含历史约束参考占位区，section 标题与模板规范一致）
3. 创建 UI 设计简报模板
4. 创建项目设计系统文档（首次 UI 需求时，由工具13 自动创建）
5. 设置权限：仅内部成员可见

---

## 六、飞书机器人配置

### Coordinator Service 机器人
- 加入需求创建群、所有项目群
- WebSocket 连接（非 Webhook），监听所有 IM 事件
- 当前部署：`admin@47.251.81.45:8004`（staging）

### checkpoint-handler 机器人
- 加入所有项目群（接收卡点卡片按钮回调）
- 配置 Webhook 地址（供 GitHub Actions 调用发送通知）
- 当前部署：`admin@47.251.81.45:8002`（稳定运行）
