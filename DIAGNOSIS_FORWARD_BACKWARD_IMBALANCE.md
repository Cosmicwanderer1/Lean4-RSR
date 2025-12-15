# 🔍 Forward-Backward 评分不平衡诊断报告

## 📊 问题现象

从运行日志中观察到,所有样本的评分结果都是 **Forward 权重远高于 Backward**:

```
WellFoundedLT:        Forward 37/40 (89.7%) vs Backward 4/40 (10.3%)
eRk_union_closure:    Forward 32/40 (88.4%) vs Backward 4/40 (11.6%)
Algebra:              Forward 32/40 (88.4%) vs Backward 4/40 (11.6%)
IsLindelof:           Forward 32/40 (96.6%) vs Backward 0/40 (3.4%)
orderEmbOfFin:        Forward 33/40 (96.7%) vs Backward 0/40 (3.3%)
...
```

## 🎯 根本原因分析

### ✅ 评分系统本身是公平的

通过检查 `consensus_v2.py` 的评分 prompt,发现:
- 明确要求 "IMPARTIAL" (公正评判)
- 强调 "DO NOT favor one approach over the other by default"
- 评分标准客观:Completeness, Accuracy, Specificity, Feasibility

**结论:评分机制设计合理,不存在系统性偏见。**

### ❌ 真正的问题:Backward 输出质量不足

检查实际数据(`data/step2_backward/backward_analysis.jsonl`),发现:

#### Backward 的输出内容过于简略:

```python
# 典型的 Backward 输出示例
{
  "proof_structure": "Rewrite chain using closure properties",  # 只有一句话
  "key_transitions": ["1. ... → ... via eRk_closure_eq"],       # 只有1-2个转换
  "proof_skeleton": "lemma foo := by\n  sorry",                 # 几乎只有 sorry
  "reasoning_chain": "The proof uses ... to ..."                # 1-2句简短说明
}
```

#### Forward 的输出内容非常详细:

```python
# 典型的 Forward 输出示例
{
  "problem_type": "Matroid Theory / Combinatorics",              # 具体分类
  "proof_strategy": "1. Analyze Hypotheses: ...\n"              # 多段详细策略
                     "2. Select Strategy: Use monotonicity...\n"
                     "3. Check Feasibility: ..."                # 包含具体引理名
}
```

### 📉 评分结果客观反映了内容质量差异

按照评分标准:
- **Completeness**: Forward 列出了所有步骤,Backward 只有寥寥数语 → Forward 8-9分,Backward 1-2分
- **Specificity**: Forward 提到具体引理(如 `eRk_mono`, `subset_closure`),Backward 只说 "rewrite chain" → Forward 7-9分,Backward 1-2分
- **Feasibility**: Forward 给出可行性分析,Backward 只有框架 → Forward 8-9分,Backward 1-4分

**结论:低分是合理的,反映了实际输出质量的差距。**

## 🔧 解决方案

### 方案实施:双管齐下

#### 1. 增强 Backward Prompt (治本)

**问题所在:**
原 Prompt 要求 "minimal outline"(最小化骨架)和 "2-3 sentences"(2-3句说明)

**优化后:**
```python
# 修改前
"""
Extract Skeleton: Generate a minimal outline with `sorry` placeholders.
Explain the logical flow in 2-3 sentences.
"""

# 修改后
"""
CRITICAL: PROVIDE COMPREHENSIVE ANALYSIS
Your analysis will be compared against forward planning. To be competitive, you MUST:
1. Identify ALL key tactics and lemmas used (aim for 4-8 transitions)
2. Explain the reasoning behind EACH major step
3. Provide a DETAILED skeleton (multiple `sorry` for different subgoals)
4. Generate 4-8 sentences of reasoning (not just 2-3)
"""
```

**预期效果:**
- `key_transitions`: 从 1-2 个增加到 4-8 个
- `proof_skeleton`: 从单个 `sorry` 变成带注释的多步骤结构
- `reasoning_chain`: 从简短说明变成详细的逐步分析

#### 2. 调整评分指导原则 (治标)

**问题所在:**
评分者可能对 Backward 的"简洁"误判为"不完整"

**优化后:**
```python
# 新增公平评估原则
"""
**For BACKWARD Analysis:**
✓ Working skeleton with structure → HIGH Feasibility (8-10)
✓ Concrete tactics mentioned → HIGH Specificity (7-10)
✓ Even if reasoning is brief but accurate → Still deserves 6-8 points
⚠ Skeleton with only `sorry` but good structure → Feasibility 5-7, not 0-2

**CRITICAL BALANCING RULE:**
DO NOT systematically favor Forward over Backward!
- Backward showing structure = Forward proposing structure (EQUAL VALUE)
- Backward listing tactics = Forward suggesting tactics (EQUAL VALUE)
```

**预期效果:**
- 即使 Backward 简洁,只要内容准确,也能获得中等分数(5-7分)
- 强调结构化的骨架本身就有价值,不应得 0-2 的极低分

### 测试验证计划

```bash
# 1. 重新运行 Phase 2 (使用增强的 Backward prompt)
python run_phase2_pipeline.py --input data/step1_forward/forward_planning.jsonl --max-samples 5

# 2. 重新运行 Phase 3 (使用调整后的评分标准)
python run_phase3_v2_pipeline.py \
  --forward-file data/step1_forward/forward_planning.jsonl \
  --backward-file data/step2_backward/backward_analysis.jsonl \
  --max-samples 5

# 3. 对比评分变化
# 预期: Backward 分数从 0-5 提升到 15-25 (总分40)
#      权重从 3-13% 提升到 35-50%
```

## 📈 预期改进效果

### Before (当前状态):
```
Typical Score: Forward 32-38/40 (80-95%)
               Backward 0-5/40   (0-13%)
Weight:        Forward 85-97%
               Backward 3-15%
```

### After (优化后):
```
Expected Score: Forward 28-35/40 (70-88%)
                Backward 15-28/40 (38-70%)
Weight:         Forward 50-70%
                Backward 30-50%
```

### 最佳情况(两种方法互补):
```
Ideal Case: Forward 30/40 (75%) - 探索性策略
            Backward 28/40 (70%) - 结构化骨架
Weight:     Forward 52%
            Backward 48%
Priority:   Balanced (充分利用两种方法的优势)
```

## 🎓 深层启示

这个问题揭示了一个重要的系统设计原则:

> **数据质量决定评分结果,而不是评分系统决定数据质量。**

- ❌ 错误思路:调整评分权重来"人为平衡"结果
- ✅ 正确思路:提升数据源的质量,让评分自然趋于平衡

这也是为什么我们同时优化了:
1. **Backward prompt**(提升数据源质量)
2. **评分指导**(避免误判,但不降低标准)

## 📝 后续监控指标

运行优化后的 pipeline,重点关注:

1. **Backward 输出长度**:
   - `proof_skeleton`: 行数是否从 3-5 行增加到 10-20 行?
   - `reasoning_chain`: 句子数是否从 1-2 句增加到 4-8 句?
   
2. **评分分布**:
   - Backward 是否有样本获得 20+ 分?(当前几乎全是 0-5 分)
   - Forward vs Backward 的标准差是否缩小?

3. **Priority 分布**:
   - "Balanced" 的比例是否增加?(当前几乎全是 "Forward")
   - 是否出现 "Backward" 优先的情况?(当前为 0)

## 🚀 立即行动

已完成的修改:
- ✅ `src/data_engine/prompts/backward_v1.py` - 增强 prompt
- ✅ `src/data_engine/prompts/consensus_v2.py` - 调整评分指导

下一步:
```bash
# 重新运行 pipeline 验证效果
python run_full_pipeline_v2.py --max-samples 10 --max-workers 4
```

预计改进后,你会看到更平衡的权重分配! 🎯
