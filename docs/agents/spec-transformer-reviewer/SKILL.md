---
name: spec-transformer-reviewer
description: 评审 spec-transformer 产出的四文件，按五维度判定 verdict ∈ {converged, reject}。
---

# Spec Transformer Reviewer Agent

## 启动流程

收到包含「请评审 Spec 转化产出 REQ-xxx (round=N)」时启动。

**Step 1：拉取本轮 transformer 产出 + snapshot**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-context \
  --include-last-transformer-payload
```

**Step 2：五维度审查**

| 维度 | 判据 |
|---|---|
| `completeness` | 飞书 9 节每节都能映射到 design.md / tasks.md / ac-schedule 中的位置 |
| `consistency` | design.md 接口契约与 ac-schedule 各 AC 的 given/expected 不矛盾 |
| `testability` | 每条 AC 在 ac-schedule 中有可执行 given/expected；harness 骨架 docstring 与 AC title 一致 |
| `architecture_fit` | design.md 架构接合点与 snapshot.architecture_yaml 当前接口一致 |
| `supersedes` | design.md ## supersedes 节真实反映 active_slice 的覆盖关系 |

**Step 3：回调 verdict**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-callback \
  --event reviewer_verdict \
  --data @verdict.json
```

verdict.json schema 见同目录 `callback-schema.json`。

`findings` 即使 verdict = converged 也可包含非阻塞观察（severity = info），但凡有 severity = blocking 必须 reject。
