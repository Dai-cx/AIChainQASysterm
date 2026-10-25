# 单智能体 vs 多智能体：同一份语料、同一套裁判的对照实验

本报告的数据由 `scripts/experiments/ab_agents.py` 跑出，表格由 `scripts/experiments/make_report.py` 渲染，所有数字都可以用文末命令复现。

## 一、实验设计

| 臂 | 检索编排 | 说明 |
| --- | --- | --- |
| `single` | 单趟顺序检索（`QA_ENABLE_AGENT=false`） | 计划 → 图查询 / 向量 / 研究库各一次 → 组装证据 → 生成 → 校验，没有调度 Agent、没有补检 |
| `multi_1` | 多智能体，补检上限 1 轮 | LLM 调度 Agent 拆任务 → 并行 worker → 审核；审核发现缺口时最多再补 1 轮 |
| `multi_3` | 多智能体，补检上限 3 轮 | 同上，缺口未被填上时最多补 3 轮 |

公平性控制：

1. **同一个引擎、同一份知识库**（`data/verified` 768 实体 / 1,219 关系 + `data/curated` 568 条 claim）、同一个 LLM、同一个问题集。
2. **统一裁判**：每题结束后，对臂的最终检索结果跑同一个 `EvidenceCoverageChecker`，按题目自身的覆盖要求打分；不采信臂内部自报的覆盖结论。
3. **同一套指标**：证据覆盖率、冲突组数、证据卡数、引用数、答案字数、延迟、LLM 调用次数、检索轮数。
4. `multi_1` 是消融臂：它与 `multi_3` 的差别只有补检轮数，用来区分「多智能体架构」和「补检闭环」各自的贡献。

## 二、总体指标

| 臂 | 题数 | 证据覆盖率 | 校验通过 | 校验告警 | 冲突组数 | 出现冲突的题 | 证据卡 | 引用 | 答案字数 | 延迟 p50 (s) | LLM 调用 | 检索轮数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | 10 | 0.50 | 0.70 | 0.30 | 0.30 | 3/10 | 6 | 6 | 1372 | 15.1 | 2 | 0 |
| `multi_1` | 10 | 0.50 | 0.00 | 1.00 | 2.10 | 10/10 | 4.3 | 4.3 | 1401 | 23.5 | 10.2 | 1.4 |
| `multi_3` | 10 | 0.50 | 0.00 | 1.00 | 2.10 | 10/10 | 4.7 | 4.7 | 1681 | 25.7 | 10.2 | 2 |

> 「校验通过/告警」由 `aika/agents/verification.py::verification_status` 判定：6 项检查全部通过且没有证据缺口时为 `pass`；只要检出冲突证据或缺口就降级为 `warn`，提示结论需要保守解释。

## 三、分层结果：只统计「有覆盖要求」的题目

| 臂 | 题数 | 覆盖率 | 缺口题数 | 平均冲突组 | 平均答案字数 | 平均 LLM 调用 |
| --- | --- | --- | --- | --- | --- | --- |
| `single` | 8 | 0.38 | 5 | 0.25 | 1304 | 2.0 |
| `multi_1` | 8 | 0.38 | 5 | 2.38 | 1199 | 10.5 |
| `multi_3` | 8 | 0.38 | 5 | 2.38 | 1970 | 10.5 |

## 四、逐题结果

### `profile_liquid` — 紫光股份的液冷业务有哪些优势？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | company_profile | 1.00 | - | 1 | warn | 6/6 | 0 | 15.0 | 2 |
| `multi_1` | company_profile | 1.00 | - | 1 | warn | 4/4 | 1 | 21.0 | 9 |
| `multi_3` | company_profile | 1.00 | - | 1 | warn | 3/3 | 1 | 21.8 | 9 |

### `profile_products` — 紫光股份的服务器产品线主要覆盖哪些场景？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | company_profile | 1.00 | - | 0 | pass | 6/6 | 0 | 14.4 | 2 |
| `multi_1` | company_profile | 1.00 | - | 1 | warn | 4/4 | 1 | 21.4 | 9 |
| `multi_3` | company_profile | 1.00 | - | 1 | warn | 4/4 | 1 | 21.3 | 9 |

### `risk_main` — 紫光股份当前面临的主要风险是什么？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | risk_analysis | 1.00 | - | 1 | warn | 6/6 | 0 | 14.5 | 2 |
| `multi_1` | risk_analysis | 1.00 | - | 1 | warn | 6/6 | 1 | 21.9 | 9 |
| `multi_3` | risk_analysis | 1.00 | - | 1 | warn | 6/6 | 1 | 25.7 | 9 |

### `risk_liquid` — 液冷业务的落地风险有哪些？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | thematic_research | 0.00 | risk_evidence, mechanism_evidence | 0 | pass | 6/6 | 0 | 20.5 | 2 |
| `multi_1` | thematic_research | 0.00 | risk_evidence, mechanism_evidence | 3 | warn | 6/6 | 2 | 30.4 | 12 |
| `multi_3` | thematic_research | 0.00 | risk_evidence, mechanism_evidence | 3 | warn | 6/6 | 4 | 30.2 | 12 |

### `theme_invest` — 液冷产业链的投资逻辑和主要风险是什么？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | thematic_research | 0.00 | risk_evidence, mechanism_evidence | 0 | pass | 6/6 | 0 | 15.1 | 2 |
| `multi_1` | thematic_research | 0.00 | risk_evidence, mechanism_evidence | 3 | warn | 6/6 | 2 | 31.1 | 12 |
| `multi_3` | thematic_research | 0.00 | risk_evidence, mechanism_evidence | 3 | warn | 6/6 | 4 | 30.5 | 12 |

### `theme_evolve` — 液冷散热技术从风冷到液冷的演进路径是什么？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | industry_bottleneck | 0.00 | mechanism_evidence | 0 | pass | 6/6 | 0 | 15.4 | 2 |
| `multi_1` | industry_bottleneck | 0.00 | mechanism_evidence | 3 | warn | 2/2 | 2 | 26.4 | 12 |
| `multi_3` | industry_bottleneck | 0.00 | mechanism_evidence | 3 | warn | 4/4 | 1 | 24.2 | 9 |

### `bottleneck_liquid` — 液冷技术规模商用的瓶颈在哪里？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | industry_bottleneck | 0.00 | mechanism_evidence | 0 | pass | 6/6 | 0 | 17.8 | 2 |
| `multi_1` | industry_bottleneck | 0.00 | mechanism_evidence | 3 | warn | 4/4 | 1 | 23.5 | 9 |
| `multi_3` | industry_bottleneck | 0.00 | mechanism_evidence | 3 | warn | 5/5 | 1 | 21.8 | 9 |

### `bottleneck_compute` — 算力基础设施目前的供给约束是什么？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | thematic_research | 0.00 | mechanism_evidence | 0 | pass | 6/6 | 0 | 16.1 | 2 |
| `multi_1` | thematic_research | 0.00 | mechanism_evidence | 2 | warn | 4/4 | 2 | 24.1 | 12 |
| `multi_3` | thematic_research | 0.00 | mechanism_evidence | 2 | warn | 6/6 | 4 | 26.5 | 12 |

### `topic_chain` — 液冷产业链有哪些关键环节，哪些公司参与？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | topic_to_company | 1.00 | - | 0 | pass | 6/6 | 0 | 13.8 | 2 |
| `multi_1` | topic_to_company | 1.00 | - | 3 | warn | 3/3 | 1 | 21.4 | 9 |
| `multi_3` | topic_to_company | 1.00 | - | 3 | warn | 3/3 | 2 | 27.2 | 12 |

### `metric_ict` — 紫光股份 ICT 基础设施业务的收入结构和毛利率如何？

| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `single` | company_profile | 1.00 | - | 1 | warn | 6/6 | 0 | 13.1 | 2 |
| `multi_1` | company_profile | 1.00 | - | 1 | warn | 4/4 | 1 | 23.4 | 9 |
| `multi_3` | company_profile | 1.00 | - | 1 | warn | 4/4 | 1 | 20.4 | 9 |

## 五、补检是否被触发

| 臂 | 题目 | 轮数 | 参与的 agent | 覆盖率 | 冲突组 |
| --- | --- | --- | --- | --- | --- |
| `multi_1` | `risk_liquid` | 2 | graph, graphrag, rag, research | 0.00 | 3 |
| `multi_1` | `theme_invest` | 2 | graph, graphrag, rag, research | 0.00 | 3 |
| `multi_1` | `theme_evolve` | 2 | graph, graphrag, rag, research | 0.00 | 3 |
| `multi_1` | `bottleneck_compute` | 2 | graph, graphrag, rag, research | 0.00 | 2 |
| `multi_3` | `risk_liquid` | 4 | graph, graphrag, rag, research | 0.00 | 3 |
| `multi_3` | `theme_invest` | 4 | graph, graphrag, rag, research | 0.00 | 3 |
| `multi_3` | `bottleneck_compute` | 4 | graph, graphrag, rag, research | 0.00 | 2 |
| `multi_3` | `topic_chain` | 2 | graph, graphrag, rag, research | 1.00 | 3 |

## 六、结论

### 6.1 证据覆盖率：三个臂完全相同（0.50）

8 道带覆盖要求的题目里，每个臂都只满足 3 道，缺口题目完全一致（`risk_liquid`、`theme_invest`、`theme_evolve`、
`bottleneck_liquid`、`bottleneck_compute`）。这不是预算不够，而是**语料里没有这类证据**：

| 检查项 | 语料事实 |
| --- | --- |
| `mechanism_evidence` | `data/curated/claims.csv` 共 81 条 `mechanism` claim，其中提到"液冷"的只有 **3** 条 |
| `risk_evidence` | 共 21 条 `risk` claim，topic 全是"经营风险"，提到"液冷"的 **0** 条 |

补检确实跑了（`multi_3` 在 4 道题上把轮数推到 4 轮），但它只是在同一批检索器上换 query 文本，
命中的候选集与首轮高度重叠：`risk_liquid` 的检索轮数从 1 增到 4、LLM 调用从 9 增到 12，覆盖率仍然是 0.00。
**结论：编排层无法凭空创造语料里不存在的证据类型。** 想让这类题目达标，得补数据或给补检换检索维度
（按 claim_type / 换数据源），而不是加轮数。

### 6.2 多智能体真正的增益：冲突与反证识别

同一套裁判下，两个多智能体臂在 **10/10** 道题上都检出了冲突证据组（平均 2.1 组/题，共 21 组），
单智能体只在 **3/10** 道题上检出（平均 0.3 组/题，共 3 组）：

| 臂 | 出现冲突的题 | 冲突组总数 | 答案平均字数 | 证据卡 | 引用 |
| --- | --- | --- | --- | --- | --- |
| `single` | 3/10 | 3 | 1372 | 6.0 | 6.0 |
| `multi_1` | 10/10 | 21 | 1401 | 4.3 | 4.3 |
| `multi_3` | 10/10 | 21 | 1681 | 4.7 | 4.7 |

原因是可解释的：调度 Agent 把同一问题拆给图、向量、研究库三类 worker 并行检索，审核 Agent 再把乐观证据与
风险证据放在一起比对，于是 `optimistic_vs_risk` 这类冲突被显式识别出来（例：`theme_invest` 单臂检出 0 组，
多智能体检出 3 组）。冲突被检出后，`verification_status` 按设计把结论降级为 `warn`（"结论需保守解释"），
所以多智能体的"校验通过率 0.00"**不是质量更差，而是更少过度自信**——单臂那 7 个 `pass` 里有 5 个是
"没检索到反方证据，所以没发现冲突"。

### 6.3 代价

| 指标 | `single` | `multi_1` | `multi_3` | 倍数 |
| --- | --- | --- | --- | --- |
| LLM 调用（次/题） | 2.0 | 10.2 | 10.2 | ≈5.1× |
| 延迟 p50（秒） | 15.1 | 23.5 | 25.7 | ≈1.6–1.7× |
| 选中证据卡 | 6.0 | 4.3 | 4.7 | 0.7–0.8× |

多智能体每道题多花约 8 次 LLM 调用、多等约 9 秒，换来的是冲突识别与更长的分析；单臂的答案更短、引用更多，
但在"是否存在反方证据"这件事上是盲的。

## 七、实验中发现并修复的缺陷：预算耦合把答案饿死

跑第一轮全量实验时，多智能体的答案异常地短，而且和"最努力"的题目反相关。定位到两个事实：

1. `CentralLLMBudget`（`aika/agents/coordination/budget.py`）把**检索规划**（`chat_json`，调度/改写/审核）
   与**答案生成**（`chat_text`，`role="answer"`）放在同一个 12 次预算里。
2. 补检轮次一多，规划就把预算吃光，`AgentTools.generate_answer` 抛
   `LLM answer failed: LLM call budget exhausted (24)`（把预算抬到 24 也一样，因为 4 轮 × 4 worker 的 JSON
   调用会再次吃满），答案于是退回 `fallback_professional_answer` 模板——932 字的"核心判断/技术机理/产业传导"填空。

修复：给 `CentralLLMBudget` 增加 `generation_reserve`（默认 2）——非生成角色最多用到 `max_calls - reserve`，
生成角色（`answer` / `summarizer`）可以用满全部预算，并新增 `tests/test_coordination_budget.py` 三条断言。
修复后同一道题（`risk_liquid`）的答案从 932 字模板变成 2723 字分析，全量实验里 `multi_3` 的答案平均字数
由 1106 涨到 1681、引用从 3.9 涨到 4.7。

这条缺陷本身也是结论的一部分：**多智能体的收益会被共享预算抵消**，如果不同时为"生成"预留配额，
补检越努力、答案越差。

## 八、要让多智能体真正赢，需要改什么

1. **补检换维度，而不是换问法**：缺口是 `mechanism_evidence` 时，应该带 `claim_type` 过滤去检索，
   或者切换到证据 span / 年报原文，而不是给原问题加一个"技术机理"后缀。
2. **预算分层**：检索预算与生成预算分开计数（本次已做最小版本：`generation_reserve`）。
3. **语料补齐**：液冷主题缺风险与机理证据，任何编排都补不出来；这属于数据工程而不是架构问题。

## 九、简历与面试怎么写（诚实版）

不要写"多智能体提升了问答准确率"——数据不支持，一追问就会崩。可以写：

> 在 10 题、3 臂、统一裁判的消融实验中，量化了 supervisor 式多智能体与本项目单趟流水线的差异：
> 证据覆盖率持平（0.50 vs 0.50，瓶颈是语料而非编排），但多智能体把冲突/反证识别从 3/10 提升到 10/10
> （21 组 vs 3 组），代价是 5.1× LLM 调用与 1.7× 延迟；实验中定位到"检索预算饿死答案生成"的耦合缺陷，
> 通过为生成角色预留预算修复，使多智能体答案长度提升 52%、引用数提升 21%。

被追问时的三句话：①覆盖率为什么没涨——语料里 21 条 risk claim 没有一条提到液冷；②为什么校验通过率反而降了——
因为检出冲突就会降级为 warn，这是设计意图；③5 倍成本值不值——取决于是否需要"发现反方证据"，需要就值。


## 十、复现方式

```powershell
# 需要 PostgreSQL（paradedb/paradedb:0.24.0-pg17 或自带 pgvector 的实例）与 .env 里的 LLM Key
$env:QA_DISABLE_POSTGRES='false'; $env:KG_DATA_DIR='data/verified'
python scripts/experiments/ab_agents.py --out docs/experiments/ab_agents.json
python scripts/experiments/make_report.py --in docs/experiments/ab_agents.json --out docs/experiments/single-vs-multi-agent.md
```

