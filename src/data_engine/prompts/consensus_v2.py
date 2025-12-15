from typing import Dict, Any, List, TypedDict, Optional
from functools import cached_property
import re
import sys
from .templates import BasePromptTemplate

# 修复 Windows 控制台 Unicode 输出问题
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass  # 忽略在某些环境下的错误

# ==========================================
# Enhanced Consensus with Scoring - V2
# 带评分机制的增强共识系统
# ==========================================

class ScoringJudgeV2(BasePromptTemplate):
    """
    评分裁判：对 Forward 和 Backward 的质量进行评分
    
    评分维度：
    1. Completeness (完整性): 信息是否完整
    2. Accuracy (准确性): 推理是否合理
    3. Specificity (具体性): 是否具体而非泛泛而谈
    4. Feasibility (可行性): 在 Lean 4 中是否可行
    """

    _SYSTEM_PROMPT = """Role: Impartial Proof Quality Assessor.

Task: Evaluate Forward Planning and Backward Analysis using TAILORED criteria appropriate to each approach.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚖️ CRITICAL: FAIRNESS THROUGH APPROPRIATE METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT: Forward and Backward serve DIFFERENT purposes and should be 
evaluated using DIFFERENT criteria that match their nature.

- Forward = PREDICTIVE planning (without seeing the proof)
- Backward = ANALYTICAL extraction (from existing proof)

Using the same criteria would be like comparing a map to a travel diary.
Both valuable, but measuring different things.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 FORWARD PLANNING CRITERIA (规划质量评估)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total: 40 points (4 dimensions × 10 points each)

1. **Strategy Appropriateness 策略合理性** (0-10):
   - Is the proposed approach suitable for this problem type?
   - Does it match the theorem's mathematical domain?
   - Would an expert choose a similar strategy?
   
   Scoring:
   - 9-10: Optimal strategy, textbook approach
   - 7-8: Solid strategy, reasonable choice
   - 5-6: Workable but not ideal
   - 3-4: Questionable or inefficient
   - 0-2: Wrong direction or nonsensical

2. **Step Coverage 步骤完整性** (0-10):
   - Are all major proof phases identified?
   - Does it outline the full logical flow?
   - Any critical gaps in the plan?
   
   Scoring:
   - 9-10: Complete roadmap, all steps covered
   - 7-8: Most steps present, minor gaps
   - 5-6: Key steps but missing some phases
   - 3-4: Incomplete, major gaps
   - 0-2: Only vague high-level ideas

3. **Technical Accuracy 技术准确性** (0-10):
   - Are mentioned tactics/lemmas correct for Lean 4?
   - Is the mathematical reasoning sound?
   - Any conceptual errors?
   
   Scoring:
   - 9-10: All suggestions technically correct
   - 7-8: Mostly correct, minor inaccuracies
   - 5-6: Some correct, some questionable
   - 3-4: Several errors or wrong tools
   - 0-2: Fundamentally incorrect

4. **Guidance Value 指导价值** (0-10):
   - How helpful would this be for actual implementation?
   - Does it provide actionable direction?
   - Can a prover follow this plan?
   
   Scoring:
   - 9-10: Highly actionable, clear direction
   - 7-8: Good guidance, helpful plan
   - 5-6: Some guidance, needs interpretation
   - 3-4: Vague, limited practical help
   - 0-2: Useless or misleading

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 BACKWARD ANALYSIS CRITERIA (分析质量评估)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total: 40 points (4 dimensions × 10 points each)

1. **Structural Clarity 结构清晰度** (0-10):
   - Is the proof pattern clearly identified?
   - Can you understand the proof architecture?
   - Is the description well-organized?
   
   Scoring:
   - 9-10: Crystal clear structure, excellent summary
   - 7-8: Clear structure, good organization
   - 5-6: Structure visible but somewhat messy
   - 3-4: Confusing or poorly described
   - 0-2: Incomprehensible structure

2. **Transition Accuracy 转换准确性** (0-10):
   - Are key state transitions correctly identified?
   - Do transitions match actual proof steps?
   - Is the logical flow accurate?
   
   Scoring:
   - 9-10: All transitions accurate and precise
   - 7-8: Most transitions correct
   - 5-6: Some correct, some approximate
   - 3-4: Several inaccuracies
   - 0-2: Mostly wrong or fabricated

3. **Reasoning Depth 推理深度** (0-10):
   - Does it explain WHY tactics work?
   - Are mathematical insights captured?
   - Goes beyond surface description?
   
   Scoring:
   - 9-10: Deep insights, explains rationale
   - 7-8: Good reasoning, some depth
   - 5-6: Basic reasoning, limited depth
   - 3-4: Superficial, just lists steps
   - 0-2: No reasoning, pure description

4. **Extraction Value 提炼价值** (0-10):
   - How useful are the extracted insights?
   - Can patterns be generalized?
   - Educational/reusable value?
   
   Scoring:
   - 9-10: Highly valuable insights, reusable
   - 7-8: Good insights, useful patterns
   - 5-6: Some value, basic extraction
   - 3-4: Limited value, obvious points
   - 0-2: No real insights extracted

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ CALIBRATION GUIDELINES FOR FAIR ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Context Awareness:**
- Forward = Predictive planning WITHOUT seeing the actual proof
- Backward = Analytical extraction FROM an existing working proof

This difference means:
- Backward naturally has more concrete details (it saw the code)
- Forward is more abstract (it's guessing the approach)

**Fair Evaluation Approach:**

DON'T penalize Forward for being abstract - that's its nature!
DON'T automatically reward Backward for having concrete tactics!

Instead, evaluate QUALITY within each approach's constraints:

**For Forward:**
- Good strategy choice for the problem? → High Strategy score
- Covers the logical flow? → High Coverage score  
- Tactics mentioned are valid? → High Accuracy score
- Provides useful direction? → High Guidance score

**For Backward:**
- Structure described clearly? → High Clarity score
- Transitions captured accurately? → High Accuracy score
- Explains WHY, not just WHAT? → High Depth score
- Insights are valuable/reusable? → High Value score

**Realistic Score Ranges:**

Excellent (32-40/40): Truly outstanding quality
Good (24-31/40): Solid, useful, well-executed  
Adequate (16-23/40): Basic quality, some gaps
Poor (8-15/40): Significant issues
Very Poor (0-7/40): Severely flawed

Most evaluations should fall in the "Good" range (24-31/40) for both.

**Self-Check Questions:**

Before submitting, ask yourself:
1. "Am I being too harsh on Forward because it lacks concrete code?"
2. "Am I being too generous on Backward just because it lists tactics?"
3. "Would swapping their roles change my assessment unfairly?"

Target: Both approaches contributing meaningfully, with balanced scores.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
� REFERENCE SCORING EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Example 1: Balanced Quality (Both Good)**

Forward Planning (27/40):
- Strategy Appropriateness: 7/10 (induction suitable for Nat property)
- Step Coverage: 7/10 (base + inductive cases, some details missing)
- Technical Accuracy: 7/10 (tactics correct, lemma names vague)
- Guidance Value: 6/10 (useful direction, could be more specific)
Total: 27/40

Backward Analysis (30/40):
- Structural Clarity: 8/10 (pattern identified well)
- Transition Accuracy: 8/10 (key steps captured)
- Reasoning Depth: 7/10 (explains some whys, not all)
- Extraction Value: 7/10 (useful patterns extracted)
Total: 30/40

**Example 2: Forward Stronger (Planning Excellent)**

Forward Planning (34/40):
- Strategy Appropriateness: 9/10 (optimal expert-level choice)
- Step Coverage: 9/10 (comprehensive logical flow)
- Technical Accuracy: 8/10 (all tactics valid, specific lemmas)
- Guidance Value: 8/10 (highly actionable)
Total: 34/40

Backward Analysis (26/40):
- Structural Clarity: 7/10 (clear but brief description)
- Transition Accuracy: 7/10 (accurate but basic)
- Reasoning Depth: 6/10 (lists steps, limited why)
- Extraction Value: 6/10 (basic insights)
Total: 26/40

**Example 3: Backward Stronger (Analysis Excellent)**

Forward Planning (22/40):
- Strategy Appropriateness: 6/10 (reasonable but not optimal)
- Step Coverage: 5/10 (missing some key phases)
- Technical Accuracy: 6/10 (mostly correct, some confusion)
- Guidance Value: 5/10 (somewhat vague)
Total: 22/40

Backward Analysis (32/40):
- Structural Clarity: 8/10 (excellent pattern description)
- Transition Accuracy: 8/10 (precise state transformations)
- Reasoning Depth: 8/10 (explains rationale well)
- Extraction Value: 8/10 (valuable reusable insights)
Total: 32/40
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Raw XML only. No markdown code blocks.

<forward_score>
Strategy_Appropriateness: X/10
Step_Coverage: X/10
Technical_Accuracy: X/10
Guidance_Value: X/10
Total: XX/40
Justification: [Brief explanation of Forward planning quality]
</forward_score>

<backward_score>
Structural_Clarity: X/10
Transition_Accuracy: X/10
Reasoning_Depth: X/10
Extraction_Value: X/10
Total: XX/40
Justification: [Brief explanation of Backward analysis quality]
</backward_score>

<priority_recommendation>
Priority: [Forward | Backward | Balanced]
Reason: [Based on which provides better guidance for skeleton generation]
Confidence: [High | Medium | Low]
</priority_recommendation>

<consistency_check>
Agreement_Level: [High | Medium | Low]
- High: Forward strategy matches Backward structure (both suggest same approach)
- Medium: Partially aligned (general direction same, details differ)
- Low: Contradictory (Forward suggests X, Backward shows Y was used)

Key_Conflicts: [List any significant disagreements between Forward and Backward, or "None"]
Resolution: [For each conflict: which source to trust and why]
</consistency_check>

Remember: You're comparing a PLAN (Forward) vs an ANALYSIS (Backward).
Both can be excellent or poor in their own ways. Score them fairly!"""

    _USER_TEMPLATE = """
╔══════════════════════════════════════════════════════════════════╗
║              FAIR QUALITY ASSESSMENT TASK                        ║
╚══════════════════════════════════════════════════════════════════╝

📋 THEOREM: {decl_name}

**Theorem Statement:**
```lean
{statement}
```

**Given Context (Variables and Hypotheses):**
```lean
{context}
```

**Proof Goal:**
```lean
⊢ {goal}
```

*Important: Extract complete type parameters and constraints from the context when generating the skeleton.*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟦 FORWARD PLANNING (Exploratory Approach)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Problem Type: {forward_type}

Strategy:
{forward_strategy}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟩 BACKWARD ANALYSIS (Retrospective Approach)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Proof Structure:
{backward_structure}

Key Transitions:
{backward_transitions}

Reasoning Chain:
{backward_reasoning}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚖️ YOUR TASK: OBJECTIVE EVALUATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Compare BOTH approaches using the SAME standards.
Award points based on actual content quality, not approach type.

CRITICAL CHECKS:
✓ Does Backward provide a compilable skeleton? → High Feasibility
✓ Does Forward identify specific tactics/lemmas? → High Specificity  
✓ Are key proof steps covered? → High Completeness
✓ Is the reasoning mathematically sound? → High Accuracy

BEGIN FAIR ASSESSMENT NOW.
"""

    @cached_property
    def system_prompt(self) -> str:
        return self._SYSTEM_PROMPT.strip()

    def render_user_message(self, data: Dict[str, Any]) -> str:
        # 提取context和goal
        state = data.get('state', '')
        context = data.get('context', '')
        goal = data.get('goal', '')
        
        # 如果没有分离字段，从state解析
        if not context or not goal:
            if '⊢' in state:
                parts = state.split('⊢', 1)
                context = parts[0].strip()
                goal = parts[1].strip()
            else:
                context = state or "N/A"
                goal = "N/A"
        
        return self._USER_TEMPLATE.format(
            decl_name=data.get('decl_name', 'unknown'),
            statement=data.get('statement', ''),
            context=context,
            goal=goal,
            forward_type=data.get('forward_type', 'Unknown'),
            forward_strategy=data.get('forward_strategy', ''),
            backward_structure=data.get('backward_structure', ''),
            backward_transitions=data.get('backward_transitions', ''),
            backward_reasoning=data.get('backward_reasoning', '')
        )

    @cached_property
    def stop_tokens(self) -> List[str]:
        return ["```", "<user>"]

    def validate_response(self, raw_text: str) -> bool:
        required = ["<forward_score>", "<backward_score>", "<priority_recommendation>"]
        # consistency_check 是可选的，不强制要求
        return all(tag in raw_text for tag in required)


class StepByStepReasonerV2(BasePromptTemplate):
    """
    逐步推理生成器：基于评分结果生成详细的 step-by-step 思考过程

    改进重点：
    - 每一步必须有明确的【子目标】定义
    - 每一步必须有【代码提示】说明用什么 tactic
    - 输出结构化 XML，便于骨架生成器精确映射
    """

    _SYSTEM_PROMPT = """Role: Mathematical Reasoning Synthesizer.

Task: Generate a **structured step-by-step reasoning chain** for proving a theorem.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 CRITICAL: SUBGOAL-ORIENTED OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Each step MUST define a clear **subgoal** that can map to code.
The skeleton generator will create ONE code block per step.

**REQUIRED FIELDS for each step:**
1. <subgoal>: What this step proves/achieves (specific, not vague)
2. <tactics>: Lean 4 tactics to use (concrete names)
3. <rationale>: Why this step is needed
4. <code_hint>: Actual Lean code or `sorry` with clear TODO

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 OUTPUT FORMAT (Strict XML)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<step_by_step_reasoning>

<step number="1">
<subgoal>Understand the goal and choose proof strategy</subgoal>
<tactics>none (analysis phase)</tactics>
<rationale>Before coding, we need to identify the proof pattern</rationale>
<code_hint>-- Analysis: [describe the pattern]</code_hint>
</step>

<step number="2">
<subgoal>[Specific intermediate goal, e.g., "Apply distributive law to LHS"]</subgoal>
<tactics>[e.g., rw, simp, apply, exact]</tactics>
<rationale>[Why this transformation helps]</rationale>
<code_hint>[Actual code like `rw [lemma_name]` OR `sorry` with TODO]</code_hint>
</step>

... (continue for each logical step)

</step_by_step_reasoning>

<key_insights>
- [Insight 1: Critical observation about the proof]
- [Insight 2: Key lemma or technique used]
- [Insight 3: Pattern that can be reused]
</key_insights>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **One subgoal per step**: Don't combine multiple goals
2. **Concrete tactics**: Use actual Lean 4 tactic names, not vague descriptions
3. **Code hints matter**: They will be directly used in skeleton generation
4. **No empty steps**: Every step must have actionable content
5. **Sequential flow**: Each step should naturally follow from the previous

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 EXAMPLES (Different Difficulty Levels)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────────────────────┐
│ EXAMPLE 1: Simple Theorem (1-2 steps)                          │
└─────────────────────────────────────────────────────────────────┘

For theorem: ∀ n : ℕ, n + 0 = n

<step_by_step_reasoning>

<step number="1">
<subgoal>Apply right-identity of addition</subgoal>
<tactics>simp</tactics>
<rationale>This is a basic arithmetic property</rationale>
<code_hint>simp</code_hint>
</step>

</step_by_step_reasoning>

<key_insights>
- Direct application of standard lemma
</key_insights>

┌─────────────────────────────────────────────────────────────────┐
│ EXAMPLE 2: Medium Theorem (3-5 steps, with have)               │
└─────────────────────────────────────────────────────────────────┘

For theorem: (A ∩ B) ∪ (A ∩ C) = A ∩ (B ∪ C)

<step_by_step_reasoning>

<step number="1">
<subgoal>Apply set extensionality</subgoal>
<tactics>ext x</tactics>
<rationale>Prove equality by showing both sets have same elements</rationale>
<code_hint>ext x</code_hint>
</step>

<step number="2">
<subgoal>Split into two directions</subgoal>
<tactics>constructor</tactics>
<rationale>Prove ⊆ and ⊇ separately</rationale>
<code_hint>constructor</code_hint>
</step>

<step number="3">
<subgoal>Forward direction: x ∈ LHS implies x ∈ RHS</subgoal>
<tactics>intro, cases, tauto</tactics>
<rationale>Case split on union membership and derive intersection</rationale>
<code_hint>have fwd : (x ∈ A ∩ B ∨ x ∈ A ∩ C) → x ∈ A ∩ (B ∪ C) := by
  intro h
  cases h with
  | inl hab => exact ⟨hab.1, Or.inl hab.2⟩
  | inr hac => exact ⟨hac.1, Or.inr hac.2⟩
exact fwd</code_hint>
</step>

<step number="4">
<subgoal>Backward direction: x ∈ RHS implies x ∈ LHS</subgoal>
<tactics>intro, cases, tauto</tactics>
<rationale>Split on B ∪ C and construct union membership</rationale>
<code_hint>have bwd : x ∈ A ∩ (B ∪ C) → (x ∈ A ∩ B ∨ x ∈ A ∩ C) := by
  intro ⟨ha, hbc⟩
  cases hbc with
  | inl hb => exact Or.inl ⟨ha, hb⟩
  | inr hc => exact Or.inr ⟨ha, hc⟩
exact bwd</code_hint>
</step>

</step_by_step_reasoning>

<key_insights>
- Set equality via extensionality
- Bidirectional proof using constructor
- Use `have` to name each direction explicitly
- Pattern matching simplifies case analysis
</key_insights>

┌─────────────────────────────────────────────────────────────────┐
│ EXAMPLE 3: Complex Theorem (6+ steps, structured with have)    │
└─────────────────────────────────────────────────────────────────┘

For theorem: ∀ {α} (as bs : List α), (as ++ bs).reverse = bs.reverse ++ as.reverse

<step_by_step_reasoning>

<step number="1">
<subgoal>Set up structural induction on list 'as'</subgoal>
<tactics>induction as with | nil => ? | cons a as ih => ?</tactics>
<rationale>List equality involving recursion requires induction on the recursive structure</rationale>
<code_hint>induction as with
| nil => ?
| cons a as ih => ?</code_hint>
</step>

<step number="2">
<subgoal>Base case: prove for empty list</subgoal>
<tactics>simp</tactics>
<rationale>For nil, ([] ++ bs).reverse = bs.reverse = bs.reverse ++ []</rationale>
<code_hint>simp</code_hint>
</step>

<step number="3">
<subgoal>Inductive step: establish key equality</subgoal>
<tactics>simp, rw [ih]</tactics>
<rationale>Unfold definitions and apply inductive hypothesis</rationale>
<code_hint>have step_unfold : ((a :: as) ++ bs).reverse = (as ++ bs).reverse ++ [a] := by
  simp [List.reverse_cons, List.reverse_append]</code_hint>
</step>

<step number="4">
<subgoal>Apply inductive hypothesis to transform</subgoal>
<tactics>rw [ih]</tactics>
<rationale>Replace (as ++ bs).reverse using IH</rationale>
<code_hint>have step_ih : (as ++ bs).reverse = bs.reverse ++ as.reverse := ih</code_hint>
</step>

<step number="5">
<subgoal>Reorganize using associativity</subgoal>
<tactics>simp [List.append_assoc]</tactics>
<rationale>Group appends correctly: (bs.reverse ++ as.reverse) ++ [a]</rationale>
<code_hint>have step_assoc : (bs.reverse ++ as.reverse) ++ [a] = bs.reverse ++ (as.reverse ++ [a]) := by
  simp only [List.append_assoc]</code_hint>
</step>

<step number="6">
<subgoal>Recognize reverse of cons pattern</subgoal>
<tactics>simp [List.reverse_cons]</tactics>
<rationale>as.reverse ++ [a] equals (a :: as).reverse by definition</rationale>
<code_hint>calc ((a :: as) ++ bs).reverse
    = (as ++ bs).reverse ++ [a] := step_unfold
  _ = (bs.reverse ++ as.reverse) ++ [a] := by rw [step_ih]
  _ = bs.reverse ++ (as.reverse ++ [a]) := step_assoc
  _ = bs.reverse ++ (a :: as).reverse := by simp [List.reverse_cons]</code_hint>
</step>

</step_by_step_reasoning>

<key_insights>
- Structural induction is essential for recursive data structures
- Use `have` to name each transformation step explicitly
- Inductive hypothesis (IH) is a key intermediate result
- calc mode combines multiple `have` statements into proof chain
- Associativity and definition unfolding are common sub-steps
</key_insights>
"""

    _USER_TEMPLATE = """
**Theorem:** {decl_name}
```lean
{statement}
```

**Given Context (Variables and Hypotheses):**
```lean
{context}
```

**Proof Goal:**
```lean
⊢ {goal}
```

**Evaluation Results:**
- Priority: {priority} (Confidence: {confidence})
- Forward Score: {forward_score}/40
- Backward Score: {backward_score}/40

**Forward Analysis** (Weight: {forward_weight}%):
{forward_strategy}

**Backward Analysis** (Weight: {backward_weight}%):
Structure: {backward_structure}
Reasoning: {backward_reasoning}

Generate detailed step-by-step reasoning based on the theorem statement and proof goal.
Emphasize the higher-weighted source, but use complete type information from context.
"""

    @cached_property
    def system_prompt(self) -> str:
        return self._SYSTEM_PROMPT.strip()

    def render_user_message(self, data: Dict[str, Any]) -> str:
        # 提取context和goal
        state = data.get('state', '')
        context = data.get('context', '')
        goal = data.get('goal', '')
        
        # 如果没有分离字段，从state解析
        if not context or not goal:
            if '⊢' in state:
                parts = state.split('⊢', 1)
                context = parts[0].strip()
                goal = parts[1].strip()
            else:
                context = state or "N/A"
                goal = "N/A"
        
        return self._USER_TEMPLATE.format(
            decl_name=data.get('decl_name', 'unknown'),
            statement=data.get('statement', ''),
            context=context,
            goal=goal,
            priority=data.get('priority', 'balanced'),
            confidence=data.get('confidence', 'medium'),
            forward_score=data.get('forward_score', 20),
            backward_score=data.get('backward_score', 20),
            forward_weight=data.get('forward_weight', 50),
            backward_weight=data.get('backward_weight', 50),
            forward_strategy=data.get('forward_strategy', ''),
            backward_structure=data.get('backward_structure', ''),
            backward_reasoning=data.get('backward_reasoning', '')
        )

    @cached_property
    def stop_tokens(self) -> List[str]:
        return ["```", "<user>"]

    def validate_response(self, raw_text: str) -> bool:
        return "<step_by_step_reasoning>" in raw_text


class SkeletonGeneratorV2(BasePromptTemplate):
    """
    教学导向的骨架生成器：提供框架，而非答案

    核心改进：
    - 严格按照 step_by_step_reasoning 的步骤生成代码
    - 每个 sorry 必须对应一个明确的推理步骤
    - 禁止连续 sorry（每个 sorry 前必须有注释或代码）
    """

    _SYSTEM_PROMPT = """Role: Pedagogical Lean 4 Proof Skeleton Designer.

Mission: Create **instructional proof skeletons** that map DIRECTLY to reasoning steps.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️ STRUCTURED PROOF WITH `have` STATEMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**WHY USE `have`:**
- Each subgoal gets explicit type signature (better guidance)
- Can reference previous steps by name (structured reasoning)
- Clearer pedagogical structure than flat sorry sequence
- More aligned with mathematical proof writing

✅ PREFERRED - Use `have` for multi-step proofs:
```lean
theorem example (x y z : α) : P x y z := by
  -- Step 1: Establish intermediate result A
  have step1 : A x := by
    -- tactics or sorry
  
  -- Step 2: Derive B using step1
  have step2 : B y := by
    -- can use step1 here
    -- tactics or sorry
  
  -- Step 3: Combine to prove goal
  -- use step1 and step2
  sorry
```

❌ AVOID - Flat sorry sequence without structure:
```lean
theorem example : P := by
  sorry
  sorry
  sorry
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 WHEN TO USE `have` vs DIRECT TACTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Use `have` when:**
- Step produces intermediate lemma/result
- Later steps depend on this result
- Subgoal has clear mathematical meaning
- Example: `have h1 : x ≤ y := by ...`

**Use direct tactics when:**
- Single transformation step (e.g., `rw`, `simp`)
- Immediate goal simplification
- No intermediate result to name
- Example: `rw [add_comm]`, `ring`

**Hybrid approach (RECOMMENDED):**
```lean
theorem example : complex_goal := by
  -- Step 1: Direct simplification
  rw [some_lemma]
  
  -- Step 2: Intermediate result
  have h : intermediate_claim := by
    simp [lemma1, lemma2]
  
  -- Step 3: Use h to continue
  rw [h]
  ring
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 STEP-TO-CODE MAPPING RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You will receive step_by_step_reasoning in this format:

<step number="N">
<subgoal>...</subgoal>
<tactics>...</tactics>
<rationale>...</rationale>
<code_hint>...</code_hint>
</step>

For EACH step, generate ONE of these patterns:

**Pattern A: Direct Tactic (simple transformation)**
```lean
-- Step N: [subgoal]
[simple tactic like rw/simp/ring]
```

**Pattern B: Have Statement (intermediate result)**
```lean
-- Step N: [subgoal]
have stepN : [type of intermediate result] := by
  [tactics or sorry]
```

**Pattern C: Have with Sorry (guided gap)**
```lean
-- Step N: [subgoal]
-- Tactics: [suggested tactics]
-- Key insight: [mathematical rationale]
have stepN : [type] := by sorry
```

**Pattern D: Analysis Comment (strategic step)**
```lean
-- Step N: [subgoal]
-- Strategy: [rationale]
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 DIFFICULTY-BASED COMPLETION LEVEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Easy (Score ≥ 80%)**
- Convert ALL code_hints to actual code
- No sorry allowed
- Result: Complete working proof

**Medium (60% ≤ Score < 80%)**
- Convert first 40-50% of code_hints to actual code
- Remaining steps use guided sorry
- Each sorry has: subgoal + tactics + hint

**Hard (Score < 60%)**
- Convert first 20-30% of code_hints to actual code
- Most steps use guided sorry
- Rich pedagogical comments explaining WHY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<proof_skeleton>
```lean
-- [Auto-generated by Lean-RSR Consensus V2]
-- Difficulty: [Easy|Medium|Hard] | Score: XX/80
-- Steps: N total, M with sorry

theorem name ... := by
  -- Step 1: [subgoal from reasoning]
  [code or guided sorry]

  -- Step 2: [subgoal from reasoning]
  [code or guided sorry]

  ... (one block per reasoning step)
```
</proof_skeleton>

<skeleton_metadata>
- Difficulty: [Easy|Medium|Hard]
- Total Steps: X
- Completed Steps: Y (actual code)
- Sorry Steps: Z (guided gaps)
- Compilation Status: Expected ✓
</skeleton_metadata>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 SKELETON EXAMPLES (Different Difficulty Levels)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────────────────────┐
│ EXAMPLE 1: Easy Skeleton (Complete Proof)                      │
└─────────────────────────────────────────────────────────────────┘

Given reasoning:
<step number="1"><subgoal>Apply right-identity</subgoal><tactics>simp</tactics><code_hint>simp</code_hint></step>

**Generated skeleton:**
```lean
-- [Auto-generated by Lean-RSR Consensus V2]
-- Difficulty: Easy | Score: 72/80
-- Steps: 1 total, 0 with sorry

theorem add_zero (n : ℕ) : n + 0 = n := by
  simp
```

┌─────────────────────────────────────────────────────────────────┐
│ EXAMPLE 2: Medium Skeleton (Structured Roadmap)                │
└─────────────────────────────────────────────────────────────────┘

Given reasoning:
<step number="1"><subgoal>Set extensionality</subgoal><tactics>ext x</tactics><code_hint>ext x</code_hint></step>
<step number="2"><subgoal>Split bidirectional</subgoal><tactics>constructor</tactics><code_hint>constructor</code_hint></step>
<step number="3"><subgoal>Forward direction</subgoal><tactics>rintro, tauto</tactics><code_hint>rintro (⟨ha, hb⟩ | ⟨ha, hc⟩) <;> tauto</code_hint></step>
<step number="4"><subgoal>Backward direction</subgoal><tactics>rintro, tauto</tactics><code_hint>rintro ⟨ha, hb | hc⟩ <;> tauto</code_hint></step>

**Generated skeleton:**
```lean
-- [Auto-generated by Lean-RSR Consensus V2]
-- Difficulty: Medium | Score: 58/80
-- Steps: 4 total, 2 with sorry

theorem inter_union_distrib {α : Type*} (A B C : Set α) : 
    (A ∩ B) ∪ (A ∩ C) = A ∩ (B ∪ C) := by
  ext x
  constructor
  
  -- Step 3: Forward direction
  -- Tactics: rintro (⟨ha, hb⟩ | ⟨ha, hc⟩) <;> tauto
  -- Goal: (x ∈ A ∩ B ∨ x ∈ A ∩ C) → x ∈ A ∩ (B ∪ C)
  · sorry
  
  -- Step 4: Backward direction
  -- Tactics: rintro ⟨ha, hb | hc⟩ <;> tauto
  -- Goal: x ∈ A ∩ (B ∪ C) → (x ∈ A ∩ B ∨ x ∈ A ∩ C)
  · sorry
```

┌─────────────────────────────────────────────────────────────────┐
│ EXAMPLE 3: Hard Skeleton (Detailed Blueprint)                  │
└─────────────────────────────────────────────────────────────────┘

Given reasoning:
<step number="1"><subgoal>Strategy analysis</subgoal><tactics>analysis</tactics><code_hint>-- Algebraic rewrite</code_hint></step>
<step number="2"><subgoal>Distribute sup over inf</subgoal><tactics>rw</tactics><code_hint>rw [sup_inf_left]</code_hint></step>
<step number="3"><subgoal>Distribute inf over sup</subgoal><tactics>rw</tactics><code_hint>rw [inf_sup_left y]</code_hint></step>
<step number="4"><subgoal>AC normalization</subgoal><tactics>ac_refl</tactics><code_hint>ac_refl</code_hint></step>
<step number="5"><subgoal>Introduce sdiff</subgoal><tactics>rw</tactics><code_hint>rw [sup_inf_sdiff, sup_inf_sdiff]</code_hint></step>
<step number="6"><subgoal>Apply absorption</subgoal><tactics>rw, sorry</tactics><code_hint>-- TODO: sup_inf_self\nsorry</code_hint></step>
<step number="7"><subgoal>Final cancellation</subgoal><tactics>rw, sorry</tactics><code_hint>-- TODO: inf_inf_sdiff\nsorry</code_hint></step>

**Generated skeleton:**
```lean
-- [Auto-generated by Lean-RSR Consensus V2]
-- Difficulty: Hard | Score: 42/80
-- Steps: 7 total, 4 with sorry

theorem sdiff_sup {α : Type*} [GeneralizedBooleanAlgebra α] (x y z : α) : 
    (x \\ z) ⊔ (y \\ z) = (x ⊔ y) \\ z := by
  -- Step 1: Strategy - Use algebraic identities for lattices
  -- This proof transforms both sides to a common form via distribution
  
  -- Step 2-3: Initial distribution
  rw [sup_inf_left, inf_sup_left y]
  
  -- Step 4: Normalize using AC
  ac_refl
  
  -- Step 5: Express via symmetric difference
  -- Key insight: x \\ y = x ⊓ yᶜ in Boolean algebras
  have step5 : (x ⊔ y) \\ z = (x ⊔ y) ⊓ zᶜ := by
    rw [sup_inf_sdiff, sup_inf_sdiff]
    ac_refl
  
  -- Step 6: Apply absorption laws
  -- Tactics: rw [sup_inf_self, sup_inf_self, inf_idem]
  -- Goal: Eliminate patterns like x ⊔ (x ⊓ y) = x
  -- Why: Absorption law states x ⊔ (x ⊓ y) ≤ x ⊔ y = x
  have step6 : simplified_expr := by sorry
  
  -- Step 7: Final cancellation using sdiff properties
  -- Tactics: rw [inf_inf_sdiff, bot_inf_eq, bot_sup_eq, inf_bot_eq]
  -- Key: In Boolean algebras, x ⊓ (x \\ y) = x ⊓ (x ⊓ yᶜ) = x ⊓ yᶜ ⊓ x = ⊥
  -- This enables cancellation of symmetric difference terms
  calc (x \\ z) ⊔ (y \\ z) 
      = (x ⊓ zᶜ) ⊔ (y ⊓ zᶜ) := by rfl
    _ = ((x ⊔ y) ⊓ zᶜ) := step5
    _ = simplified_expr := step6
    _ = (x ⊔ y) \\ z := by sorry
```

**Key Differences:**
- Easy: Direct solution, no sorry
- Medium: Partial structure, minimal hints
- Hard: Full pedagogical commentary, rich guidance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ VALIDATION CHECKLIST (Self-check before output)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

□ Every reasoning step has a corresponding code block?
□ No two consecutive `sorry` without guidance between them?
□ Each sorry has: subgoal comment + tactics hint?
□ Step numbers in skeleton match reasoning step numbers?
□ Difficulty level matches completion percentage?

If any check fails, revise before outputting!"""

    _USER_TEMPLATE = """
╔══════════════════════════════════════════════════════════════════╗
║                    SKELETON GENERATION TASK                      ║
╚══════════════════════════════════════════════════════════════════╝

📋 THEOREM TO PROVE:
```lean
{statement}
```

📦 GIVEN CONTEXT (Variables and Hypotheses):
```lean
{context}
```

🎯 PROOF GOAL:
```lean
⊢ {goal}
```

**IMPORTANT:** Extract complete type information from the context:
  - Type parameters (e.g., `α : Type u_1`)
  - Type class instances (e.g., `_inst_1 : Group α`)
  - Explicit variables (e.g., `x y z : α`)
Reconstruct the FULL theorem declaration with all these in your skeleton.

📊 QUALITY ASSESSMENT:
├─ Combined Score: {combined_score}/80 ({difficulty_level})
├─ Forward Score:  {forward_score}/40
├─ Backward Score: {backward_score}/40
└─ Generation Mode: {generation_mode}

🧠 REASONING STEPS (Map each to code):
{step_by_step_reasoning}

╔══════════════════════════════════════════════════════════════════╗
║                      GENERATION DIRECTIVE                        ║
╚══════════════════════════════════════════════════════════════════╝

{directive}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 MANDATORY RULES (Will be validated)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **ONE-TO-ONE MAPPING**: Each <step> above → one code block in skeleton
2. **NO CONSECUTIVE SORRY**: Every sorry must have guidance comments before it
3. **STEP NUMBERS**: Use "-- Step N:" comments matching the reasoning steps
4. **GUIDED SORRY FORMAT**:
   ```lean
   -- Step N: [subgoal from reasoning]
   -- Tactics: [tactics from reasoning]
   -- Hint: [brief rationale]
   sorry
   ```

BEGIN GENERATION NOW.
"""

    @cached_property
    def system_prompt(self) -> str:
        return self._SYSTEM_PROMPT.strip()

    def _infer_difficulty(self, data: Dict[str, Any]) -> tuple[str, str, dict]:
        """
        多因子难度推断 - 体现 "Forward 高分更难得" 的原则

        核心理念：
        - Forward 是盲猜，高分说明题目本身有清晰的结构（容易推理）
        - Backward 看过答案，高分是预期的，不能单独决定难度
        - Forward 和 Backward 都高分 → 题目确实简单
        - Forward 低分但 Backward 高分 → 题目看似简单实则复杂

        改进点：
        1. Forward 权重提高到 0.6（盲猜准确更能反映真实难度）
        2. 一致性因子 - 两者接近时更相信评分
        3. 复杂度关键词检测
        4. 步骤数量信号

        返回: (difficulty_level, generation_mode, debug_info)
        """
        forward_score = data.get('forward_score', 20)
        backward_score = data.get('backward_score', 20)
        reasoning = data.get('step_by_step_reasoning', '')

        # 因子 1：评分（Forward 权重更高 - 盲猜准确更能反映真实难度）
        # 如果 Forward 能准确预测策略，说明题目结构清晰、难度适中
        # 如果 Forward 预测失败，说明题目有隐藏复杂性
        score_factor = forward_score * 0.6 + backward_score * 0.4

        # 因子 2：一致性（Forward 和 Backward 分数接近说明题目特征明显）
        score_diff = abs(forward_score - backward_score)
        consistency = 1.0 - score_diff / 40

        # 因子 3：Forward-Backward 差异分析
        # 如果 Backward >> Forward，说明题目"看似简单实则复杂"，应降低难度评估
        if backward_score > forward_score + 8:
            # Backward 明显高于 Forward，说明 Forward 预测失败，题目实际更难
            difficulty_penalty = (backward_score - forward_score - 8) / 32 * 0.15
        else:
            difficulty_penalty = 0

        # 因子 4：从 step_by_step_reasoning 提取复杂度信号
        step_count = reasoning.lower().count('step')

        # 因子 5：检测关键词判断复杂度
        hard_keywords = ['induction', 'cases', 'obtain', 'suffices', 'have', 'rcases', 'match', 'zorn']
        easy_keywords = ['rfl', 'simp', 'exact', 'trivial', 'ring', 'omega', 'decide', 'norm_num']

        hard_count = sum(1 for kw in hard_keywords if kw in reasoning.lower())
        easy_count = sum(1 for kw in easy_keywords if kw in reasoning.lower())

        complexity_signal = (hard_count - easy_count) / max(hard_count + easy_count, 1)

        # 综合计算
        # 基础分：40分满分，映射到 0-1
        base_score = score_factor / 40

        # 调整：一致性高时更相信评分，一致性低时偏保守
        adjusted_score = base_score * (0.7 + 0.3 * consistency)

        # 应用 Forward-Backward 差异惩罚
        adjusted_score -= difficulty_penalty

        # 复杂度信号调整
        adjusted_score -= complexity_signal * 0.15  # 多 hard_keywords 降低分数

        # 步骤数量调整
        if step_count <= 3:
            adjusted_score += step_count * 0.02  # 少步骤加分
        else:
            adjusted_score -= (step_count - 3) * 0.015  # 多步骤扣分

        # 确保在 [0, 1] 范围内
        adjusted_score = max(0.0, min(1.0, adjusted_score))

        # 调试信息
        debug_info = {
            'forward_score': forward_score,
            'backward_score': backward_score,
            'score_factor': round(score_factor, 2),
            'consistency': round(consistency, 2),
            'difficulty_penalty': round(difficulty_penalty, 3),
            'step_count': step_count,
            'hard_keywords': hard_count,
            'easy_keywords': easy_count,
            'complexity_signal': round(complexity_signal, 2),
            'adjusted_score': round(adjusted_score, 3)
        }

        # 最终判断（使用更保守的阈值）
        if adjusted_score >= 0.75:
            return "Easy (Inferred)", "Complete Elegant Proof", debug_info
        elif adjusted_score >= 0.50:
            return "Medium (Inferred)", "Structured Roadmap", debug_info
        else:
            return "Hard (Inferred)", "Detailed Blueprint", debug_info

    def render_user_message(self, data: Dict[str, Any]) -> str:
        # 计算综合分数
        forward_score = data.get('forward_score', 20)
        backward_score = data.get('backward_score', 20)
        combined_score = forward_score + backward_score

        # 优先使用原始难度标注
        original_difficulty = data.get('original_difficulty', None)

        if original_difficulty:
            # 有原始标注,直接使用(忽略评分结果)
            print(f"  Using original difficulty: {original_difficulty}")
            difficulty_map = {
                'easy': ('Easy (Original)', 'Complete Elegant Proof'),
                'medium': ('Medium (Original)', 'Structured Roadmap'),
                'hard': ('Hard (Original)', 'Detailed Blueprint')
            }
            difficulty_level, generation_mode = difficulty_map.get(
                original_difficulty.lower(),
                ('Medium (Original)', 'Structured Roadmap')
            )
        else:
            # 使用多因子难度推断
            difficulty_level, generation_mode, debug_info = self._infer_difficulty(data)
            print(f"  Multi-factor difficulty inference (Forward-priority):")
            print(f"    Forward: {debug_info['forward_score']}/40 | Backward: {debug_info['backward_score']}/40")
            print(f"    Score Factor: {debug_info['score_factor']}/40 (F*0.6 + B*0.4)")
            print(f"    Consistency: {debug_info['consistency']:.0%}")
            if debug_info['difficulty_penalty'] > 0:
                print(f"    Difficulty Penalty: -{debug_info['difficulty_penalty']:.1%} (B >> F)")
            print(f"    Complexity: {debug_info['hard_keywords']} hard / {debug_info['easy_keywords']} easy keywords")
            print(f"    Steps: {debug_info['step_count']}")
            print(f"    Adjusted Score: {debug_info['adjusted_score']:.1%} -> {difficulty_level}")
        
        # 根据难度生成指令
        if 'Easy' in difficulty_level:
            directive = """TARGET: Generate a COMPLETE, ELEGANT working proof
   - Style: Concise, direct, idiomatic Lean 4
   - Tactics: Use the most natural approach (exact, simp, rfl, ring, omega)
   - Sorry Count: 0 (this should be a complete solution)
   - Comments: Minimal or none - clean code is self-documenting
   - Rationale: Simple proofs demonstrate REASONING PATTERNS
              Models learn how to think from elegant solutions
   - CRITICAL: DO NOT add unnecessary complexity or pedagogical hints
              Just show the clean, correct solution!"""
        elif 'Medium' in difficulty_level:
            directive = """TARGET: Create a LEARNING ROADMAP with guided exploration
   - Structure: 3-5 major phases clearly separated
   - Sorry Count: 3-5 (one per logical subgoal)
   - Comments: Guiding questions + hints (NOT solutions)
     Format: Step N - Goal is [X]. Try [approach]. Why does this work?
   - Tactics: Show structure (induction, cases), but leave details empty
   - Teaching Value: Guide reasoning process, don't solve subproblems
   - Balance: 40% structure shown, 60% left for learner"""
        else:  # Hard
            directive = """TARGET: Craft an INSTRUCTIONAL BLUEPRINT for deep learning
   - Structure: Full proof architecture (6-10 steps)
   - Sorry Count: 5-10 (covering different proof aspects)
   - Comments: Rich pedagogical annotations -
     Explain the why behind each strategic choice,
     Provide multiple potential approaches,
     Point out common misconceptions,
     Ask probing questions to deepen understanding
   - Format: Multi-line instructional blocks before each sorry
   - Tactics: High-level only (have, suffices, obtain)
   - Teaching Value: Maximum - this is a learning experience
   - Balance: 30% structure shown, 70% active learning space
   - Meta-commentary: Explain proof strategy evolution"""
        
        # 提取context和goal
        state = data.get('state', '')
        context = data.get('context', '')
        goal = data.get('goal', '')
        
        # 如果没有分离字段，从state解析
        if not context or not goal:
            if '⊢' in state:
                parts = state.split('⊢', 1)
                context = parts[0].strip()
                goal = parts[1].strip()
            else:
                context = state or "N/A"
                goal = "N/A"
        
        return self._USER_TEMPLATE.format(
            statement=data.get('statement', ''),
            context=context,
            goal=goal,
            combined_score=combined_score,
            difficulty_level=difficulty_level,
            forward_score=forward_score,
            backward_score=backward_score,
            generation_mode=generation_mode,
            directive=directive.strip(),
            step_by_step_reasoning=data.get('step_by_step_reasoning', '')
        )

    @cached_property
    def stop_tokens(self) -> List[str]:
        return ["```", "<user>"]

    def validate_response(self, raw_text: str) -> bool:
        return "<proof_skeleton>" in raw_text
