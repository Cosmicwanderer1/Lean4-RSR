**增强版共识系统设计文档（Consensus V2）**

- **目的**：在 Forward（正向探索）与 Backward（逆向分析）已有输出基础上，引入可解释的评分机制并基于评分进行加权融合；生成详尽的逐步思路（step-by-step reasoning），并将思路转换为可编译的 Lean 4 骨架用于训练与验证。

**概览**
- 三阶段流水线：
  - **Phase 1 — Scoring（评分）**：对 Forward 与 Backward 的结果分别量化评分，输出权重与优先级建议；评分由 LLM 按照明确的四维准则（Completeness、Accuracy、Specificity、Feasibility）分别评分并给出理由。
  - **Phase 2 — Step-by-Step Reasoner（逐步推理）**：根据评分结果按比例加权融合两边信息，生成原子、可追踪、按序的思维步骤（每步包含 Goal/Action/Insight）。
  - **Phase 3 — Skeleton Generator（骨架生成）**：把逐步推理映射为 Lean 4 可编译骨架（使用 `sorry` 填充细节），并产生元数据（主要战术、步骤数、是否预期可编译）。

**设计目标与约束**
- 可解释性：评分与加权需有清晰理由，且以 XML/结构化文本输出，便于审查与统计。
- 可训练性：最终输出应可直接用于 LoRA/QLoRA 等微调样本（包含思路/骨架/评分元信息）。
- 鲁棒性：对 LLM 可能出现的截断/未闭合标签有容错解析逻辑。
- 可控性：权重计算必须清晰、可复现（例如权重按总分占比），并允许手动覆盖。

**详细规范**
- 输入：
  - `forward_result`（JSON 对象）：必含 `id`, `statement`, `proof_strategy`, `key_tactics`, `proof_steps` 等字段。
  - `backward_result`（JSON 对象）：必含 `id`, `statement`, `proof_structure`, `key_transitions`, `proof_skeleton`, `reasoning_chain` 等字段。

- Phase 1 输出格式（XML）样式：
  - `<consensus_result>`
    - `<forward_score>`: 各项分数与总分（例如：Total: XX/40）
    - `<backward_score>`: 各项分数与总分
    - `<score_explanation>`: 逐项理由与权重决策说明
    - `<priority_recommendation>`: `Priority`、`Reason`、`Confidence`
  - 解析：代码将从标签中提取 `Total`，并由 `forward_total` 与 `backward_total` 计算权重：
    - forward_weight = forward_total / (forward_total + backward_total) * 100
    - backward_weight = 100 - forward_weight
  - 支持手动阈值：若任一方总分 >= 32（80%），可直接设为高优先并把权重限定为 e.g. 80/20。

- Phase 2 输出规范：
  - `<step_by_step_reasoning>` 节点必须按序编号（Step 1, Step 2, ...），每步包含：
    - **Goal**：本步目标
    - **Action**：可执行的 tactic/操作（尽可能与 Lean 4 术语一致，如 `intro`, `induction`, `cases`, `simp`, `rw` 等）
    - **Insight**：引用来源（Forward/Backward）与简短理由
  - `<key_insights>`：2–5 个最关键的洞见
  - 质量评估：可在返回 JSON 中额外带 `reasoning_quality` 字段（Excellent/Good/Fair）以便后续筛选训练样本。

- Phase 3 输出规范：
  - `<proof_skeleton>`：包含 ```lean
    ... ``` 代码块，保证保留原定理声明和 `:= by` 结构；步骤映射为注释（`-- Step i:`），并在关键位置用 `sorry` 填充。
  - `<skeleton_metadata>`：`total_steps`, `main_tactic`, `key_lemmas`, `compilation_status`（预期）
  - `compilation_ready` 布尔指示器（pipeline 层面简单用语法检查启发式判断：是否包含 `theorem` 与 `:= by`）

**权重与融合策略（范式）**
- 默认：基于总分按比例混合。
  - fused_item = forward_weight% * normalized_forward_item + backward_weight% * normalized_backward_item
- 对于“结构性”信息（proof_structure、key_transitions）优先使用 Backward；对于“策略细节/战术顺序”优先使用 Forward。
- 在实现中：
  - Step 的生成过程会把每个建议（来自 Forward 或 Backward）附带来源标签与置信度分数，StepByStepReasoner 在生成步骤时会把高权重来源的句子作为首要依据，并用低权重来源补充替代或后续步骤。

**逐步推理生成器实现要点**
- 模板应强制要求每步提供 Goal/Action/Insight，Insight 必须标注来源（F/B）和一句 8–20 字的理由。
- 避免长段话，步骤应“原子化”：每步不超过 3 行核心行动。
- 当出现分支（case-splits）时，需产生明确的子步骤，形如：
  - Step 4a: 处理 case A
  - Step 4b: 处理 case B

**骨架生成器实现要点**
- 映射规则示例：
  - `Intro`/`assume` -> `intro` 或 `intro h` 注释
  - `Induction` -> `induction h with | base => ... | step => ...` 模板
  - 分支 -> `| case1 =>` / `| case2 =>` 结构
- 为便于自动验证，骨架须包含注释映射到逐步推理的 Step 编号：`-- Step 3: Decompose goal`。
- 对难以自动决定的 tactic，可在注释中提示候选：`-- Suggested tactic: rw [lemma_name]`。

**容错与解析**
- LLM 输出可能被截断或未闭合 XML 标签：解析器应：
  - 支持非严格闭合的贪婪正则解析，尝试提取最重要块（score、reasoning、skeleton）。
  - 对未命中标签，退回到关键关键字/代码块提取（例如提取 ` ```lean ... ``` ` 作为骨架）。

**接口与 CLI**
- 主运行命令（示例）：
```powershell
python run_phase3_v2_pipeline.py --api-key <KEY> --max-samples 10 --forward-file data/step1_forward/forward_planning.jsonl --backward-file data/step2_backward/backward_analysis.jsonl --output-file data/step3_consensus_v2/enhanced_consensus.jsonl
```
- 环境变量支持：`DEEPSEEK_API_KEY` 作备选。

**测试、验证与评估**
- 单样本快速验收：选 5 个带有 `golden_proof` 的样本，逐步检查：
  - Score 是否合理（手工验证）
  - Step-by-step 是否原子、连贯
  - Skeleton 是否语法上接近可编译（人工或自动脚本检测 `theorem`/`:= by` 存在）
- 自动指标：
  - 平均 Forward/Backward 总分分布
  - Step 数与 key_insights 数统计
  - 骨架 `compilation_ready` 占比

**示例（精简）**
- Phase 1 输出片段：
```xml
<consensus_result>
  <forward_score>...
  </forward_score>
  <backward_score>...
  </backward_score>
  <score_explanation>...</score_explanation>
  <priority_recommendation>
    Priority: Backward
    Reason: Clear structural decomposition
    Confidence: High
  </priority_recommendation>
</consensus_result>
```
- Phase 2 `<step_by_step_reasoning>` 示例：
```
Step 1: Introduce assumptions
**Goal:** Expose hypothesis h
**Action:** `intro h`
**Insight:** (F) Forward suggested intro; (B) matches skeleton entry point
```
- Phase 3 `<proof_skeleton>` 示例（片段）：
```lean
theorem sample_theorem (x : α) (h : P x) : Q x := by
  -- Step 1: Introduce assumptions
  intro h
  -- Step 2: Reduce to simpler lemma
  apply LemmaA
  sorry
```

**训练集格式与存储**
- 每条样本写入 JSONL，字段包含：`id`, `statement`, `scoring`（结构化）, `reasoning`（文本/HTML/XML）, `skeleton`（lean code string）, `metadata`。
- 建议路径：`data/step3_consensus_v2/enhanced_consensus.jsonl`。

**评估指标建议（训练后）**
- 精确度（可由 Lean 验证器在细节补全后衡量）
- 可读性评分（人工或 LLM 自动评估）
- 案例覆盖度（不同难度/主题分布）

**逐步迭代计划（短期）**
1. 运行 5–20 个样本，人工审查输出（评分与思路质量）。
2. 调整评分模板的权重阈值或更多评分维度。 
3. 增加自动化检查：语法检测、标签完整性告警。

**风险与缓解**
- 风险：LLM 输出不一致或过度偏向某一方。缓解：在 pipeline 中加入正则化（例如最小/最大权重阈值）和人工审核回路。
- 风险：生成骨架不可编译。缓解：扩大注释提示、生成更多候选骨架供筛选。

**下一步（建议）**
- 立刻运行 `run_phase3_v2_pipeline.py` 对 5 个样本进行验证。
- 把人工发现的问题（评分偏差、step 不原子等）以 issue 形式记录并迭代提示词。

---

文件位置建议：`ARCHITECTURE_CONSENSUS_V2.md`（项目根），并在 `README.md` 中加入快速入口。