# Lean-RSR 数据引擎架构设计

## 📐 整体架构

本项目采用 **三阶段流水线** 设计，结合了 Lean-STAR 的逆向推理思想：

```
Raw Mathlib Data
      ↓
┌─────────────────────────────────────────────────┐
│  PHASE 1: FORWARD PLANNING (正向探索)           │
│  - 从定理出发，"盲目"探索证明策略                │
│  - 输出：问题类型 + 探索性策略                    │
└─────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────┐
│  PHASE 2: BACKWARD ANALYSIS (逆向分析)          │
│  - 从已验证的证明出发，逆向提取结构               │
│  - 输出：证明骨架 + 状态转换 + 推理链             │
└─────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────┐
│  PHASE 3: CONSENSUS JUDGMENT (共识裁决)         │
│  - 融合正向和逆向的结果                          │
│  - 输出：验证过的骨架 + 统一推理链                │
└─────────────────────────────────────────────────┘
      ↓
Final Training Data (高质量 SFT 数据)
```

## 📁 项目结构

```
src/data_engine/
├── prompts/                    # 提示词模板层
│   ├── templates.py            # 基础模板抽象类
│   ├── forward_v1.py           # Phase 1: 正向规划提示词
│   ├── backward_v1.py          # Phase 2: 逆向分析提示词
│   └── consensus_v1.py         # Phase 3: 共识裁决提示词
│
├── pipelines/                  # 流水线执行层
│   ├── forward_pipeline.py     # Phase 1 执行器
│   ├── backward_pipeline.py    # Phase 2 执行器
│   └── consensus_pipeline.py   # Phase 3 执行器
│
└── data_gen/                   # 数据生成工具
    └── extract_mathlib_prompts.py  # Mathlib 提取器

# 顶层启动脚本
run_phase1_pipeline.py          # 单独运行 Phase 1
run_phase2_pipeline.py          # 单独运行 Phase 2
run_phase3_pipeline.py          # 单独运行 Phase 3
run_full_pipeline.py            # 一键运行完整流程
```

## 🔄 核心组件详解

### 1. **Forward Planning (正向探索)**

**角色定位**: Mathematician (Fresh Solve)  
**输入**: 定理声明 + 导入上下文  
**输出**: 
- `problem_type`: 问题分类（如 Number Theory, Group Theory）
- `proof_strategy`: 探索性策略描述

**设计要点**:
- 模拟"不看答案"的真实解题过程
- 温度设置较高 (0.7)，鼓励创造性探索
- 关注"为什么这么做"而非"具体怎么做"

**文件**: 
- `src/data_engine/prompts/forward_v1.py`
- `src/data_engine/pipelines/forward_pipeline.py`

---

### 2. **Backward Analysis (逆向分析)** ⭐ 核心创新

**角色定位**: Senior Lean 4 Proof Analyst (Retrospective)  
**输入**: 定理声明 + **已验证的完整证明代码**  
**输出**:
- `proof_structure`: 证明模式（如 "Induction on n"）
- `key_transitions`: 关键状态转换列表
- `proof_skeleton`: 带 `sorry` 的可编译骨架
- `reasoning_chain`: 逻辑推理链

**设计要点** (受 Lean-STAR 启发):
- **状态追踪 (State Tracing)**: 识别证明中的中间目标状态
- **骨架提取 (Skeleton Extraction)**: 保留结构，去除实现细节
- **可编译性约束**: 骨架必须是合法的 Lean 4 代码
- 温度设置较低 (0.3)，确保精确分析

**文件**:
- `src/data_engine/prompts/backward_v1.py`
- `src/data_engine/pipelines/backward_pipeline.py`

---

### 3. **Consensus Judgment (共识裁决)**

**角色定位**: Proof Strategy Consensus Judge  
**输入**: Forward 结果 + Backward 结果  
**输出**:
- `consensus_strategy`: 融合后的策略
- `verified_skeleton`: 最终验证的骨架
- `unified_reasoning`: 统一的推理链

**设计要点**:
- 识别正向探索和逆向分析的**共识部分**
- 冲突解决：优先采用 Backward 的具体结构
- 温度最低 (0.2)，确保一致性

**文件**:
- `src/data_engine/prompts/consensus_v1.py`
- `src/data_engine/pipelines/consensus_pipeline.py`

---

## 🚀 使用方法

### 方式一：分阶段运行

```powershell
# Phase 1: 正向规划
python run_phase1_pipeline.py --max-samples 50

# Phase 2: 逆向分析
python run_phase2_pipeline.py --max-samples 50

# Phase 3: 共识裁决
python run_phase3_pipeline.py --max-samples 50
```

### 方式二：一键运行完整流程

```powershell
# 运行全部三个阶段
python run_full_pipeline.py --max-samples 50

# 跳过某些阶段（如果已有输出）
python run_full_pipeline.py --skip-phase1 --max-samples 50
```

---

## 📊 数据流示例

### Input (Raw Mathlib Data)
```json
{
  "id": "Nat.add_comm",
  "statement": "theorem add_comm (n m : Nat) : n + m = m + n",
  "golden_proof": "theorem add_comm (n m : Nat) : n + m = m + n := by\n  induction n with\n  | zero => simp [Nat.zero_add]\n  | succ n ih => rw [Nat.succ_add, ih, Nat.add_succ]",
  "imports": ["Mathlib.Data.Nat.Basic"]
}
```

### Phase 1 Output (Forward Planning)
```json
{
  "id": "Nat.add_comm",
  "problem_type": "Number Theory - Commutativity",
  "proof_strategy": "Likely induction on one variable, use commutativity laws"
}
```

### Phase 2 Output (Backward Analysis)
```json
{
  "id": "Nat.add_comm",
  "backward_analysis": {
    "proof_structure": "Induction on n with base (zero) and step (succ)",
    "key_transitions": [
      "⊢ 0 + m = m + 0 → ⊢ m = m via Nat.zero_add",
      "⊢ n + m = m + n → ⊢ (n+1) + m = m + (n+1) via rewrite"
    ],
    "proof_skeleton": "theorem add_comm (n m : Nat) : n + m = m + n := by\n  induction n with\n  | zero => sorry\n  | succ n ih => sorry"
  }
}
```

### Phase 3 Output (Final Training Data)
```json
{
  "id": "Nat.add_comm",
  "consensus": {
    "strategy": "Both agree on induction on n. Forward anticipated commutativity; Backward confirms structure.",
    "verified_skeleton": "theorem add_comm (n m : Nat) : n + m = m + n := by\n  induction n with\n  | zero =>\n    -- uses: Nat.zero_add\n    sorry\n  | succ n ih =>\n    -- uses: Nat.succ_add, Nat.add_succ, IH\n    sorry",
    "unified_reasoning": "Proof by induction. Base: 0+m=m via definition. Step: (n+1)+m=m+(n+1) via successor laws and IH."
  }
}
```

---

## 🎯 设计优势

### 相比传统 CoT (Chain-of-Thought)
- ✅ 提供**可验证的骨架**，而非纯文本推理
- ✅ 融合**探索直觉**和**逻辑结构**
- ✅ 输出可直接用于 Lean 4 编译验证

### 相比单纯的 Backward Analysis
- ✅ Forward 提供**问题分类**，帮助泛化
- ✅ 避免过拟合特定证明风格

### 受 Lean-STAR 启发的创新点
- 🌟 **状态转换追踪**：显式建模中间证明状态
- 🌟 **骨架生成**：提供结构化的证明轮廓
- 🌟 **双向验证**：正向+逆向互相印证

---

## 🔧 扩展性设计

所有提示词继承自 `BasePromptTemplate`，便于:
- 快速迭代新版本 (如 `forward_v2.py`)
- A/B 测试不同策略
- 插件式替换组件

所有流水线模块化，支持:
- 独立运行任意阶段
- 并行处理大规模数据
- 断点续传

---

## 📝 后续优化方向

1. **引入 REPL 验证**: 在 Phase 2 中用 Lean 编译器验证骨架
2. **强化学习闭环**: 将编译结果作为奖励信号
3. **检索增强 (RAG)**: 在 Forward 阶段加入 Mathlib 定理检索
4. **树搜索**: 将骨架的每个 `sorry` 转化为子问题，递归求解

---

**Author**: Lean-RSR Team  
**Inspired by**: Lean-STAR, DeepSeek-Prover, AlphaProof
