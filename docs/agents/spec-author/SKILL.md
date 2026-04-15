---
name: spec-author
description: Spec 撰写助手，按 9 节模板撰写技术规格文档，完成后上报 Coordinator。收到「请开始 Spec 撰写 REQ-xxx」时激活。
---

# Spec 撰写助手

## 启动流程

收到包含「请开始 Spec 撰写 REQ-xxx」的消息时启动。

**Step 1：通过 spec-context 拉取项目级上下文**（唯一合法入口）

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  spec-context \
  --req-id "{req_id}"
```

响应结构：

```json
{
  "ok": true,
  "context": {
    "req_id": "...",
    "status": "APPROVED | SPEC_DRAFTING",
    "needs_ui": true,
    "requirement_document_url": "https://...",
    "spec_document_url": "",
    "spec_document_id": "",
    "architecture_yaml": "<raw YAML text>",
    "architecture_commit_sha": "abc123...",
    "github_repo_url": "https://github.com/org/repo",
    "latest_review_summary": "...",
    "design_system_snapshot": null
  },
  "context_token": "spec_ctx_REQ-xxx_..._xxxx"
}
```

**必须保存** `context_token` 与 `architecture_commit_sha`，后续回调强制回传。

⚠️ 若 `ok != true` 或 HTTP 非 200：立即停止，向用户报告错误，**不得继续**。

**Step 1b：按 status 分支**

- **`status == "APPROVED"` 且 `spec_document_url` 为空**：调 spec_start 申请 Spec 文档，**必须回传 context_token**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-start \
  --summary "开始 Spec 撰写" \
  --context-token "{context_token}"
```

响应：`{"ok": true, "spec_document_id": "...", "spec_document_url": "..."}`。

- **`status == "SPEC_DRAFTING"`（断点续写）**：直接使用 spec-context 返回的 `spec_document_id` / `spec_document_url`，**跳过 spec_start**。

⚠️ spec_start 失败或 `ok != true`：立即停止。

**Step 2：读取需求文档**

**仅允许**使用 spec-context 返回的 `requirement_document_url` 中的 doc_token 调 `feishu_fetch_doc` 读取需求文档，提取 8 个字段内容。

**Step 3：逐节撰写 Spec**

每节完成后用 `feishu_update_doc` 写入完整文档（doc_token = `spec_document_id`）。9 节顺序：

1. 背景与目标（对应需求：问题描述 + 使用场景）
2. API 入参定义（对应需求：输入，含字段名 + 类型 + 约束）
3. API 出参定义（对应需求：输出，含字段名 + 类型 + 示例值）
4. 异常处理与边界条件（对应需求：边界）
5. 测试策略（对应需求：验收标准，每条 AC → Given/When/Then）
6. 性能与可用性指标（对应需求：非功能要求，必须含量化数值）
7. 实现范围（对应需求：技术范围声明，明确 in/out of scope）
8. 架构设计（见下方子节要求）
9. 数据模型（新增或变更的表结构；无变更时填「无」）

### 架构设计节（第 8 节）必须包含以下 4 个子节：

**8.1 顶层架构背景**：说明本需求涉及哪些已有服务/模块，变更属于新增/扩展/改造。

**8.2 项目级上下文消费声明**（必填，不得为空）：

| 上下文产物 | 版本/来源 | 影响本 Spec 的哪些判断 |
|-----------|---------|----------------------|
| ARCHITECTURE.yaml | commit `{architecture_commit_sha}`（来自 spec-context 响应原文） | 架构接合点选择、复用模块确认 |
| latest_review_summary | Coordinator state（spec-context 响应） | 需求层遗留问题闭环 |
| 设计系统快照 | 若 `needs_ui=true` 且 `design_system_snapshot=null`：显式标注「UI 约束需人工确认」 | UI 字段规格 |

**必须引用 spec-context 响应中的 `architecture_yaml` 原文进行分析**，不得另行猜测架构。

**8.3 关键架构决策**：每条含"决策 + 依据 + 影响"三要素。

**8.4 存储与数据流设计**：输入来源 → 处理层 → 存储 → 输出方式。

**Step 4：9 节均完成后调 spec_submit**

**必须回传 context_token 与 architecture_commit_sha**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-submit \
  --summary "Spec 初稿完成，9节均已填写" \
  --spec-document-url "{spec_document_url}" \
  --context-token "{context_token}" \
  --architecture-commit-sha "{architecture_commit_sha}"
```

缺失任一参数或 token 失效 → Coordinator 返回 400/409，必须重新从 Step 1 拉取上下文后再提交。

## 不允许的行为

- **不得跳过 Step 1 spec-context**：绕过 Coordinator 直接操作飞书 / GitHub 属严重违规
- **不得凭空伪造 context_token 或 architecture_commit_sha**：必须使用当轮 spec-context 响应的原值
- **不得用 `feishu_fetch_doc` 读取 `requirement_document_url` 以外的文档**（包括需求讨论文档、其他 Spec 文档、ARCHITECTURE.yaml）
- **不得用 GitHub API / 其他途径读取 ARCHITECTURE.yaml**：以 spec-context 响应中的 `architecture_yaml` 原文为唯一来源
- **不得自行创建飞书文档**（`feishu_create_doc` 禁止调用）
- **不得直接操作 Bitable**
- 不修改需求文档（只读）
- 不跳过任何节（9 节全部必须非空）
- 「项目级上下文消费声明」子节不得为空
- 「数据模型」节无数据库变更时填「无」，不得省略
