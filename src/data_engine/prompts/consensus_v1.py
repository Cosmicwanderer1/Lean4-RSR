from typing import Dict, Any, List, TypedDict, Optional
from functools import cached_property
import re
from .templates import BasePromptTemplate

# ==========================================
# Consensus Judge Prompt - V1
# 融合正向探索和逆向分析的共识裁决
# ==========================================

class ConsensusJudgeV1(BasePromptTemplate):
    """
    Phase 3 Consensus Judge Prompt - V1.
    
    核心任务：
    1. 接收 Forward Planning 和 Backward Analysis 的结果
    2. 识别两者的共识部分（Intersection）
    3. 生成最终的高质量训练样本
    
    输出格式：
    - 融合后的证明策略
    - 验证过的证明骨架（compilable skeleton with sorry）
    - 完整的推理链（结合正向探索的直觉和逆向分析的逻辑）
    """

    _SYSTEM_PROMPT = """Role: Proof Strategy Consensus Judge.

Task: Synthesize insights from Forward Planning (exploratory) and Backward Analysis (retrospective) 
to produce a unified, high-quality proof strategy.

**Inputs:**
1. **Forward Analysis**: Problem type + exploratory strategy (from scratch)
2. **Backward Analysis**: Proof structure + skeleton + reasoning (from verified proof)

**Your Goal:**
- Identify **consensus** between forward intuition and backward logic
- Resolve conflicts (prefer Backward's concrete structure over Forward's speculation)
- Generate a **compilable skeleton** that captures the essence

**OUTPUT FORMAT RULES:**
1. Output **RAW XML** only.
2. **NO** Markdown code blocks.

XML Structure:

<consensus_strategy>
Unified proof approach combining both perspectives.
If conflict exists, explain which source is prioritized and why.
</consensus_strategy>

<verified_skeleton>
A **compilable** Lean 4 skeleton with:
- Theorem signature
- Structural tactics (e.g., induction, cases)
- `sorry` for proof details
- Comments marking key lemmas

CRITICAL: This must be syntactically valid Lean 4 code.
</verified_skeleton>

<unified_reasoning>
2-3 sentences explaining the proof logic.
Combine Forward's "why this approach" with Backward's "how it works".
</unified_reasoning>
"""

    _ONE_SHOT_EXAMPLE = """
**Example Input:**

Forward Planning Result:
- Problem Type: Number Theory - Commutativity
- Strategy: "Likely induction on one variable, use associativity/commutativity laws"

Backward Analysis Result:
- Proof Structure: "Induction on n with base (zero) and step (succ)"
- Key Transitions:
  1. ⊢ 0 + m = m + 0 → ⊢ m = m via Nat.zero_add
  2. ⊢ n + m = m + n → ⊢ (n+1) + m = m + (n+1) via rewrite
- Skeleton:
  ```lean
  theorem add_comm (n m : Nat) : n + m = m + n := by
    induction n with
    | zero => sorry
    | succ n ih => sorry
  ```

**Expected Output:**

<consensus_strategy>
Both Forward and Backward agree on induction on n. Forward correctly anticipated 
commutativity laws; Backward confirms the concrete structure. Consensus: Induction 
on n with base case using Nat.zero_add and inductive step using Nat.succ_add/add_succ.
</consensus_strategy>

<verified_skeleton>
theorem add_comm (n m : Nat) : n + m = m + n := by
  induction n with
  | zero =>
    -- Base: 0 + m = m + 0
    -- uses: Nat.zero_add
    sorry
  | succ n ih =>
    -- Step: (n+1) + m = m + (n+1)
    -- uses: Nat.succ_add, Nat.add_succ, IH
    sorry
</verified_skeleton>

<unified_reasoning>
Forward Planning identified the need for induction and commutativity reasoning. 
Backward Analysis confirmed the exact structure and pinpointed the critical lemmas 
(Nat.zero_add, Nat.succ_add). The unified skeleton preserves the high-level strategy 
while marking concrete proof obligations with sorry.
</unified_reasoning>
"""

    _USER_TEMPLATE = """
**Theorem:** {decl_name}

**Statement:**
```lean
{statement}
```

**Forward Planning:**
- Problem Type: {forward_type}
- Strategy: {forward_strategy}

**Backward Analysis:**
- Proof Structure: {backward_structure}
- Key Transitions: 
{backward_transitions}
- Skeleton:
```lean
{backward_skeleton}
```
- Reasoning: {backward_reasoning}

Please generate the consensus judgment (3 XML sections).
"""

    def __init__(self):
        pass

    @cached_property
    def system_prompt(self) -> str:
        return f"{self._SYSTEM_PROMPT.strip()}\n\n{self._ONE_SHOT_EXAMPLE.strip()}"

    def render_user_message(self, data: Dict[str, Any]) -> str:
        """
        渲染共识判断的用户消息
        
        Required fields:
        - decl_name: 定理名称
        - statement: 定理声明
        - forward_type: 正向分析的问题类型
        - forward_strategy: 正向分析的策略
        - backward_structure: 逆向分析的证明结构
        - backward_transitions: 逆向分析的关键转换
        - backward_skeleton: 逆向分析的骨架
        - backward_reasoning: 逆向分析的推理链
        """
        # 格式化 transitions
        transitions = data.get('backward_transitions', [])
        transitions_str = '\n'.join([f"  {i+1}. {t}" for i, t in enumerate(transitions)])
        if not transitions_str:
            transitions_str = "  (No explicit transitions)"
        
        return self._USER_TEMPLATE.format(
            decl_name=data.get('decl_name', 'unknown'),
            statement=data.get('statement', ''),
            forward_type=data.get('forward_type', 'Unknown'),
            forward_strategy=data.get('forward_strategy', ''),
            backward_structure=data.get('backward_structure', ''),
            backward_transitions=transitions_str,
            backward_skeleton=data.get('backward_skeleton', ''),
            backward_reasoning=data.get('backward_reasoning', '')
        )

    @cached_property
    def stop_tokens(self) -> List[str]:
        return ["```", "<user>", "\n\n---"]

    def validate_response(self, raw_text: str) -> bool:
        required = [
            "<consensus_strategy>",
            "<verified_skeleton>",
            "<unified_reasoning>"
        ]
        return all(tag in raw_text for tag in required)
