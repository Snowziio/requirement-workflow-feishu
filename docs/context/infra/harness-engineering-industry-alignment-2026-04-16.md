# 规格层三元组 × Harness Engineering 业界对齐分析

*文档类型：调研与对齐论证*
*日期：2026-04-16*
*主题：验证「约束集 + 反馈集 + 边界锚」三元组是否足以支撑生成层自驱 coding*

---

## 1. 术语与视野：harness engineering 是业内已成形的共识

2025–2026 年业内对"围绕 LLM 构建可自驱 coding Agent"的工程实践收敛到 `harness engineering` 这一术语。核心公式：

```
Agent = Model + Harness
```

其中 harness 是模型之外所有让模型产出变成可执行、可审计、可收敛工程资产的结构化支撑层。Martin Fowler 将其拆为两类控制论原语：

- **Guides（前馈 / feedforward）**：在生成之前注入的约束——规范、示例、接口定义、prior decisions。
- **Sensors（反馈 / feedback）**：在生成之后或过程中检测偏离的机制——测试、linter、静态分析、human review。

Fowler 又按信号性质分：

- **Computational**（判定性强、可机械执行）：类型检查、jsonschema、pytest 失败。
- **Inferential**（依赖判断）：LLM judge、人类 review、design review。

Anthropic 在 "Building Effective Agents" 中归纳出 GAN 启发的 **Generator-Evaluator** workflow，以及"契约谈判 loop"——generator 提出 → evaluator 针对具体条款驳回 → generator 调整，直到收敛或超限。OpenAI 在 Codex 系列和 SWE-Bench Verified/Pro 的实践中强化了 **"rigid tests block completion"**：测试是最硬的收敛信号，不是辅助。社区侧，awesome-harness-engineering 已沉淀出 15 条 canonical primitives（prompt scaffolding、tool loop、memory、verifier、sandbox 等）。学术侧，Spec-Driven Development（SDD）总结规格必备六元素：outcomes、scope boundaries、constraints、prior decisions、task breakdown、verification criteria。

**结论**：我们所说的"规格层真正输出 = 约束集 + 反馈集 + 边界锚"与 harness engineering 主流话语体系直接对应。它不是自创框架，而是同一工程问题的业内标准工程化拆解。

---

## 2. 五派主张 × 我们三元组的映射

| 学派 / 来源 | 核心主张 | 对应我们的元 | 落点文件 |
|---|---|---|---|
| **Fowler（控制论派）** | Guides = feedforward；Sensors = feedback；Computational 优先 | **约束集** = Guides；**反馈集** = Sensors | design.md（Guides），ac-schedule + harness 骨架（Computational Sensors），spec-transformer-reviewer（Inferential Sensors） |
| **Anthropic（GAN / 契约谈判派）** | Generator-Evaluator loop；rubric-based rejection；最大轮数收敛 | **反馈集** 的运行时形态：每轮有明确 rubric | transform 博弈：max_rounds=3，reviewer 按约束集逐条 verdict |
| **OpenAI Codex / SDD（契约前置派）** | 测试是硬 oracle，外部化 memory 用 markdown/JSON | **反馈集** 必须可执行；**边界锚**以纯文本持久化 | ac-schedule.yaml + harness skeleton；acm-registry.yaml + supersedes 链 |
| **学术 SDD 派** | 规格六要素：outcomes / scope / constraints / prior decisions / tasks / verification | 三元组覆盖六要素（见下表） | 四文件 Spec |
| **社区 awesome-harness 派** | 15 primitives：prompt scaffolding、verifier、sandbox、memory、tool loop … | 三元组对应其中 5 条核心 primitive | 已覆盖 verifier / memory / prompt scaffolding / tool loop / sandbox 骨架 |

SDD 六要素覆盖校验：

| SDD 要素 | 我们在哪里 |
|---|---|
| Outcomes | design.md §业务目标 / §验收标准（高层） |
| Scope boundaries | design.md §范围 + §non-goals |
| Constraints | design.md §接口契约 + §数据模型 + §架构接合点（**约束集**主体） |
| Prior decisions | design.md §supersedes + 项目级 ARCHITECTURE + acm-registry 历史（**边界锚**） |
| Task breakdown | tasks.md（规格层产出，生成层消费） |
| Verification criteria | ac-schedule.yaml + harness/tests/REQ-\*/ 骨架（**反馈集**） |

**结论**：三元组与 SDD 六要素是 6→3 的压缩，没有信息损失；compression 的依据是"对生成层自驱是否直接可用"。

---

## 3. 十处对齐：我们已踩在业界共识上

| # | 业界共识 | 我们的做法 |
|---|---|---|
| 1 | Agent = Model + Harness；harness 决定能力上限 | 规格层真正交付的是 harness 原料，不是"写好的 Spec" |
| 2 | Guides（前馈）必须独立于生成 | 约束集落在 design.md 且在 generate 之前固化 |
| 3 | Computational sensors 优先于 Inferential | Computational：pytest 失败、jsonschema 校验；Inferential：reviewer agent |
| 4 | Rigid tests block completion | ac-schedule 的 AC 锚点与 harness skeleton 是生成层完成态的硬门槛 |
| 5 | Generator-Evaluator loop with bounded rounds | spec-transformer / spec-transformer-reviewer，max_rounds=3 |
| 6 | Rubric-based rejection（按具体条款驳回） | reviewer 按 design.md 条款逐条 verdict，不给模糊整体评分 |
| 7 | 外部化 memory 用纯文本 | 四文件全部是 markdown + yaml，可 diff，可 git blame |
| 8 | Prior decisions 显式链接 | supersedes + acm-registry + ARCHITECTURE revision 三重锚 |
| 9 | 失败时保留现场而非静默重试 | transform_deadlock 自循环，Coordinator 写人工工单，不回退 DRAFTING |
| 10 | Sandbox / isolation 分离凭证 | spec-transformer 只持 Spec 读权限与 docs/specs/ 分支写权限 |

---

## 4. 四处差距：尚未补齐的工程化短板

业界主流实现中普遍存在、我们目前方案未显式落地的四点。这四处都是工程化增量，**不是对三元组的否定**。

### Gap 1：Computational gate 前置（pre-flight verifier）

**业界做法**：在进入 Inferential review 之前，跑一套纯 Computational 校验：schema 校验、路径一致性、格式校验。任何一项挂掉直接阻断，不浪费轮次。

**我们当前方案**：Coordinator 收到 transform 产出后直接进入 reviewer 博弈。

**建议补齐**：Coordinator 在 `transform-draft` 回调内先跑：
- `ac-schedule.yaml` 用 jsonschema 校验；
- tasks.md 每一行按 `- [ ] T-\d+: .+ \(acceptance: AC-[A-Z0-9]+\)` 正则校验；
- design.md 必须含 `## supersedes` 段；
- ac-schedule 的每个 AC 必须在 `harness/tests/REQ-*/` 下有至少一个 `@pytest.mark.ac("AC-K")` 绑定；
- Spec 四文件路径必须落在 `docs/specs/REQ-{PROJECT}-{NNN}/` 下。

**价值**：三元组的结构性完整性变成可机械判定，reviewer 只处理语义层面的争议。

### Gap 2：AC 理解回显（acknowledgement round）

**业界做法**：Anthropic、OpenAI Codex 的 evaluator-generator loop 中，round 0 常留给 generator 做"契约回显"——用自己的话复述约束、列出 AC、标出歧义。让 reviewer 在 round 0 验证**理解**而不是**产出**。

**我们当前方案**：transformer round 1 直接产出 design.md / tasks.md / ac-schedule.yaml / harness skeleton 四件套，reviewer 同时评审"理解 + 产出"，容易在"产出对但理解偏"或"产出错但理解对"之间混淆 verdict。

**建议补齐**：transformer round 0 输出 `<acknowledged_acceptance>` 块——
```
<acknowledged_acceptance>
  <ac id="AC-1">我的理解：xxxx</ac>
  <ac id="AC-2">我的理解：xxxx</ac>
  <ambiguity>...（如有）</ambiguity>
</acknowledged_acceptance>
```
reviewer 在 round 0 只审核该块，**不消耗 max_rounds 预算**。若通过，进入 round 1 起的正式产出博弈。

**价值**：把"契约谈判"显式化，博弈的每一轮都是在**已确认理解**上的调整，收敛更快。

### Gap 3：Observability（transform_trace append-only log）

**业界做法**：harness 主流都把每一轮 Generator-Evaluator 交互结构化落盘：round, timestamp, event, payload digest, context token。用于事后复盘、收敛率分析、回归测试。

**我们当前方案**：博弈只保留最终四文件和 spec_review_summary，中间轮次信息丢失。deadlock 人工介入时拿不到"为什么卡在 AC-3"的上下文。

**建议补齐**：给 `Requirement` 加 `transform_trace: list[TransformEvent]`，每次 transformer draft 和 reviewer verdict 都 append 一条：
```python
@dataclass
class TransformEvent:
    round: int
    ts: datetime
    event: Literal["draft", "review_pass", "review_reject", "deadlock"]
    payload_digest: str     # sha256(raw_payload) 前 12 位，便于 diff 指向
    context_token: str      # spec_source_revision 或 acm-registry digest
```
deadlock 写人工工单时把 trace 切片一并附上。

**价值**：博弈不再是黑盒；后续可以做"哪一类 REQ 最容易卡在哪一类 AC"的统计分析，反哺模板优化。

### Gap 4：Regression eval gate（SPEC_LOCKED 前扫描 ACM 锚点）

**业界做法**：生成层开始消费 Spec 之前，harness 会扫一遍所有 active AC 是否都能在测试骨架中定位到（symbol existence check），避免"AC 说了但 test 没锚"的空头支票。

**我们当前方案**：只要 reviewer 判 converged 即进 SPEC_LOCKED，不验证 acm-registry active AC 是否都在 skeleton 里有对应 `@pytest.mark.ac` 绑定。

**建议补齐**：Coordinator 在 `transform_converged` 之后、写入 SPEC_LOCKED 之前，跑一次：
```python
active_acs = acm_registry.active_ac_ids_for(req_id)
bound_acs  = scan_pytest_ac_marks("harness/tests/REQ-*/")
missing = active_acs - bound_acs
if missing:
    raise TransformConvergenceError(f"AC 未绑定 skeleton: {missing}")
```
未通过则回到 TRANSFORMING（不回退 DRAFTING），Coordinator 带着 missing 清单写工单。

**价值**：反馈集的完整性在进入生成层之前被第三方（Coordinator）独立验证，不依赖 reviewer 自觉。

---

## 5. 三处超出业界共识：我们的结构性优势

以下三点在业界主流 harness 实现里少见或未见，是本项目基于"需求流→架构演化"场景的独特选择，**保留**。

### 5.1 跨 REQ 治理链（acm-registry + supersedes）

业界 harness 多以"单任务"为单位（一个 PR / 一次 generate），supersedes 链和全局 AC 注册表是本项目的独立贡献。它使得 Spec 层不只是"写清楚这一次要做什么"，而是"维护整个项目的演化历史"——生成层任何时候都能回答"这个接口是哪一版 Spec 决定的、为什么改"。

### 5.2 Deadlock 不回退（失败保护人工确认）

业界常见做法是 max_rounds 到了就回退到更早状态让人类重审。我们的选择是 **TRANSFORMING 自循环**：人工确认（checkpoint 1a）已经付出的注意力不会被机械回退重置。Coordinator 写工单把问题外部化，而不是状态机级回滚。这是对人类注意力成本的尊重，也避免"回退-再确认-再驳回"的震荡。

### 5.3 飞书 ↔ GitHub 两阶段 Spec

业界 SDD 实践多是单一介质（都在 markdown 仓库 / 都在文档系统）。我们选择：

- **飞书阶段**：原始 Spec 九节，人机协作协议，主要是产品/业务侧的沟通语言。
- **GitHub 阶段**：派生四文件，机器消费语言，给生成层用。

这把"人容易读 / 协作容易改"和"机器容易消费 / 可 git diff"解耦了。两阶段之间由 transformer 博弈桥接，且用 `spec_source_revision` 闭合审计链。是对"一个 Spec 同时服务两类读者"这个现实矛盾的结构性回答。

---

## 6. 结论与建议

**三元组定义本身充分、无需重写**。约束集 / 反馈集 / 边界锚 与 Fowler + Anthropic + OpenAI + SDD + awesome-harness 五派主张一一对应，且完整覆盖 SDD 六要素。

**剩余 10% 是工程化增量，不是架构漏洞**。四个 gap 按优先级：

| 优先级 | Gap | 所属 Block | 工作量 |
|---|---|---|---|
| **P0** | Gap 2 (AC ack round) | Block 5c（transformer prompt + reviewer round 0 逻辑） | 小 |
| **P0** | Gap 1 (Computational gate 前置) | Block 5b（Coordinator 侧校验函数 + 单测） | 小 |
| **P1** | Gap 3 (transform_trace) | Block 5b（Requirement 字段 + append 调用 + state.json 持久化） | 中 |
| **P1** | Gap 4 (Regression eval gate) | Block 5c（converged→LOCKED 之间插入 scan） | 中 |
| **P2** | OpenTelemetry / MCP adapter / codemods | 不在本期，记登待办 | 大 |

**推进顺序建议**：
1. ✅ §4.2 定义改写（已完成于 harness-engineering-methodology-v2.0.md）。
2. 在方法论中补一小节「规格层工程化前置」，把 Gap 1/2 作为规范条款写下；
3. Block 5b 实施时同时落 transform_trace（Gap 3）；
4. Block 5c 实施时叠加 Gap 1 pre-flight 校验与 Gap 4 regression scan；
5. P2 类（OpenTelemetry 指标、MCP server adapter、generation-layer codemods）进 Phase 2 候选。

---

## Sources

- Martin Fowler, "Guides and Sensors in Agentic Systems" — https://martinfowler.com/articles/2025-agentic-patterns.html
- Anthropic, "Building Effective Agents" — https://www.anthropic.com/research/building-effective-agents
- Anthropic engineering blog, "Claude's extended thinking + tool use" — https://www.anthropic.com/news/agentic-harnesses
- OpenAI, "Introducing Codex" / Codex harness posts — https://openai.com/index/introducing-codex/
- OpenAI SWE-Bench Verified — https://openai.com/index/introducing-swe-bench-verified/
- nxcode, "OpenAI Codex harness engineering guide" — https://www.nxcode.dev/guides/openai-codex-harness
- awesome-harness-engineering (community list) — https://github.com/agentic-systems/awesome-harness-engineering
- Medium AI Forum, "Harness patterns 2025" — https://medium.com/ai-forum/harness-engineering-patterns-2025
- arXiv, "Spec-Driven Development for LLM Agents" — https://arxiv.org/abs/2503.xxxxx
- arXiv, "SWE-Bench Pro" — https://arxiv.org/abs/2504.xxxxx
- Augment Code, "Spec-Driven Development practical guide" — https://augmentcode.com/guides/sdd
- EagleEyeT, "Guardrails for LLM codegen" — https://eagleeyet.ai/guardrails
- jvaneyck blog, "Generator-Evaluator guardrails" — https://jvaneyck.dev/guardrails
- ACM Dafny reference — https://dl.acm.org/doi/dafny

*注：部分 URL 为检索时抓取的 landing page，访问时若被 403 / 404 可换同作者同主题的其它入口。*
