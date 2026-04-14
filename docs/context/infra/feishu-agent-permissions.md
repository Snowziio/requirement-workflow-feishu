# 飞书 Agent 权限配置方案

> 本文记录 OpenClaw 体系中各 Agent 在飞书开放平台所需的权限配置，包含每个 Agent 的应用权限清单、Token 类型选择依据、以及授权配置步骤。

---

## 一、背景概念

### 1.1 Token 类型说明

飞书开放平台有两种核心 Token 类型，Agent 使用哪种 Token 决定了操作以谁的身份执行。

| 类型 | 获取方式 | 代表身份 | 典型用途 |
|------|----------|----------|----------|
| `tenant_access_token` | 应用 AppID + AppSecret 换取，无需用户登录 | 机器人应用本身 | 发送机器人消息、管理文档（以应用为所有者）、读写 Bitable |
| `user_access_token` | OAuth 授权流程，需用户扫码登录 | 具体用户 | 以用户身份操作文档、访问用户授权才可见的资源 |

**OpenClaw Agent 当前使用 `tenant_access_token`**（应用级别 Token），所有操作以机器人身份执行。这意味着：

- 机器人创建的文档，所有者是机器人（需手动分享给团队成员）
- 机器人发送的消息以机器人头像显示
- 不需要用户登录，适合无人值守的自动化流程

### 1.2 权限范围（Scope）概念

飞书权限分两种：

- **应用权限**（API 权限）：控制应用能调用哪些 API，在飞书开放平台「应用 → 权限管理」配置
- **资源级权限**：控制应用能访问哪些具体资源（如某个文档、某个群），在资源本身配置（如文档分享、将机器人添加到群）

两者都需要配置，缺一不可。

### 1.3 "授权请求卡片"机制

当 OpenClaw Agent 调用工具（如 `feishu_fetch_doc`）时，如果当前应用缺少对应的 API 权限，飞书网关会向会话发送一张**授权请求卡片**，要求用户手动授权。

**这是设计上的降级机制**，正式配置后不应出现。若 Agent 初次使用时频繁收到授权卡片，说明该应用未预先在开放平台申请对应权限。

---

## 二、各 Agent 权限清单

### 2.1 spec-author（Spec 撰写助手）

**用途**：读取需求文档、撰写 Spec 文档、调用 Coordinator 回调。

| 权限 Scope | 用途 | 必须/可选 |
|------------|------|-----------|
| `docx:document` | 读写飞书文档（读需求文档、写 Spec 文档） | **必须** |
| `im:message` | 接收私聊/群消息中的触发指令 | **必须** |
| `im:message:send_as_bot` | 发送回复消息 | **必须** |

**不需要的权限**：
- `bitable:app`：不允许直接操作 Bitable，所有状态更新通过 Coordinator 回调完成
- `im:chat`：不需要主动管理群

**资源级权限**：
- 需要文档空间（需求文档所在 Space）将 spec-author 机器人添加为成员，否则无法读取需求文档

---

### 2.2 spec-reviewer（Spec 审查助手）

**用途**：读取 Spec 文档和需求文档、执行多维度审查、调用 Coordinator 回调。

| 权限 Scope | 用途 | 必须/可选 |
|------------|------|-----------|
| `docx:document` | 读取 Spec 文档和需求文档（只读） | **必须** |
| `im:message` | 接收审查触发消息 | **必须** |
| `im:message:send_as_bot` | 发送审查结论消息 | **必须** |
| `search:docs:read` | 通过 `feishu_search_doc_wiki` 搜索文档（若审查中需要检索相关文档） | **可选** |

**不需要的权限**：
- `bitable:app`：不允许直接操作 Bitable
- `docx:document`（写权限）：审查助手只读文档，不修改文档

**资源级权限**：
- 需要文档空间将 spec-reviewer 机器人添加为成员（只读）

---

### 2.3 requirement-author（需求撰写助手）

**用途**：接收需求信息、撰写需求文档、调用 Coordinator 回调。

| 权限 Scope | 用途 | 必须/可选 |
|------------|------|-----------|
| `docx:document` | 创建和写入需求文档 | **必须** |
| `im:message` | 接收/发送群消息（需求创建群中的交互） | **必须** |
| `im:message:send_as_bot` | 发送需求撰写进度消息 | **必须** |
| `im:chat` | 读取所在群的基本信息（如群名、成员列表） | **可选** |

**不需要的权限**：
- `bitable:app`：需求文档由 Coordinator 负责写入 Bitable

---

### 2.4 requirement-reviewer（需求审查助手）

**用途**：读取需求文档、按维度审查、调用 Coordinator 回调。

| 权限 Scope | 用途 | 必须/可选 |
|------------|------|-----------|
| `docx:document` | 读取需求文档 | **必须** |
| `im:message` | 接收/发送消息 | **必须** |
| `im:message:send_as_bot` | 发送审查结论 | **必须** |

**不需要的权限**：
- `bitable:app`：不允许直接操作 Bitable

---

### 2.5 ai-ops-router（需求协调器 / Coordinator Agent）

**用途**：路由消息到正确的 Agent、读取群信息、触发各类工作流。该 Agent 是系统的入口，权限最广。

| 权限 Scope | 用途 | 必须/可选 |
|------------|------|-----------|
| `im:message` | 监听所有群/私聊消息 | **必须** |
| `im:message:send_as_bot` | 发送通知卡片、引导消息 | **必须** |
| `im:chat` | 读取群信息（群 ID、成员列表等） | **必须** |
| `contact:user.id:readonly` | 获取用户 open_id（用于私聊通知、@用户） | **必须** |
| `bitable:app` | 读写需求追踪 Bitable（状态同步） | **必须** |
| `docx:document` | 创建 Spec 文档（spec_start 时） | **必须** |

**注意**：ai-ops-router 是唯一允许操作 Bitable 的 Agent 对应的飞书应用，其他 Agent 的飞书应用不配置 `bitable:app` 权限，从权限侧杜绝直接操作。

---

## 三、各 Agent 对应飞书应用配置汇总

| Agent | 飞书应用 AppID | 关键权限 | 是否允许写 Bitable |
|-------|--------------|----------|-------------------|
| spec-author | `cli_a954a1cc87f89ccb` | `docx:document`, `im:message` | ❌ 不允许 |
| spec-reviewer | `cli_a954a32d62f89bef` | `docx:document`（只读）, `im:message` | ❌ 不允许 |
| requirement-author（ai-founder-brief） | 待填写 | `docx:document`, `im:message` | ❌ 不允许 |
| requirement-reviewer（ai-meeting-closeout） | 待填写 | `docx:document`（只读）, `im:message` | ❌ 不允许 |
| coordinator（ai-ops-router） | 待填写 | 全部权限 | ✅ 允许 |

---

## 四、飞书开放平台权限配置步骤

### 4.1 为应用申请 API 权限

1. 登录 [飞书开放平台](https://open.feishu.cn/app)
2. 选择对应的自建应用
3. 左侧菜单「权限管理」→「API 权限」
4. 搜索并添加所需 Scope（如 `docx:document`）
5. 点击「申请权限」→ 填写申请理由
6. **发布应用版本**：权限申请后需要创建新版本并发布，权限才会生效

### 4.2 将机器人添加到文档空间

操作文档前，必须将机器人加入文档或文档所在 Space：

1. 打开目标飞书文档
2. 右上角「分享」→「邀请成员」
3. 搜索机器人应用名称（如"spec-author"）
4. 设置权限（读写或只读）→ 确认

对于文档 Space（知识库）：
1. 进入知识库设置
2. 「成员管理」→「添加成员」
3. 添加对应机器人并设置权限

### 4.3 将机器人添加到飞书群

1. 进入目标群聊
2. 右上角「设置」→「群机器人」→「添加机器人」
3. 搜索并添加对应应用的机器人

**推荐做法**：将各 Agent 机器人统一添加到项目群，避免后续频繁授权。

---

## 五、预授权检查清单

部署新 Agent 后，在正式使用前按以下清单确认权限：

```
□ 飞书开放平台已为该应用添加所有必需 Scope
□ 已创建新版本并发布（版本未发布则权限不生效）
□ 机器人已加入需求文档所在的文档 Space（或已单独分享文档）
□ 机器人已加入需求创建群和项目群
□ 在飞书私聊该机器人发送一条测试消息，确认机器人有响应
□ 触发一次 feishu_fetch_doc 调用，确认无"授权请求卡片"弹出
□ 若出现授权请求卡片，检查权限配置后重新发布应用版本
```

---

## 六、常见问题

### Q1：Agent 频繁发送"授权请求卡片"

**原因**：应用未申请对应 API Scope，或申请后未发布新版本。

**处理**：
1. 在开放平台检查权限列表
2. 确认该 Scope 状态为"已获取"（不是"申请中"）
3. 检查应用是否已发布最新版本

### Q2：spec-author 调用 feishu_fetch_doc 读取需求文档失败

**原因**：spec-author 机器人未被添加到文档所在 Space 或文档本身未分享给机器人。

**处理**：在需求文档（或其所在 Space）将 spec-author 机器人添加为成员（至少只读权限）。

### Q3：spec-reviewer 的 feishu_search_doc_wiki 无结果

**原因**：缺少 `search:docs:read` 权限，或机器人无法访问搜索目标 Space。

**处理**：在开放平台为 spec-reviewer 应用添加 `search:docs:read` 权限并发布新版本。

### Q4：各 Agent 能否复用同一个飞书应用？

**技术上可以**，但不推荐。每个 Agent 使用独立飞书应用的优势：
- 权限最小化：spec-reviewer 应用完全不配置写权限，从源头防止误操作
- 身份区分：在文档协作历史和群消息中可以区分不同 Agent 的操作
- 故障隔离：单个 Agent 的 AppSecret 泄露不影响其他 Agent

**如果资源有限**，至少将 coordinator（ai-ops-router）和其他 Agent 使用不同应用，因为 coordinator 是唯一需要 Bitable 写权限的角色。
