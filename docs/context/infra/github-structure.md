# GitHub 仓库结构与 CI 配置

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) 工程自动化轨的实现细节文档。
> 完整的 GitHub Actions workflow 配置见 [../layers/generation-delivery-layers.md](../layers/generation-delivery-layers.md)。

---

## 一、仓库结构（项目模板）

参见 [../layers/generation-delivery-layers.md §三](../layers/generation-delivery-layers.md)（GitHub 仓库结构一节），含完整目录树和各目录说明。

---

## 二、GitHub Actions workflow 清单

| workflow 文件 | 触发方式 | 覆盖阶段 | 状态 |
|---|---|---|---|
| `ci.yml` | PR 创建/更新 | 验证层（卡点2 触发源） | ✅ 完成 |
| `staging.yml` | push to main | 集成层（自动部署 Staging） | ✅ 完成 |
| `deploy.yml` | workflow_dispatch | 交付层（卡点3 后触发） | ✅ 完成 |
| `spec-to-harness.yml` | workflow_dispatch | 规格层-B（Harness 自动生成） | □ 待建（Phase 3） |
| `harness-confirmed.yml` | workflow_dispatch | 生成层（AI 实现触发） | □ 待建（Phase 3） |

完整 YAML 配置见 [../layers/generation-delivery-layers.md §四](../layers/generation-delivery-layers.md)。

---

## 三、Self-hosted Runner 配置

- **Runner 类型**：Self-hosted（ARM 服务器）
- **原因**：需要访问内网服务、客户环境；避免 GitHub 托管 Runner 的网络限制
- **当前主机**：`admin@47.251.81.45`（与 Coordinator Service 共用）
- **注册方式**：GitHub 仓库 → Settings → Actions → Runners

---

## 四、分支保护规则

| 分支 | 保护规则 |
|---|---|
| `main` | 必须通过 CI（`ci.yml`）；不能直接 push，必须通过 PR |
| `staging` | 由 `staging.yml` 自动同步 main；不接受直接 push |

---

## 五、ACM 注册表与设计系统快照路径

| 产物 | GitHub 路径 | 维护者 |
|---|---|---|
| ACM 注册表 | `spec/registry/consolidated.yaml` | checkpoint-handler |
| 设计系统快照 | `specs/design-system-snapshot.yaml` | Coordinator Service（Spec 生成时导出） |
| ARCHITECTURE.yaml | 仓库根目录 | checkpoint-handler（Impl PR 合并后更新） |

格式规范见 [../infra/project-context.md](project-context.md)。
