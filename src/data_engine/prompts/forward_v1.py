from typing import Dict, Any, List, TypedDict, cast, Optional
from functools import cached_property
import re
from .templates import BasePromptTemplate

# 定义输入类型，方便类型检查
class TheoremInput(TypedDict, total=False):
    decl_name: str
    statement: str
    imports: List[str]
    open_namespaces: List[str]

class ForwardPlanV1(BasePromptTemplate):
    """
    Phase 1 Forward Planning Prompt - V1 (Simplified Strategy Only).
    
    Changes:
    1. Removed <suggested_theorems> entirely to eliminate hallucination noise.
    2. Focus purely on Taxonomy (Problem Type) and Logical Strategy.
    3. Retained robust XML formatting and context extraction.
    """

    _SYSTEM_PROMPT = """You are a Lean 4 proof strategist analyzing theorem proving tasks.

Task: Develop a proof strategy based on the LEAN PROOF STATE (context + goal).
CRITICAL: The "Type Context" you see is Lean's actual proof state - it contains ALL the information you need!

**Understanding Lean Proof State Format:**
Format: `variables, hypotheses ⊢ goal`
Example: `m n : ℕ, h : m > 0 ⊢ m * n > 0`
  - Left of `⊢`: All available variables, type classes, and hypotheses
  - Right of `⊢`: The goal you need to prove
  - This is your COMPLETE context - use it!

**Anti-Hallucination Rules:**
1. The proof state tells you EXACTLY what's available - don't assume anything not shown
2. If you see `[Group G]`, you can use group axioms - say so explicitly
3. If you see `h : x < y`, you have this hypothesis - reference it in your strategy
4. DO NOT guess based on theorem name - the proof state is your ground truth
5. Your <problem_type> MUST match what's in the proof state, not the theorem name

**What you have:**
- Full Lean proof state (format: `context ⊢ goal`) - THIS IS EVERYTHING
- All variables with their types
- All hypotheses and assumptions  
- Type class instances available
- The exact goal to prove

**What you DON'T have:**
- The actual proof tactics sequence
- Specific lemmas used in the solution

**OUTPUT FORMAT (Raw XML only - NO markdown, NO code blocks):**

<problem_type>
Identify the mathematical domain (e.g., Algebra, Topology, Number Theory).
</problem_type>

<proof_strategy>
Provide step-by-step reasoning:
1. **Analyze Goal**: What needs to be proven? What hypotheses are given?
2. **Choose Approach**: Which proof technique fits best?
   - Induction (for recursive structures)
   - Direct proof (for equations/inequalities)
   - Contradiction (for existence/uniqueness)
   - Case analysis (for conditional statements)
3. **Outline Key Steps**: What are the main logical transitions?
4. **Assess Feasibility**: Is this approach formalizable in Lean 4?

Be specific about tactics and lemmas when possible.
</proof_strategy>
"""

    # One-Shot 示例：移除了定理推荐部分
    _ONE_SHOT_EXAMPLE = """
Example:

Input:
**Target Theorem Name:** List.length_append
**Theorem Statement:**
```lean
theorem length_append {α : Type u} (s t : List α) : length (s ++ t) = length s + length t
```

Output:
<problem_type>
Data Structures - List Theory
</problem_type>

<proof_strategy>
1. **Analyze Goal**: Prove length distributes over list concatenation.
   - Given: Two lists `s` and `t`
   - Goal: `length (s ++ t) = length s + length t`
   
2. **Choose Approach**: Structural induction on first list `s`.
   - Why: Both `length` and `++` are defined recursively on the first argument.
   
3. **Outline Key Steps**:
   - Base case (`s = []`): Use `length_nil` and `nil_append`
   - Inductive step (`s = x :: xs`): Apply `length_cons`, `cons_append`, and IH
   
4. **Assess Feasibility**: High - standard structural induction pattern in Lean 4.
</proof_strategy>
"""

    _USER_TEMPLATE = """
Input Theorem (Fresh Exploration - No Proof Given):

**Target Theorem Name:** {decl_name}

**Imports:**
{imports}

**Open Namespaces:**
{namespaces}

**Given Context (What You Have):**
```lean
{context}
```

**Proof Goal (What to Prove):**
```lean
⊢ {goal}
```

**Complete Lean Proof State:**
```lean
{type_context}
```
(Format: `context ⊢ goal` - this is the full state Lean sees)

**Theorem Declaration:**
```lean
{statement_block}
```

Analyze the context and goal above. The context shows all available variables, hypotheses, and type class instances.
The goal is what needs to be proven. Develop a strategy based on this information.
Output ONLY the two XML sections.
"""

    def __init__(self):
        pass  # 保留以便未来扩展

    @cached_property
    def system_prompt(self) -> str:
        return f"{self._SYSTEM_PROMPT.strip()}\n\n{self._ONE_SHOT_EXAMPLE.strip()}"

    def render_user_message(self, data: Dict[str, Any]) -> str:
        typed_data = cast(TheoremInput, data)
        
        imports_list = typed_data.get('imports', [])
        ns_list = typed_data.get('open_namespaces', [])
        theorem = typed_data.get('theorem', '')
        full_name = typed_data.get('full_name', 'Unknown')
        
        # **关键**: 使用分离的context和goal字段以提高清晰度
        state = typed_data.get('state', '')
        context = typed_data.get('context', '')
        goal = typed_data.get('goal', '')
        
        # 如果没有分离的context/goal，尝试从state解析
        if not context or not goal:
            if '⊢' in state:
                parts = state.split('⊢', 1)
                context = parts[0].strip()
                goal = parts[1].strip()
            else:
                context = state
                goal = "ERROR: Could not extract goal from state"
        
        # 如果完全没有state，这是严重问题
        if not state:
            state = "ERROR: No Lean proof state available!"
            if not context:
                context = "ERROR: No context available!"
            if not goal:
                goal = "ERROR: No goal available!"
        
        return self._USER_TEMPLATE.format(
            decl_name=full_name,
            statement_block=theorem,
            type_context=state,  # 完整的Lean上下文状态
            context=context,     # 分离的上下文（变量和假设）
            goal=goal,           # 分离的目标
            imports="\n".join(imports_list) or "None",
            namespaces=" ".join(ns_list) or "None"
        )
    
    @cached_property
    def stop_tokens(self) -> List[str]:
        # 移除可能导致提前截断的标签
        # 只保留明确的分隔符
        return ["```", "<user>", "\n\n---"]

    def validate_response(self, raw_text: str) -> bool:
        # 只验证这两个核心标签
        required = ["<problem_type>", "<proof_strategy>"]
        return all(t in raw_text for t in required)