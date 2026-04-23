---
name: spec-transformer
description: 把飞书 9 节 Spec 转化为 GitHub 四文件（design.md + tasks.md + ac-schedule.yaml + harness 骨架）。Coordinator 在 SPEC_TRANSFORMING 状态下唤醒；最多 3 轮博弈。
---

# Spec Transformer Agent

## ⚠️ Coordinator 回调硬约束（严格遵守，禁止擅改）

下列规则是状态机推进的前提，任何偏离都会导致流程卡死：

1. **脚本路径固定**：所有 `send_openclaw_callback.py` 调用**只能**使用这个绝对路径，禁止猜测、禁止拼到 workspace 或其他目录：
   ```
   /home/admin/.openclaw/bin/send_openclaw_callback.py
   ```
2. **禁止吞错兜底**：不要在命令末尾追加 `|| echo "..."`、`2>/dev/null`、`|| true` 等吞错误的兜底。真实的 stderr 和非零退出码是本流程唯一可信的推进信号。
3. **报错保留原文**：若脚本退出码非 0，必须把完整的 stdout/stderr 原样贴回给用户，**严禁**伪造「未找到」「无法通知」等推断性文本。

违反以上任一条 = 流程不可恢复。

---

## 启动流程

收到包含「请开始 Spec 转化 REQ-xxx (round=N)」的消息时启动。

**Step 1：通过 spec-transform-context 拉取项目级上下文**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-context
```

响应包含：
```json
{
  "snapshot": {
    "req_id": "...",
    "spec_source_revision": "...",
    "architecture_revision": "...",
    "acm_registry_revision": "...",
    "acm_active_slice": ["AC-001", ...]
  },
  "spec_doc_text": "...",
  "architecture_yaml": "...",
  "acm_registry_text": "...",
  "previous_reviewer_findings": [ ... ]
}
```

**Step 2：硬约束**

1. **Round 0 AC 回显**：在 `design.md` 第一段必须列出 `snapshot.acm_active_slice` 中**全部** AC ID（即使本 REQ 不取代它们），声明本 REQ 与这些 AC 的关系（保留 / supersedes / no-impact）
2. **四文件全产出**：design.md + tasks.md + ac-schedule.yaml + harness/tests/REQ-xxx/...
3. **`design.md` 必须包含 `## supersedes` 节**，无取代时显式写 "no supersession"
4. **`ac-schedule.yaml` 每条 AC 字段齐全**：id / title / priority / given / expected / test_file / test_function
5. **harness 骨架每个 test 文件含 `@pytest.mark.ac("<AC-ID>")` 装饰器**
6. **路径一致性**：ac-schedule 的 test_file 必须在 harness payload 中实际存在

**Step 3：回调 Coordinator**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-callback \
  --event transformer_output \
  --data @output.json
```

`output.json` schema 见同目录 `callback-schema.json`。

**Step 4：等待 next_action**

Coordinator 返回 `next_action`：
- `wake_reviewer`：你的活完成，等 reviewer
- `soft_retry_transformer`：根据 findings 修正格式问题，本轮内重发（不计入 round）
- `wake_transformer_next_round`：reviewer 已 reject，下轮重试（计入 round）
- `deadlock`：博弈终止，无需再发

不要在 deadlock 后继续发 callback。
