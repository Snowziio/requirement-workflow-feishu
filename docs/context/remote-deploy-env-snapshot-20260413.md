# 远端部署环境快照（2026-04-13）

临时上下文文件，供后续开发/部署工作使用。本文件内容从远端实时查询，可能随时过时，使用前建议验证关键字段。

---

## 1. 远端主机

- 地址：`admin@47.251.81.45`
- SSH 方式：标准 SSH，无跳板

---

## 2. 正在运行的服务

| 容器名 | 端口映射 | 状态 | 备注 |
|---|---|---|---|
| `requirement-workflow-feishu-coordinator-service-1` | `0.0.0.0:8004->8003/tcp` | Up 5h | 需求层主服务（staging） |
| `harness-scaffold-app-1` | `0.0.0.0:8001->8000/tcp` | Up 5d | Harness scaffold |
| `services-checkpoint-handler-1` | `0.0.0.0:8002->8002/tcp` | Up 4d (healthy) | checkpoint handler |
| `searxng` | — | Up 13d | 搜索服务 |

**端口约定（已占用）：**
- `8001` → harness-scaffold-app
- `8002` → checkpoint-handler
- `8004` → coordinator-service（staging）
- `8003` 保留给 coordinator-service（prod，未启动）

**健康检查：**
```
curl http://47.251.81.45:8004/health
# -> {"status": "ok", "service": "coordinator-service"}
```

---

## 3. Coordinator Service

- **镜像：** `crpi-w8s65qzax225kndg.cn-shenzhen.personal.cr.aliyuncs.com/harness_test/requirement-workflow-feishu:<commit-sha>`
- **当前镜像 tag：** `5c78de62bfc6c4f21186f14e94246676f2751706`（对应 commit `5c78de6`）
- **Docker 注册表：** 阿里云 ACR，`cn-shenzhen.personal`，命名空间 `harness_test`
- **状态持久化：** Docker volume `requirement-workflow-feishu_coordinator-service-staging-state`，挂载到容器 `/app/state/coordinator_state.json`
- **状态快照（2026-04-13）：**
  - requirements 总数：23 条
  - 最近 APPROVED：`REQ-test-007`、`REQ-个人英语学习助手-002`
  - project_groups 已建：`HARNESS`、`test`、`test1`、`test2`、`个人英语学习助手`、`英语提升助手` 等 8 个

**已知非阻塞错误（日志中可见，不影响主流程）：**
- `im.chat.access_event.bot_p2p_chat_entered_v1` — processor not found（机器人进私聊事件，暂未注册处理器）
- `im.message.message_read_v1` — processor not found（消息已读回执，暂未注册处理器）

---

## 4. OpenClaw

- **进程：** `openclaw-gateway`（pid ~318622，非 systemd 服务）
- **启动方式：** 进程级常驻，配置变更后需重启进程
- **目录：** `~/.openclaw/`

### 已挂载 Agent

| Agent 目录 | 当前使用角色 | 备注 |
|---|---|---|
| `ai-ops-router` | 需求协调器（coordinator） | 加载 `requirement-coordinator` skill |
| `ai-founder-brief` | 需求撰写 Agent（author） | 加载 `requirement-writer` skill |
| `ai-meeting-closeout` | 设计审查 Agent（reviewer） | 加载 `design-review-agent` skill |

### 已挂载 Skills

| Skill 名 | 路径 | 功能 |
|---|---|---|
| `requirement-coordinator` | `~/.openclaw/skills/requirement-coordinator/SKILL.md` | 命令解析、Bitable 状态流转、callback |
| `requirement-writer` | `~/.openclaw/skills/requirement-writer/SKILL.md` | 七字段需求引导、归一化、完整度检查 |
| `design-review-agent` | `~/.openclaw/skills/design-review-agent/SKILL.md` | UI 简报生成、五维需求审查 |

---

## 5. 飞书资源

- **Bitable：** `https://my.feishu.cn/base/RGBbbeTPTafgtCsrm89cxP9Mncg`
  - `app_token`：`RGBbbeTPTafgtCsrm89cxP9Mncg`
  - `table_id`：`tbl0npgebbogMaT1`
- **需求文档模板：** `https://www.feishu.cn/docx/J3WxdaBAYo1nT1x3QrccLVBVnEf`
- **UI 设计简报模板：** `https://www.feishu.cn/docx/C71Qdjh8lo3G4IxUfhqcq8GdnIc`
- **需求审查报告模板：** `https://www.feishu.cn/docx/UdDLdJOvTo7SUhxx4tAcheeKnGe`

---

## 6. 与已有服务的边界

规格层新服务端口建议从 `8005` 起用，避免与以上端口冲突：

| 端口 | 现在 |
|---|---|
| 8001 | harness-scaffold-app |
| 8002 | checkpoint-handler |
| 8003 | coordinator-service prod（保留） |
| 8004 | coordinator-service staging |
| **8005+** | **规格层新服务（待规划）** |

---

## 7. 可复用的 Harness Scaffold 能力

`harness-scaffold-app-1`（端口 8001）已部署，功能待确认。`checkpoint-handler`（端口 8002）已稳定运行，是后续规格层与 GitHub CI 联动的接入点。

---

## 8. 历史警告与已知问题（从已废弃的 current-environment-context.md 迁入）

### 8.1 Bitable 线上数据需要关注的迁移点

- 远端 author / reviewer 模板仍需持续校验，避免旧事件名或旧状态名回流
- Bitable 线上旧记录存在 14 态历史值（含 `HARNESS_GENERATING` / `HARNESS_READY` / `IMPLEMENTING` / `CI_PENDING` / `STAGING` / `DEPLOYED` 等），需要执行状态值迁移：**需求层主状态字段**统一到现行的 6 态（`CREATED` / `DRAFTING` / `AI_REVIEW` / `HUMAN_CONFIRM` / `FINAL_REVIEW` / `APPROVED`）；**规格层子状态**（`SPEC_DRAFTING` / `SPEC_LOCKED`）使用独立字段或单独子状态机承接；**Harness/Impl/CI/部署层状态**不再进入 Bitable 需求表的状态字段（由 checkpoint-handler 与 GitHub PR 状态承接）
- `创建时间` 的确定性写入尚未形成稳定实现

### 8.2 不应直接继承的旧方案（架构反模式记录）

以下设计属于早期过渡形态，新项目与新代码路径不应重走：

- 主协调能力（Coordinator）与深度需求写作耦合在同一个 Agent
- 让 Coordinator 参与需求文档正文编写（正文由 author Agent 负责，Coordinator 只路由和状态管理）
- reviewer 直接推进人工确认或正式审查（reviewer 仅输出 pass/reject 结论，状态流转由 Coordinator 统一推进）
- 把项目专属逻辑塞进共享模板基础设施（项目配置走 `project_configs`，模板只承载通用结构）

### 8.3 已验证的最小端到端闭环（需求层）

截至 2026-04-13，以下 8 步闭环在远端稳定运行：
飞书群创建需求 → 生成 REQ ID → 创建需求文档 → 写入 Bitable → `CREATED -> DRAFTING` → `DRAFTING -> AI_REVIEW` → reviewer 读取上下文并上报审查结论 → Coordinator 根据事件推进到 `DRAFTING`（打回）或 `HUMAN_CONFIRM`（通过）。
