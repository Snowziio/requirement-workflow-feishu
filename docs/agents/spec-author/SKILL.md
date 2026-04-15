---
name: spec-author
description: Spec 撰写助手，按 9 节模板撰写技术规格文档，并演化项目级 ARCHITECTURE 飞书文档。收到「请开始 Spec 撰写 REQ-xxx」时激活。
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
    "name": "...",
    "project": "...",
    "category": "saas-ai-automation",
    "status": "APPROVED | SPEC_DRAFTING",
    "needs_ui": true,
    "requirement_document_url": "https://feishu.../doc_req",
    "architecture_doc_url": "https://feishu.../doc_arch",
    "architecture_doc_revision": "rev-7",
    "template_version": "saas-ai-automation.v1",
    "spec_document_url": "",
    "spec_document_id": "",
    "latest_review_summary": "...",
    "design_system_snapshot": null
  },
  "context_token": "spec_ctx_REQ-xxx_..._xxxx"
}
```

**必须保存** `context_token`。`architecture_doc_revision` 是进入时的 revision，最终回传时必须是**写回后**的新 revision。

若返回 `ok != true` 或 HTTP 非 200：立即停止。若错误码为 `concurrent_spec_in_progress`：通知用户稍后重试，不得自行循环轮询。

**Step 1b：按 status 分支**

- **`APPROVED` 且 `spec_document_url` 为空**：调 spec_start，**必须回传 context_token**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-start \
  --summary "开始 Spec 撰写" \
  --context-token "{context_token}"
```

- **`SPEC_DRAFTING`（断点续写）**：直接使用 spec-context 返回的 `spec_document_id` / `spec_document_url`，跳过 spec_start。

**Step 2：读取需求文档与当前 ARCHITECTURE 快照**

- 用 `feishu_fetch_doc` 读取 `requirement_document_url` 获取需求 8 字段。
- 用 `feishu_fetch_doc` 读取 `architecture_doc_url` 获取项目当前 ARCHITECTURE YAML 文本（作为背景信息与增量合并底本）。

**禁止**用其它途径（GitHub、缓存副本、人工贴入）获取 ARCHITECTURE。

**Step 3：逐节撰写 Spec**

每节完成后用 `feishu_update_doc` 写入 spec 文档（doc_token = `spec_document_id`）。9 节顺序：

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
| ARCHITECTURE YAML | `architecture_doc_url` 进入时 revision `{architecture_doc_revision}` | 架构接合点选择、复用模块确认 |
| latest_review_summary | Coordinator state（spec-context 响应） | 需求层遗留问题闭环 |
| 设计系统快照 | 若 `needs_ui=true` 且 `design_system_snapshot=null`：显式标注「UI 约束需人工确认」 | UI 字段规格 |

本子节必须**引用 Step 2 读到的 YAML 原文**做分析，严禁凭空猜测架构。

**8.3 关键架构决策**：每条含"决策 + 依据 + 影响"三要素。

**8.4 存储与数据流设计**：输入来源 → 处理层 → 存储 → 输出方式。

**Step 3b：演化 ARCHITECTURE YAML（Spec 的核心产出之一）**

- 基于 Step 2 读到的当前 YAML 与本次 Spec 的 8.3 / 8.4，识别本 REQ 引入的架构增量：
  - 新增 / 修改的模块
  - 新增 / 修改的服务
  - 新增 / 修改的数据模型
  - 新增的外部依赖
- 在本地合并：原 YAML + 增量 → 新版 YAML。保留原有条目，仅新增/修订增量涉及部分。
- 调 `feishu_update_doc` 将新版 YAML 覆盖写回 `architecture_doc_url`（doc_token = `architecture_doc_id`）。
- 写回完成后，**调 spec-context 再次读取**获取**写后的 `architecture_doc_revision`**，保留供 Step 4 回传。

**Step 4：9 节均完成且 ARCHITECTURE 已写回后调 spec_submit**

**必须回传 context_token 与写后 architecture_doc_revision**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-submit \
  --summary "Spec 初稿完成，9节均已填写；ARCHITECTURE 已演化" \
  --spec-document-url "{spec_document_url}" \
  --context-token "{context_token}" \
  --architecture-doc-revision "{post_write_revision}"
```

缺失任一参数或 token 失效 → Coordinator 返回 400/409，必须重新从 Step 1 拉取上下文后再提交。

## 不允许的行为

- **不得跳过 Step 1 spec-context**：绕过 Coordinator 直接操作飞书属严重违规
- **不得凭空伪造 context_token 或 architecture_doc_revision**：必须使用端点响应的原值
- **不得用 `feishu_fetch_doc` 读取上述两条 URL 以外的文档**（包括其他 Spec 文档、其他项目的 ARCHITECTURE）
- **不得用 GitHub / 本地副本读取 ARCHITECTURE**：项目级 ARCHITECTURE 的唯一来源是 `architecture_doc_url`
- **不得自行创建飞书文档**（`feishu_create_doc` 禁止调用，spec 文档由 spec_start 创建，ARCHITECTURE 文档由 Coordinator 在首条 REQ 时创建）
- **不得直接操作 Bitable**
- 不修改需求文档（只读）
- 不跳过任何节（9 节全部必须非空）
- 不得把 ARCHITECTURE 演化放到 Step 3 之前（必须先读原文再增量合并；覆盖写前确保未漏既有模块）
