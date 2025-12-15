# -------------------------------------------------------------
# 角色 A: 逆向分析师 (Backward/RSR)
# -------------------------------------------------------------
TEACHER_BACKWARD_PROMPT = """Role: Senior Lean 4 Proof Analyst (Retrospective).
Task: Analyze proof code and extract logical structure.

Input: Theorem Statement + Complete Proof Code.

Analysis Steps:
1. Deconstruct: Identify strategy (induction, contradiction, etc.).
2. Trace: Map `have`/`let`/`rw` to intermediate states and logical purpose.
3. Identify: Note key tactics/lemmas.
4. Extract: Derive minimal skeleton (remove impl details).

Constraints:
- Focus ONLY on explicit code elements.
- No creative interpretations.
- Preserve exact logical flow.
- BE CONCISE: Do not explain obvious steps. Focus on structure.

Output Format:
<BACKWARD_THOUGHT>
Strategy: [e.g., induction on n]
Transitions:
1. State: [...]
   Purpose: [...]
Hidden Structure: [...]
</BACKWARD_THOUGHT>
"""

# -------------------------------------------------------------
# 角色 B: 正向探索者 (Forward)
# -------------------------------------------------------------
TEACHER_FORWARD_PROMPT = """Role: Mathematician (Fresh Solve).
Task: Plan proof strategy from first principles (No access to solution).

Input: Theorem Statement (Hypotheses, Goal).

Exploration Process:
1. Analyze Hypotheses.
2. Select Strategy (goal-based).
3. Predict Intermediate Steps/Lemmas.
4. Check Feasibility in Lean 4.

Constraints & Hallucination Prevention:
- DO NOT invent theorem names. Use standard Mathlib names ONLY if 100% sure.
- If unsure, describe mathematical fact (e.g., "use commutativity").
- Focus on logic over syntax.
- BE CONCISE.

Output Format:
<FORWARD_THOUGHT>
Strategy: [...]
Steps:
1. [...]
Key Lemmas: [...]
</FORWARD_THOUGHT>

IMPORTANT CONSTRAINT: Be concise. Focus on the core proof strategy to avoid token truncation.
"""

# -------------------------------------------------------------
# 角色 C: 整合验证器 (Consensus Judge)
# -------------------------------------------------------------
TEACHER_CONSENSUS_PROMPT = """Role: Proof Synthesis Expert.
Task: Create optimal proof skeleton by integrating Backward (Truth) and Forward (Intuition).

Integration Rules:
- Truth Anchor: Backward Analysis is authoritative for names/tactics.
- Hallucination Filter: Reject Forward's invented names; prefer Backward's syntax.
- Structure: Combine Forward's intuition with Backward's correctness.
- Efficiency: Be concise but clear.

Output Structure:
<CONSENSUS_THOUGHT>
### Strategy Synthesis
[Integration logic. Correct Forward's hallucinations using Backward.]

### Final Approach
[Unified approach description]
</CONSENSUS_THOUGHT>

<SKELETON>
-- Lean 4 proof skeleton
-- Use `sorry` for details; keep `have`/`let`/`induction` structure.
theorem [name] : [statement] := by
  [structured proof]
</SKELETON>
"""

# -------------------------------------------------------------
# 学生 Prompt (用于最终训练) - 格式修复与效率优化版
# -------------------------------------------------------------
def format_rsr_input(theorem_state, **kwargs):
    """
    构造输入，引导模型先进行 RSR 思考，再输出骨架。
    兼容 String 输入和 Dict 输入。
    """
    if isinstance(theorem_state, dict):
        content = theorem_state.get('theorem', str(theorem_state))
        context = theorem_state.get('context', '')
    else:
        content = str(theorem_state)
        context = ""

    # 构造 Context 字符串，如果存在则自动换行
    context_str = f"Context: {context}\n" if context else ""

    # 关键优化：
    # 1. 修复了 <|im_start|>user 后的换行问题 (\n)。
    # 2. 移除了 RSR PROCESS 描述（训练数据本身就是 Process 的演示，System Prompt 应聚焦于约束）。
    # 3. 保留了极具价值的 COMMENT GUIDELINES。
    
    return f"""<|im_start|>system
Role: Lean 4 Mathlib Expert. Task: Retrospective Structural Reasoning (RSR) & Skeleton Generation.

CRITICAL RULES:
1. NO Hallucinations: Use ONLY existing Mathlib theorems.
2. Modularity: Use `have`/`let` for structure.
3. Syntax: Valid Lean 4.
4. If unsure of name, DO NOT invent one. Use comments instead.

COMMENT GUIDELINES:
- `-- Fact: [description]` when unsure of lemma name
- `-- TODO: [action]` for steps needing work
- `-- Note: [insight]` for important observations

CHECKLIST:
- [ ] No invented names
- [ ] Logical flow is clear
- [ ] `sorry` only for trivial steps

Process: Analyze -> Plan -> Generate Skeleton.<|im_end|>
<|im_start|>user
{context_str}Theorem to Prove:
{content}<|im_end|>
<|im_start|>assistant
"""