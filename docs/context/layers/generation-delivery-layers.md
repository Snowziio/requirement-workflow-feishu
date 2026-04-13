# 生成层至交付层实现规格

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §4.4–§4.7 的实现细节文档。
> 描述 CLAUDE.md 模板结构、AI 自修复规则、GitHub Actions 配置、测试分层策略、Smoke Test、分支策略和部署配置。

---

## 一、CLAUDE.md 通用模板结构

每个项目代码仓库的根目录必须有 CLAUDE.md，是 AI Coding Agent 每次 session 的热加载规则文件。

```markdown
# {项目名称}

## 项目背景
{项目一句话描述}

## 当前任务阶段（由 workflow 自动注入，每次 session 开始时读取）
CURRENT_TASK: {spec | harness | implement}
REQ_ID: {REQ-{PROJECT}-{NNN}}

## 架构快照（由 checkpoint-handler 维护）
参见 ARCHITECTURE.yaml（同目录）

## 强制规则

### 文件权限
- `harness/tests/` — 只读，任何 PR 不得修改此目录
- `spec/` — 只读，任何 PR 不得修改此目录
- `src/` — 实现代码的唯一允许修改区域
- `docs/` — 只允许在 spec 阶段修改

### 任务阶段约束
- CURRENT_TASK = spec：只在 spec/ 目录下工作，不碰 src/ 和 harness/
- CURRENT_TASK = harness：只在 harness/tests/{REQ_ID}/ 目录下生成测试，不碰 src/
- CURRENT_TASK = implement：在 src/ 下工作，harness/ 只读

### 自修复约束
- CI 失败时最多自动修复 3 轮
- 每轮修复前必须读取完整的失败日志（不猜测原因）
- 第 3 轮失败后停止，在 PR 评论中写明卡点，等待人工介入
- 每次修复只改最小范围，不扩大修改面

### 禁止行为
- 不得在没有对应 AC 的情况下新增功能
- 不得修改数据库迁移文件（已合并的 migration 只读）
- 不得内联 API 密钥或敏感配置（统一走环境变量）

## 技术栈
{语言}：{版本}
{框架}：{版本}
包管理：{pip / poetry / npm / ...}
测试框架：{pytest / jest / ...}
数据库：{PostgreSQL 15 / ...}

## 本地开发
{启动命令}
{测试运行命令}

## Harness 通过标准（CI 必须全绿才能合并 PR）
- P0 AC 对应测试全部通过
- 视觉回归测试无超阈值差异（需要UI = true 时）
- 无新增 lint 错误
```

---

## 二、AI 自修复规则

AI Coding Agent 在 CI 失败时按以下规则自修复，这些规则由 CLAUDE.md 约束。

```
失败处理循环（最多 3 轮）：

Round N（N = 1, 2, 3）：
  1. 读取完整 CI 失败日志（不跳过任何错误行）
  2. 定位失败的测试函数和断言
  3. 追溯到对应的 AC 条目（按 test_file / test_function 字段）
  4. 查看对应 AC 的 expected 约定，判断是实现错误还是测试错误
     - 实现错误 → 修改 src/
     - 测试错误 → 不能改测试，写明分析结果等待人工介入
  5. 最小化修改：只改与失败直接相关的代码
  6. 运行单个失败的测试确认修复（不运行全量）
  7. git add / commit / push
  8. 等待 CI 结果

Round 3 失败后：
  → 停止自修复
  → 在 PR 评论中写明：
    - 已尝试次数
    - 每轮的失败原因
    - 当前认为的根因
    - 推荐的人工介入方向
  → 状态设为 waiting_for_human
```

---

## 三、GitHub 仓库结构

```
{project-name}/
├── CLAUDE.md                        # AI 工作规则（热加载）
├── ARCHITECTURE.yaml                # 架构快照（checkpoint-handler 维护）
├── .github/
│   └── workflows/
│       ├── ci.yml                   # PR 验证（卡点2 触发源）
│       ├── staging.yml              # 合并后自动部署 Staging
│       ├── deploy.yml               # 卡点3 后触发客户部署
│       ├── spec-to-harness.yml      # 卡点1a 后自动生成 Harness
│       └── harness-confirmed.yml    # 卡点1b 后触发 AI 实现
├── spec/                            # 四层 Spec（按 REQ 组织）
│   ├── REQ-PROJECT-001/
│   │   ├── requirements.md
│   │   ├── design.md
│   │   ├── design-ui.md             # 可选
│   │   ├── acceptance.yaml
│   │   └── tasks.md
│   └── registry/
│       └── consolidated.yaml        # ACM 注册表（checkpoint-handler 维护）
├── specs/
│   └── design-system-snapshot.yaml  # 设计系统快照（Spec 生成时导出）
├── harness/
│   └── tests/
│       ├── REQ-PROJECT-001/         # 按 REQ 组织（卡点1b 后只读）
│       └── conftest.py
├── docs/
│   └── decisions/
│       └── ADR-001-*.md             # 架构决策记录
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml           # 本地开发
│   ├── docker-compose.test.yml      # CI 测试
│   ├── docker-compose.staging.yml   # Staging
│   └── docker-compose.prod.yml      # 生产
├── deploy/
│   ├── customers/                   # 客户配置（gitignore）
│   │   ├── client-a.env
│   │   └── client-b.env
│   └── deploy.sh
├── scripts/
│   ├── notify_feishu.py             # 飞书通知脚本
│   └── analyze_failure.py           # AI 失败分析脚本
└── src/                             # AI 生成的应用代码
```

---

## 四、GitHub Actions 配置

### ci.yml（验证层）

```yaml
name: Harness Gate
on:
  pull_request:
    branches: [main, staging]

jobs:
  harness:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: Run Full Harness
        run: |
          docker compose -f docker/docker-compose.test.yml up \
            --abort-on-container-exit \
            --exit-code-from test

      - name: Upload Test Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-report
          path: reports/

      - name: Notify Feishu on Failure
        if: failure()
        run: |
          python scripts/notify_feishu.py \
            --event ci_failed \
            --pr "${{ github.event.pull_request.number }}" \
            --report reports/summary.json

      - name: Notify Feishu on Success
        if: success()
        run: |
          python scripts/notify_feishu.py \
            --event ci_passed \
            --pr "${{ github.event.pull_request.number }}" \
            --report reports/summary.json
```

### spec-to-harness.yml（规格层-B 触发）

```yaml
name: Spec to Harness
on:
  workflow_dispatch:
    inputs:
      req_id:
        description: "REQ ID (e.g. REQ-PROJECT-001)"
        required: true
      spec_pr:
        description: "Spec PR number"
        required: true

jobs:
  generate-harness:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: Set CLAUDE.md task stage
        run: |
          sed -i "s/CURRENT_TASK: .*/CURRENT_TASK: harness/" CLAUDE.md
          sed -i "s/REQ_ID: .*/REQ_ID: ${{ inputs.req_id }}/" CLAUDE.md

      - name: Generate Harness with Claude Code
        run: |
          claude-code --task "Generate harness tests for ${{ inputs.req_id }} based on spec/${{ inputs.req_id }}/acceptance.yaml"

      - name: Create Harness PR
        run: |
          gh pr create \
            --title "harness: ${{ inputs.req_id }}" \
            --body "Auto-generated harness from Spec PR #${{ inputs.spec_pr }}" \
            --base main
```

### harness-confirmed.yml（生成层触发）

```yaml
name: Harness Confirmed - Trigger Implementation
on:
  workflow_dispatch:
    inputs:
      req_id:
        description: "REQ ID"
        required: true
      harness_pr:
        description: "Harness PR number (to merge)"
        required: true

jobs:
  start-implementation:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: Merge Harness PR
        run: gh pr merge ${{ inputs.harness_pr }} --squash

      - name: Create impl branch
        run: git checkout -b impl/${{ inputs.req_id }}

      - name: Set CLAUDE.md task stage
        run: |
          sed -i "s/CURRENT_TASK: .*/CURRENT_TASK: implement/" CLAUDE.md
          sed -i "s/REQ_ID: .*/REQ_ID: ${{ inputs.req_id }}/" CLAUDE.md
          git add CLAUDE.md
          git commit -m "chore: set task stage to implement for ${{ inputs.req_id }}"

      - name: Start Implementation with Claude Code
        run: |
          claude-code --task "Implement ${{ inputs.req_id }} based on spec/${{ inputs.req_id }}/ and harness/tests/${{ inputs.req_id }}/"

      - name: Create Impl PR
        run: |
          gh pr create \
            --title "impl: ${{ inputs.req_id }}" \
            --body "Auto-generated implementation for ${{ inputs.req_id }}" \
            --base main
```

---

## 五、测试分层策略

| 层次 | 范围 | Mock 策略 | 运行时机 | Harness 对应 |
|---|---|---|---|---|
| 单元测试 | 单个函数/类 | 全部 mock 外部依赖 | 每次 CI | AC test_type: unit |
| 集成测试 | 模块间交互 | Mock 第三方 API，真实数据库 | 每次 CI | AC test_type: integration |
| 视觉回归 | 关键 UI 视图 | 真实前端，mock API 响应 | 每次 CI | AC test_type: visual |
| Smoke 测试 | 核心路径可用性 | 无 mock，真实环境 | 每次部署后 | 不在 Harness，独立脚本 |
| 性能测试 | 响应时间 SLA | 无 mock，稳定环境 | 仅 Staging 验收 | AC ci_enabled: false |

---

## 六、分支策略

```
feature/xxx → (PR) → main → (自动) → staging → (手动触发) → 客户环境

分支命名：
  spec/REQ-{PROJECT}-{NNN}      Spec 分支（规格层-A）
  impl/REQ-{PROJECT}-{NNN}      实现分支（生成层）
  main                           生产代码
  staging                        Staging 环境（自动同步 main）
```

---

## 七、Smoke Test 规范

Smoke Test 仅验证服务是否能正常启动和核心路径是否可走通，不追求完整业务覆盖：

```python
# smoke_test.py：每次部署后自动运行

def test_service_health():
    """服务健康检查接口响应正常"""
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_core_path_reachable():
    """核心业务路径（风控报告）可以到达，不验证具体结果"""
    response = requests.post(f"{BASE_URL}/api/v1/risk-report", ...)
    assert response.status_code in [200, 422]  # 有正常响应即可，不验证业务逻辑
```

---

## 八、客户部署配置

### 配置隔离

```
deploy/
├── customers/
│   ├── client-a.env      # 客户 A 的所有配置（gitignore）
│   └── client-b.env      # 客户 B 的所有配置
└── deploy.sh
```

```bash
# deploy/deploy.sh

CUSTOMER=$1
if [ -z "$CUSTOMER" ]; then
  echo "Usage: deploy.sh <customer-name>"
  exit 1
fi

ENV_FILE="deploy/customers/${CUSTOMER}.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Customer config not found: $ENV_FILE"
  exit 1
fi

# 加载客户配置
source "$ENV_FILE"

# 部署
docker compose -f docker/docker-compose.prod.yml up -d

# 健康检查（最多等待 60 秒）
MAX_WAIT=60
WAIT=0
until curl -sf "${HEALTH_URL}/health" > /dev/null; do
  sleep 2
  WAIT=$((WAIT + 2))
  if [ $WAIT -ge $MAX_WAIT ]; then
    echo "HEALTH CHECK FAILED after ${MAX_WAIT}s, rolling back..."
    docker compose -f docker/docker-compose.prod.yml down
    # 回滚到上一个镜像版本
    docker compose -f docker/docker-compose.prod.yml up -d --no-deps \
      --build --pull missing
    exit 1
  fi
done

echo "Deployment successful: ${CUSTOMER}"
```
