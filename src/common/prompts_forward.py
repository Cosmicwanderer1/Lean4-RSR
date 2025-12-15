from dataclasses import dataclass

@dataclass
class ForwardPrompts:
    
    SYSTEM = """
You are the "Forward Thinker" module of a Lean 4 automated theorem prover.
Your goal is to explore the **Assumption Space** of a given theorem.
You must NOT try to prove the theorem. You only identify available resources and immediate consequences.
"""

    TEMPLATE = """
### Theorem to Analyze:
```lean
{theorem_statement}
```

### Your Task:
Perform a "Forward Pass" analysis by filling in the following four sections.

**1. Hypotheses Analysis**:
List all variables and premises. For each premise, explain what it gives us mathematically.

**2. Definition Unfolding**:
Identify key mathematical concepts (e.g., `Nat.Prime`, `Continuous`, `Group`) in the hypotheses and write down their Lean 4 definitions or equivalence properties (e.g., `Nat.prime_def_lt`).

**3. Tool Retrieval (Mathlib Lemmas)**:
Suggest 3-5 specific Mathlib lemmas that are relevant to the *hypotheses* (not necessarily the goal). 
*Format*: `Lemma_Name: Description of when to use it`.

**4. Immediate Deductions**:
Write 2-3 `have` statements that are true by definition or by applying simple lemmas to the hypotheses.
*Format*: `have h_new : [type] := by [proof]` (keep proof simple, e.g., `apply`, `exact`, or `simp`).

### Output Format (JSON):
Please output strictly in JSON format as follows:
{{
  "hypotheses": ["..."],
  "definitions": ["..."],
  "lemmas": [
    {{"name": "...", "reason": "..."}}
  ],
  "deductions": [
    {{"statement": "...", "proof": "..."}}
  ]
}}
"""