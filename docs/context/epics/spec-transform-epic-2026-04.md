# Epic · Spec 层 GitHub 四文件转化 + ACM 治理链

> **临时规划文档**。本 epic 完成后删除(历次 commit 即审计留痕)。
> 建立时间:2026-04-16
> 背景:方法论文档 §4.2 规定 Spec 层输出 GitHub 四层 Spec,但能力从未落地;同时引入 ARCHITECTURE 定位纠偏、harness 目录 C 方案、ACM 注册表治理链三条纪律。

---

## 一、设计决策摘要(对话中已拍板)

1. **飞书 9 节 Spec vs GitHub 四文件 = derivation 关系**:spec-author 只写飞书 9 节(原始产出);GitHub 四文件是卡点 1a 后由 AI Agent(spec-transformer + spec-transformer-reviewer)多轮博弈**转化**出的派生产出。
2. **ARCHITECTURE 不是 Spec 层产出,而是项目级上下文**:被 Spec 层消费并演化;0-1 初始化通过需求建立时的产品形态模板解决。
3. **转化时机**:`checkpoint_1a_pass` → 新中间态 `SPEC_TRANSFORMING` → 博弈收敛 → `SPEC_LOCKED`。博弈失败走人工工单,**不回退** SPEC_DRAFTING(保护人工确认)。
4. **GitHub 物理承载**:Coordinator 在 SPEC_TRANSFORMING 进入时,基于 `Snowziio/harness-scaffold` 建项目 repo(新项目)或切 `spec/REQ-*` 分支(旧项目),再把 Agent 产出的四文件 commit 到分支。Agent 不持 GitHub 凭据。
5. **审计链**:Coordinator 在卡点 1a 那一刻 fetch 飞书 Spec docx 的 revision,记为 `spec_source_revision`,写入 Spec PR body + bitable,单向追溯,不做双向握手。
6. **Spec 四文件路径**:`docs/specs/REQ-{PROJECT}-{NNN}/`(与 scaffold 现有 `docs/specs/` 对齐,不用方法论旧文档里的 `spec/REQ-*/`)。
7. **Harness 目录 C 方案**:
   ```
   harness/tests/
     REQ-*/{unit,integration,e2e}/      # REQ 锁定后整块只读
     _system/{smoke,compatibility,migration}/   # 跨 REQ 公共测试,项目维护者可改
   ```
8. **过期 AC 治理**:测试代码永远保留;CI 是否跑由 `acm-registry.yaml` 调度。三条事件链:
   - `supersedes:<REQ>` — 新 REQ 显式覆盖老 AC,卡点 1a 通过时自动标记
   - `retired:<REQ>` — 专门的"废弃 REQ"(无 impl,只改 registry),独立触发
   - `shell_patched:<REQ>` — AC 语义不变但测试外壳需改(如依赖升级),走 harness-patch PR + spec-reviewer 双签
9. **纪律硬约束**:任何人不可直接 git push 改 `harness/tests/REQ-*/` 或手改 registry。CI guardrail + PR template + AI Agent SKILL 三重锁。

---

## 二、工作块划分

### Block 1 · scaffold 改造
**Repo**:`Snowziio/harness-scaffold`

- `harness/tests/` 改为 C 方案结构(`_system/` + `.REQ-template/`)
- 新增 `acm-registry.yaml`(schema 定义 + 空初始文件)
- 新增 `harness/conftest.py`:pytest test collector 插件,读 registry,非 active AC 自动 skip,输出 retired-ac-report
- `.github/workflows/ci.yml` 加 harness guardrail:修改 `harness/tests/REQ-*/` 且 AC 不在 shell_patched 声明中 → fail
- `.github/PULL_REQUEST_TEMPLATE.md` 新增"治理事件声明"段落
- `.github/ISSUE_TEMPLATE/retire-request.md`
- `CLAUDE.md` 纪律条款(禁绕 guardrail、禁手改 registry)

### Block 2 · project_config schema 扩展
**Repo**:本 repo + Bitable

- `ProjectConfig` dataclass 加 `github_repo_url`、`github_owner_username`
- Bitable ProjectConfigs 表加对应列(走 `sync_bitable_schema_v12.py`,dry-run 再同步)
- `list_project_configs` / 回写契约带上新字段
- 测试:store 往返 + Bitable 往返

### Block 3 · Coordinator GitHub 能力
**Repo**:本 repo

- 新增 `github_gateway.py`(类比 `feishu_gateway.py`):
  - `create_repo_from_template(owner, name, template)`
  - `create_branch(repo_url, branch)`
  - `commit_files(branch, files, message)`
  - `open_pull_request(...)`
- GitHub App 或 PAT secret 配置(staging + prod)
- 集成测试:`Snowziio/test-sandbox` 做落地验证

### Block 4 · spec-transformer 能力层
**Repo**:OpenClaw skills 仓库

- `spec-transformer` SKILL:输入飞书 9 节 + scaffold 参数 → 返回 4 文件文本(不持 GitHub 凭据)
- `spec-transformer-reviewer` SKILL:审查 supersedes 覆盖完整性 / ACM yaml schema / tasks.md 可执行性
- 多轮博弈 callback 协议:`transform-draft` / `transform-review` / `transform-converged` / `transform-deadlock`

### Block 5 · SPEC_TRANSFORMING 状态扩展
**Repo**:本 repo

- `spec_state_machine.py` 加 `SPEC_TRANSFORMING` 态 + `TRANSFORM_CONVERGED` / `TRANSFORM_DEADLOCK` 事件
- `checkpoint_1a_pass` 目标改为 `SPEC_TRANSFORMING`
- `SPEC_TRANSFORMING` onEnter hook:
  1. 捕获 `spec_source_revision`
  2. 调 GitHub gateway 建 repo / 切分支
  3. 唤醒 transformer 博弈
  4. 收敛后 Coordinator commit 四文件 + 开 Spec PR
  5. 转 `SPEC_LOCKED`
- `TRANSFORM_DEADLOCK`:写人工工单,状态留在 `SPEC_TRANSFORMING`,**不回退**
- 测试覆盖:成功路径 / 博弈 deadlock / GitHub 侧失败(repo 已存在、权限不足)

### Block 6 · ACM registry 治理链
**Repo**:本 repo + scaffold

- spec-transformer 生成 design.md 时强制输出 `supersedes` 节;无取代时必须显式"no supersession"
- Coordinator 在 `SPEC_LOCKED` 成功后自动生成 `acm-registry.yaml` 的 patch,作为 Spec PR 的一个 commit
- "retirement REQ" 识别逻辑:专门的需求模板 / category;Coordinator 只改 registry 不建 impl 分支
- "shell-patch PR" 轻量流程(PR template + spec-reviewer 双签,不引入新状态)

### Block 7 · 文档对齐
**Repo**:本 repo(方法论 + spec-harness-layer 文档)

- 方法论 §3.2:ARCHITECTURE 表述从"Spec 层产出物"改为"项目级上下文,被 Spec 层消费并演化"
- 方法论 §4.2 输出行重写:**飞书 9 节 Spec**(原始)+ **GitHub 四文件**(派生);ARCHITECTURE 从输出行移除
- 方法论 §4.2:补 `SPEC_TRANSFORMING` 子状态 + 博弈机制描述
- 方法论 §4.3:harness 目录改为 C 方案;加"治理事件"小节
- spec-harness-layer §"Spec 子层产出":ARCHITECTURE 从产出表移到"消费并演化"节;加 GitHub 四文件产出条目 + `spec_source_revision` 字段
- spec-harness-layer §四:加 `SPEC_TRANSFORMING` 行;`checkpoint_1a_pass` 目标改为 `SPEC_TRANSFORMING`
- spec-harness-layer 新增 §"治理链:过期 AC 处理"
- 路径统一:`docs/specs/REQ-{PROJECT}-{NNN}/` 替换所有 `spec/REQ-*/`

---

## 三、依赖与推进顺序

```
Block 2 ─┐
Block 1 ─┼─► Block 3 ─► Block 5 ─► Block 7
Block 4 ─┘              (Block 6 穿插在 5 之内)
```

- Block 1 / 2 / 4 相互独立,可并行启动
- Block 3 依赖 Block 2(project_config 新字段)
- Block 5 依赖 Block 1、3、4
- Block 6 的 registry patch 生成穿插在 Block 5 实现中
- Block 7 留到最后一次性做,避免文档与代码反复打架

---

## 四、未决项(需要后续决定,不阻塞启动)

- GitHub App vs PAT:建 repo 需要 admin 权限,选哪种身份
- 新项目的 repo owner(Snowziio 自有 / 客户 org / 每客户独立 org)
- "retirement REQ" 的产品形态模板内容
- shell-patch PR 是否需要引入独立的 `harness-patch` 状态(当前倾向不引入,走轻量 PR 流程)

---

## 五、完成标准

所有 7 个 Block 合并主干,且:
- 能跑通端到端:新项目从 APPROVED → SPEC_DRAFTING → 卡点 1a → SPEC_TRANSFORMING → SPEC_LOCKED,GitHub repo 建出来、四文件提交、Spec PR 开出来
- 老项目增量 REQ 能从已有 repo 切分支走通同一流程
- 至少一次 `supersedes` / `retires` / `shell_patched` 治理事件在 staging 跑通
- 方法论文档和 spec-harness-layer 文档完全对齐,无自相矛盾

完成后删除本文档。
