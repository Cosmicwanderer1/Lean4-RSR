# 🎓 骨架生成器教学化改造 (Skeleton Pedagogy Update)

## 📋 改造背景

**原问题:** 系统倾向生成完整证明,偏离"骨架生成"的教学初衷

**核心矛盾:**
- ❌ 旧设计:自动化证明器 → 给出完整答案
- ✅ 新设计:教学工具 → 提供框架,引导思考

## 🎯 新设计哲学

### 核心原则

```
提供框架 ≠ 提供答案
引导思考 > 替代思考
战略性留白 = 学习机会
```

### 四大支柱

1. **Skeleton Suitability (骨架适合性)**
   - 评估:是否提供框架而非完整证明
   - 标准:完整证明 → 0-3分,适当框架 → 7-10分

2. **Guidance Quality (引导性)**
   - 评估:注释是否帮助理解而非直接给答案
   - 标准:提问式引导 > 陈述式答案

3. **Structural Clarity (结构清晰度)**
   - 评估:证明架构是否清晰易懂
   - 标准:逻辑流畅,层次分明

4. **Appropriate Gaps (适当留白)**
   - 评估:`sorry` 是否在关键学习点
   - 标准:战略性空缺,非随意省略

## 📊 自适应策略调整

### Easy Theorems (≥70%)
**旧策略:** 生成完整证明
```lean
theorem foo : n + 0 = n := by
  exact Nat.add_zero n  ❌ 直接给答案
```

**新策略:** 最小化框架
```lean
theorem foo : n + 0 = n := by
  -- Question: Which lemma handles addition with zero?
  -- Hint: Consider commutativity or definitional equality
  sorry  ✓ 引导发现
```

### Medium Theorems (50-70%)
**旧策略:** 部分框架+TODO
```lean
induction xs with
| nil => sorry  -- TODO: Use nil_append
```

**新策略:** 结构化路线图
```lean
induction xs with
| nil => 
  -- Base Case: Prove ([] ++ ys).length = 0 + ys.length
  -- Strategy: Simplify left side using definition
  -- Question: What is [] ++ ys by definition?
  sorry
```

### Hard Theorems (<50%)
**旧策略:** 详细注释但仍给出关键引理
```lean
have h : ... := by
  -- Use ZMod.isUnit_of_coprime
  sorry
```

**新策略:** 教学式蓝图
```lean
have h : IsUnit (a : ZMod p) := by
  -- Why we need this: Units form a group for Lagrange's theorem
  -- Approach options:
  --   1. Direct: Use coprimality condition
  --   2. Contrapositive: Show non-unit → divisible
  -- Key insight: In ℤ/pℤ, coprime ↔ unit
  -- Where to look: Explore ZMod.isUnit_* lemmas
  sorry
```

## 🚫 反模式识别

### ❌ Bad Patterns (自动给答案)
```lean
-- BAD: 直接解决
rw [Nat.add_comm]

-- BAD: 精确指定引理
exact some_specific_lemma x y proof

-- BAD: 完整子证明
apply le_antisymm
· exact some_lemma
· exact another_lemma
```

### ✅ Good Patterns (引导学习)
```lean
-- GOOD: 提示方向
-- Hint: Try commutativity or associativity
sorry

-- GOOD: 引导探索
-- TODO: Prove monotonicity
-- Approach: Look for lemmas about order preservation
sorry

-- GOOD: 结构化引导
-- Step 1: Establish upper bound
have h_upper : ... := by sorry
-- Step 2: Establish lower bound  
have h_lower : ... := by sorry
-- Step 3: Combine using antisymmetry
sorry
```

## 📈 预期效果

### 训练数据质量提升
- **旧模式:** 学到"记忆答案" → 泛化能力差
- **新模式:** 学到"推理过程" → 迁移能力强

### 用户体验改善
- **旧模式:** 直接给答案 → 失去学习机会
- **新模式:** 渐进式引导 → 深度理解

### 评分更合理
```
完整证明(Easy题): Suitability 8/10 → 2/10
框架引导(Easy题): Suitability 3/10 → 9/10

完整证明(Hard题): Suitability 5/10 → 1/10  
详细蓝图(Hard题): Suitability 6/10 → 10/10
```

## 🔧 技术实现亮点

### 1. 动态难度感知
```python
if combined_score >= 56:  # Easy
    mode = "Minimal Framework"
    sorry_count = "1-2"
elif combined_score >= 40:  # Medium
    mode = "Structured Roadmap"
    sorry_count = "3-5"
else:  # Hard
    mode = "Detailed Blueprint"
    sorry_count = "5-10"
```

### 2. 教学价值度量
```
Metadata增加:
- Teaching Value: High/Medium/Low
- Teaching Focus: Framework/Roadmap/Blueprint
- Estimated Completion Time: 15min/45min/2hr
```

### 3. 反馈机制
通过 `skeleton_metadata` 提供自我评估维度,帮助后续迭代优化

## 🎯 验证检查清单

运行 pipeline 后,检查生成的骨架:

- [ ] Easy 题是否避免了完整证明?
- [ ] 注释是否以提问/提示为主,而非直接答案?
- [ ] `sorry` 是否在有意义的学习点?
- [ ] 结构是否清晰到可以理解证明思路?
- [ ] 是否有足够的留白让用户填充?

## 📝 测试建议

```bash
# 重新生成骨架
python run_phase3_v2_pipeline.py \
  --forward-file data/step1_forward/forward_planning.jsonl \
  --backward-file data/step2_backward/backward_analysis.jsonl \
  --max-samples 5

# 人工检查生成质量
# 重点关注:
# 1. Sorry 数量是否合理(Easy:1-2, Medium:3-5, Hard:5-10)
# 2. 注释风格是否引导式而非答案式
# 3. 结构是否保留但细节留白
```

---

**核心理念:** 好的教学工具不是给答案,而是指明方向! 🧭
