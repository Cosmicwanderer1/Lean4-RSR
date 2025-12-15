# 字段映射规范

## 数据集字段（LeanDojo提取）

**文件**: `data/raw/train_samples_1000.jsonl`

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `full_name` | str | 定理完整名称 | `linear_map.fun_left_injective_of_surjective` |
| `state` | str | 完整Lean proof state (`context ⊢ goal`) | `R : Type u_1,\n...\n⊢ injective ...` |
| `context` | str | 分离的上下文（⊢左边） | `R : Type u_1,\n_inst_1 : semiring R,...` |
| `goal` | str | 分离的目标（⊢右边） | `injective ⇑(fun_left R M f)` |
| `theorem` | str | 定理声明 | `theorem linear_map.fun_left... : ...` |
| `proof` | str | Tactic序列 | `obtain ⟨g, hg⟩ := ...\nsuffices : ...` |
| `imports` | list | 使用的模块 | `["Mathlib.Algebra.Module.Linear_map"]` |
| `difficulty` | str | 推断难度 | `easy`, `medium`, `hard` |
| `num_tactics` | int | Tactic数量 | `5` |
| `used_theorems` | list | 使用的定理详情 | `[{full_name, def_path, ...}]` |
| `file_path` | str | 源文件路径 | `src/linear_algebra/basic.lean` |

## Pipeline字段映射

### Phase 1: Forward Planning

**输入字段** (从数据集):
- `full_name` → 用于标识
- `theorem` → 定理声明
- `state` → 完整proof state
- `context` → 上下文
- `goal` → 目标
- `imports` → 导入模块

**输出字段** (`data/step1_forward/forward_planning.jsonl`):
- `decl_name` ← `full_name`
- `statement` ← `theorem`
- `state` ← `state`
- `problem_type` ← 推断的问题类型
- `proof_strategy` ← 推荐的证明策略

### Phase 2: Backward Analysis

**输入字段** (从数据集):
- `full_name` → 用于标识
- `theorem` → 定理声明（作为`statement`）
- `proof` → 完整证明（⚠️ 不是`golden_proof`）
- `state` → 完整proof state
- `context` → 上下文
- `goal` → 目标
- `imports` → 导入模块

**输出字段** (`data/step2_backward/backward_analysis.jsonl`):
- `decl_name` ← `full_name`
- `statement` ← `theorem`
- `state` ← `state`
- `backward_analysis`:
  - `proof_structure` ← 分析的证明结构
  - `key_transitions` ← 关键状态转换
  - `reasoning_chain` ← 推理链

### Phase 3: Consensus (V2)

**输入字段** (合并Forward和Backward):

#### Stage 1: ScoringJudgeV2
```python
{
    'decl_name': forward['decl_name'],  # 定理名
    'statement': theorem_statement,     # 定理声明
    'state': state_context,            # 完整state
    'context': context,                # 分离的上下文（新增）
    'goal': goal,                      # 分离的目标（新增）
    'forward_type': forward['problem_type'],
    'forward_strategy': forward['proof_strategy'],
    'backward_structure': backward['proof_structure'],
    'backward_transitions': backward['key_transitions'],
    'backward_reasoning': backward['reasoning_chain']
}
```

#### Stage 2: StepByStepReasonerV2
```python
{
    'decl_name': full_name,
    'statement': theorem_statement,
    'state': state_context,
    'context': context,                # 分离的上下文（新增）
    'goal': goal,                      # 分离的目标（新增）
    'priority': score_result.priority,
    'confidence': score_result.confidence,
    'forward_score': score_result.forward_total,
    'backward_score': score_result.backward_total,
    'forward_weight': forward_weight,
    'backward_weight': backward_weight,
    'forward_strategy': forward['proof_strategy'],
    'backward_structure': backward['proof_structure'],
    'backward_reasoning': backward['reasoning_chain']
}
```

#### Stage 3: SkeletonGeneratorV2
```python
{
    'statement': theorem_statement,
    'state': state_context,
    'context': context,                # 分离的上下文（新增）
    'goal': goal,                      # 分离的目标（新增）
    'step_by_step_reasoning': step_by_step,
    'forward_score': score_result.forward_total,
    'backward_score': score_result.backward_total,
    'original_difficulty': difficulty  # 从数据集传递
}
```

**输出字段** (`data/step3_consensus_v2/enhanced_consensus.jsonl`):
- `decl_name` ← `full_name`
- `statement` ← 补全后的定理声明
- `proof_skeleton` ← 生成的骨架
- `metadata`:
  - `difficulty_level` ← 推断或使用`original_difficulty`
  - `generation_mode` ← 生成模式
  - `forward_score` / `backward_score`
  - `combined_score`

## 关键字段映射规则

### ✅ 正确映射
- 数据集 `full_name` → Pipeline `decl_name`
- 数据集 `theorem` → Pipeline `statement`
- 数据集 `proof` → Backward `{proof}` （⚠️ 不是`golden_proof`）
- 数据集 `state` → 所有组件 `state`
- 数据集 `context` → 所有组件 `context` (新增)
- 数据集 `goal` → 所有组件 `goal` (新增)
- 数据集 `difficulty` → Skeleton `original_difficulty`

### ❌ 常见错误
- ~~`golden_proof`~~ → 应使用 `proof`
- ~~直接使用`state`解析~~ → 应优先使用分离的`context`和`goal`
- ~~忽略`difficulty`字段~~ → 应传递给Skeleton作为`original_difficulty`

## 字段验证清单

在修改prompt或pipeline时，确保：

- [ ] 所有`data.get()`使用正确的字段名
- [ ] 模板`{}`中的字段名与数据集一致
- [ ] Forward/Backward输出使用`decl_name`（不是`full_name`）
- [ ] Backward使用`{proof}`（不是`{golden_proof}`）
- [ ] 所有组件都接收`context`和`goal`分离字段
- [ ] `original_difficulty`正确传递到Skeleton生成

## 测试验证

运行字段一致性检查：
```bash
python check_field_consistency.py
```

预期输出：
```
✓ 所有字段一致性检查通过
```
