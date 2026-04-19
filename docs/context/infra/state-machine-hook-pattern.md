# 状态机 + 显式钩子模式

## 原则

纯状态机 + 显式钩子 = 可测 + 可扩展。状态机只负责"事件 + 当前状态 → 下一个状态"，所有副作用（I/O、外部系统调用、日志发送）在状态转移的 `on_exit`/`on_enter` 钩子里触发。

## 适用场景

- 状态转移需要副作用（GitHub 写入、外部 webhook、审计日志等）
- 副作用数量会随业务扩展增长（每加一个状态就要加一批副作用）
- 需要能单测状态转移逻辑，不被 I/O 污染

## 反模式

在 `apply_event` 附近堆 `if next_status == X: do_effect_x()`。具体表现：
- `submit_checkpoint_*` 方法里直接调 `self.orchestrator.on_enter_transforming(...)`
- 状态机的 decision 分支里夹一段 GitHub 调用
- 同一副作用散落在多处触发点，没有中心登记簿

这些会让状态机不再是纯函数，也让新增状态的工程成本随状态数线性增长。

## 契约摘要

- `fire_exit(prev_status, req)` 必须早于 `apply_spec_event`（旧状态仍可读）
- `fire_enter(next_status, req)` 必须晚于 `apply_spec_event`（新状态已落地）
- 钩子失败 = 转移失败：抛出的异常透传到调用方（fail-fast）
- 异常必须先 log（带结构化字段）再 re-raise，不得吞

## 与 Coordinator 的关系

`StateTransitionHooks` 实例挂在 Coordinator 上，生命周期与 Coordinator 一致。各子系统（orchestrator、审计器、webhook 发送器）在装配阶段（例如 `configure_*`）向钩子注册回调；状态转移方法本身不假设任何 orchestrator 存在，只 `fire_exit → apply → fire_enter`。

## 参考实现

本仓库落地：见 `docs/superpowers/specs/2026-04-19-project-repo-tools-design.md` § 4。
