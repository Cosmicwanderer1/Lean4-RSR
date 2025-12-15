from typing import Dict, Any, List, TypedDict, cast, Optional
from functools import cached_property
import re
from .templates import BasePromptTemplate

# ==========================================
# Backward Analysis Prompt - V1
# 受 Lean-STAR 启发的逆向分析提示词
# ==========================================

class BackwardAnalysisV1(BasePromptTemplate):
    """
    Phase 2 Backward Analysis Prompt - V1 (Inspired by Lean-STAR).
    
    核心思想：
    1. 给定完整的证明代码，进行"事后诸葛亮"式的分析
    2. 提取证明的逻辑骨架 (Proof Skeleton)
    3. 识别关键的中间状态转换 (State Transitions)
    4. 生成结构化的思维链 (Structured Reasoning Chain)
    
    与 Forward 的区别：
    - Forward: 从定理出发，"盲目"探索可能的策略
    - Backward: 从已知正确的证明出发，逆向分析其结构
    """

    _SYSTEM_PROMPT = """Role: Senior Lean 4 Proof Analyst (Retrospective Analysis).

Task: Analyze a **complete, verified** Lean 4 proof and extract its logical REASONING WITH RICH DETAIL.

**CRITICAL: PROVIDE COMPREHENSIVE RATIONALE GENERATION (Lean-STAR Inspired)**
Your analysis will be compared against forward planning. To be competitive, you MUST:
1. Identify ALL key tactics and lemmas used
2. Explain the reasoning behind EACH major step in detail
3. Generate 6-10 sentences of step-by-step reasoning (not just 2-3)
4. Provide rich pedagogical explanations for WHY each step works

**Core Principles (Rationale Generation - NO Skeleton):**
1. **Decompose**: Break proof into ALL logical steps (tactics/lemmas).
2. **Trace State**: Identify ALL intermediate goal states and transformations.
3. **Explain Reasoning**: Focus on WHY tactics work, not HOW to write the skeleton.
4. **Pedagogical Value**: Teach the reasoning process, skeleton generation happens later.

**OUTPUT FORMAT RULES:**
1. Output **RAW XML** only.
2. **DO NOT** use Markdown code blocks.
3. **DO NOT** output JSON.

Strictly follow this XML structure:

<proof_structure>
Provide a DETAILED categorization:
- Main proof pattern (e.g., "Induction on n", "Case analysis", "Rewrite chain")
- Key techniques employed
- Overall strategy in 1-2 sentences
</proof_structure>

<key_transitions>
List ALL critical intermediate states (aim for 6-10 transitions).
Format: "N. [Current Goal] → [New Goal] via [specific tactic/lemma]"
Example: "1. ⊢ n + 0 = n → ⊢ n = n via Nat.add_zero and rfl"
Be SPECIFIC about which lemmas and tactics are used.
</key_transitions>

<reasoning_chain>
Explain the logical flow in 6-10 detailed sentences (Rationale Generation).
For EACH major step, provide pedagogical explanation:
- WHAT tactic/lemma is used and WHY it's chosen
- WHAT mathematical insight makes this step work
- HOW this step transforms the goal state
- WHAT prerequisites or lemmas are needed
- WHY alternative approaches wouldn't work as well

Focus on teaching the REASONING PROCESS, not writing code.
The skeleton will be generated later by a separate system.
Your job is to explain the THOUGHT PROCESS behind the proof.
</reasoning_chain>
"""

    _ONE_SHOT_EXAMPLE = """
**Example Input:**

Theorem:
```lean
theorem add_comm (n m : Nat) : n + m = m + n
```

Complete Proof:
```lean
theorem add_comm (n m : Nat) : n + m = m + n := by
  induction n with
  | zero => simp [Nat.zero_add]
  | succ n ih =>
    rw [Nat.succ_add, ih, Nat.add_succ]
```

**Expected Output:**

<proof_structure>
Induction on n with base case (zero) and inductive step (succ)
</proof_structure>

<key_transitions>
1. ⊢ 0 + m = m + 0 → ⊢ m = m via Nat.zero_add (base case)
2. ⊢ n + m = m + n (IH) → ⊢ succ n + m = m + succ n via Nat.succ_add
3. ⊢ m + succ n = succ (m + n) via Nat.add_succ
4. ⊢ succ (m + n) = succ (n + m) via IH (inductive hypothesis)
5. ⊢ succ (n + m) = (n+1) + m via definitional equality
</key_transitions>

<reasoning_chain>
The proof uses structural induction on n, which is the standard approach for proving properties of addition. In the base case, we need to show 0 + m = m + 0. By Lean's definition, 0 + m reduces to m, so we need m = m + 0. The lemma Nat.zero_add tells us that 0 + m = m, so by commutativity we get our goal. For the inductive step, we assume n + m = m + n (the inductive hypothesis) and prove (n+1) + m = m + (n+1). The key insight is to use the lemma Nat.succ_add, which states that (n+1) + m = n + (m+1), allowing us to rewrite the left side. Then we apply the inductive hypothesis to transform n + m to m + n. Finally, Nat.add_succ gives us m + (n+1) = (m + n) + 1, completing the chain of equalities. This proof strategy works because Lean's natural number addition is defined recursively on the first argument, making induction on the first argument natural.
</reasoning_chain>
"""

    _USER_TEMPLATE = """
**Context:**
Imports: {imports}
Open: {namespaces}

**Theorem Statement:**
```lean
{statement}
```

**Proof Context (Given Variables and Hypotheses):**
```lean
{context}
```

**Proof Goal:**
```lean
⊢ {goal}
```

**Complete Proof (Verified Correct):**
```lean
{proof}
```

Please perform retrospective analysis and output the 3 XML sections.
"""

    def __init__(self):
        self.decl_pattern = re.compile(
            r"^(?:@\[.*?\]\s*)?(?:protected\s+|private\s+|noncomputable\s+|scoped\s+)*(?:theorem|lemma)\s+([^\s\{]+)",
            re.MULTILINE
        )

    @cached_property
    def system_prompt(self) -> str:
        return f"{self._SYSTEM_PROMPT.strip()}\n\n{self._ONE_SHOT_EXAMPLE.strip()}"

    def render_user_message(self, data: Dict[str, Any]) -> str:
        """
        渲染逆向分析的用户消息。
        
        Required fields in data:
        - statement: 定理声明
        - proof: 正确的完整证明代码
        - imports (optional): 导入列表
        - open_namespaces (optional): 打开的命名空间
        - context (optional): 分离的上下文
        - goal (optional): 分离的目标
        - state (optional): 完整的proof state
        """
        imports = data.get('imports', [])
        namespaces = data.get('open_namespaces', [])
        statement = data.get('statement', '')
        proof = data.get('proof', '')
        
        # 获取分离的context和goal
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

        imports_str = ', '.join(imports) if imports else "None"
        namespaces_str = ', '.join(namespaces) if namespaces else "None"

        return self._USER_TEMPLATE.format(
            imports=imports_str,
            namespaces=namespaces_str,
            statement=statement,
            context=context,
            goal=goal,
            proof=proof
        )

    @cached_property
    def stop_tokens(self) -> List[str]:
        return ["```", "<user>", "\n\n---"]

    def validate_response(self, raw_text: str) -> bool:
        """验证响应是否包含所有必需的标签（仅思路和推理，无骨架）"""
        required = [
            "<proof_structure>",
            "<key_transitions>",
            "<reasoning_chain>"
        ]
        return all(tag in raw_text for tag in required)
