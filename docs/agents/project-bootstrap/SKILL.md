---
name: project-bootstrap
description: 项目引导助手（MVP 由 coordinator CLI 驱动；后续可 agent 化）。将 /create project 固化命令接到 7 步 Bootstrap 流程。
---

# Project Bootstrap 助手

## MVP 实现

MVP 阶段 Project Bootstrap **由 coordinator 直接执行**（`ProjectBootstrapService.run`），
不通过 AI agent。本文件作为后续 agent 化的占位：当 Bootstrap 需要决策（如
environments/CI 选型）时，再扩展为 agent 驱动。

## 当前流程

1. 用户在创建群发 `/create project <name> --category <c> --owner <uid>`
2. coordinator 解析 → `BootstrapRequest` → `ProjectBootstrapService.run`
3. 7 步流程见 `src/requirement_workflow_v12/project_bootstrap/service.py`
4. 失败时用户发 `--resume` 续跑

## 后续扩展方向（Phase 2）

- environments.yaml 的 category 默认骨架细化（按技术栈差异化）
- SECRETS 清单自动补全（按 CI 需要的具体 key）
- CI workflow 的 category-aware 渲染（不同 category 不同 lint/test/deploy）
