# lean-proof

这是你的本地项目 `lean-proof` 的仓库。下面是快速说明：

内容概览：
- `src/`：项目源码
- `data/`：原始数据（在 `.gitignore` 中已排除，避免上传大数据）
- `models/`：模型权重（已排除）
- `requirements.txt`：Python 依赖

本地快速初始化与推送到 GitHub：
```powershell
cd D:\lean-proof
git init           # 若尚未初始化
git add .          # 添加文件（注意 .gitignore 会排除大文件）
git commit -m "Initial commit"
# 在 GitHub 上创建 repo，然后：
git remote add origin https://github.com/<your-username>/<repo>.git
git push -u origin main
```

注意事项：
- 请在推送前检查不应公开的敏感文件（API keys、秘钥、模型权重），必要时使用 Git LFS 或将其从历史中清除。
- 如果需要，我可以替你尝试用 `gh` CLI 在 GitHub 上创建仓库并推送（需要你已在本机登录 `gh`）。
# Lean-RSR: Math Thinker V2 (Pro)

**Lean-RSR** (Reverse Structured Reasoning) 是一个基于 **Qwen2.5-Math-7B** 的神经符号自动定理证明项目。本项目旨在通过**逆向结构化推理**和**专家迭代 (Expert Iteration)** 机制，提升大语言模型在 Lean 4 形式化数学证明中的能力。

## 🚀 核心理念

本项目模拟人类数学家“大胆假设，小心求证”的认知过程（System 2 思维），核心包含两个关键机制：

1.  **逆向结构化推理 (RSR)**：不仅仅学习“如何写代码”，更学习“如何思考”。通过 Teacher Model 逆向分析正确的证明代码，提取出**思维链 (Thought Chain)** 和 **证明骨架 (Proof Skeleton)**，让模型学会先规划后执行。
2.  **专家迭代 (Expert Iteration)**：
    *   **题海战术 (Massive Generation)**：模型对每道题生成大量候选解。
    *   **残酷筛选 (REPL Filter)**：利用 Lean 4 编译器进行验证，只保留 100% 正确的代码。
    *   **逆向注入 (Retrospective Injection)**：将通过编译的代码“回炉重造”，补全思维过程，形成高质量训练数据。
    *   **微调 (Fine-tuning)**：用这些“有思维、有骨架、有代码”的数据强化模型。

## 📂 项目结构

```
lean-proof/
├── configs/
│   └── config.yaml             # 全局配置文件 (模型、路径、超参数)
├── data/
│   ├── raw/                    # 原始数据
│   │   ├── leandojo_mathlib.jsonl  # Mathlib 提取的定理与证明
│   │   └── mathlib_10k_prompts.jsonl # 待生成的 10k 题目提示
│   ├── processed/              # 中间处理数据
│   │   └── mathlib_10k_solutions.jsonl # 模型生成的候选解
│   ├── synthetic/              # 合成训练数据
│   │   └── mathlib_consensus.jsonl # 经过 RSR 增强的高质量数据
│   └── temp_mathlib/           # Lean 4 编译沙盒 (Mathlib 副本)
├── lean_gym/                   # Lean 4 交互环境 (用于 REPL 验证)
│   ├── LeanGym/                # Lean 源码
│   ├── lakefile.toml           # Lake 构建配置
│   └── lean-toolchain          # Lean 版本锁定
├── models/                     # 模型权重目录
│   └── math-thinker-7b-pro/    # LoRA Adapter 权重文件
├── outputs/                    # 训练输出目录 (Checkpoints, Logs)
├── src/                        # 核心源代码
│   ├── common/                 # 通用组件
│   │   ├── prompts.py          # RSR 提示词模板 (Teacher/Student)
│   │   ├── types.py            # 数据类型定义
│   │   └── untils.py           # 辅助工具函数
│   ├── data_gen/               # 数据合成与处理
│   │   ├── pipeline.py         # 数据合成主流水线
│   │   ├── reasoners.py        # 推理器 (Backward/Forward/Consensus)
│   │   ├── run_synthesis.py    # 启动合成任务脚本
│   │   └── extract_mathlib_prompts.py # 从 Mathlib 提取题目
│   ├── inference/              # 推理与生成
│   │   ├── generate_solutions.py # 批量题目生成脚本
│   │   ├── evaluate.py         # 评估脚本
│   │   └── hammer.py           # 证明搜索工具
│   └── training/               # 模型训练
│       └── train.py            # SFT/LoRA 训练主程序
├── merge_lora.py               # LoRA 权重合并脚本
├── run_generation.ps1          # 快速启动生成的 PowerShell 脚本
├── requirements.txt            # Python 依赖列表
├── STRATEGY.md                 # 技术路线与战略文档
└── README.md                   # 项目说明文档
```

## 🛠️ 环境安装

1.  **Python 环境**:
    ```bash
    pip install -r requirements.txt
    ```
    *注意：Windows 用户安装 `bitsandbytes` 可能需要特定版本或预编译包。*

2.  **Lean 4 环境**:
    确保已安装 Lean 4 和 Lake，并初始化 `data/temp_mathlib` 目录以便进行编译验证。

## 🚦 使用指南

### 数据生成流水线 (Data Engine Pipeline)

本项目采用**三阶段数据生成流水线**（详见 `ARCHITECTURE.md`）：

#### 方式一：完整流水线（推荐）
```powershell
# 一键运行 Forward → Backward → Consensus
python run_full_pipeline.py --max-samples 50
```

#### 方式二：分阶段运行
```powershell
# Phase 1: 正向规划（探索策略）
python run_phase1_pipeline.py --max-samples 50

# Phase 2: 逆向分析（提取骨架）
python run_phase2_pipeline.py --max-samples 50

# Phase 3: 共识裁决（融合结果）
python run_phase3_pipeline.py --max-samples 50
```

**输出**:
- Phase 1: `data/step1_planning/mathlib_plans.jsonl`
- Phase 2: `data/step2_backward/backward_analysis.jsonl`
- Phase 3: `data/step3_consensus/final_training_data.jsonl` ⭐ 用于训练

---

### 1. 大规模生成 (Generation - 已弃用)
**注意**: 此脚本用于直接生成证明，现已被三阶段流水线取代。
```powershell
# 使用 PowerShell 脚本快速启动
.\run_generation.ps1

# 或者直接运行 Python 脚本
python src/inference/generate_solutions.py
```
*   配置：默认每题生成 32 个样本 (Temperature 0.7)。
*   输出：`data/processed/mathlib_10k_solutions.jsonl`

---

### 2. 训练 (Training)
使用合成的高质量数据对模型进行 LoRA 微调。
```bash
python src/training/train.py
```
*   配置：可在 `configs/config.yaml` 中调整 Batch Size, Learning Rate, LoRA Rank 等。
*   特性：支持 4-bit QLoRA，针对 RTX 4090 优化 (Flash Attention 2 / SDPA)。

### 3. 模型合并 (Merge)
将训练好的 LoRA 权重合并回 Base Model，以便部署或进行下一轮迭代。
```bash
python merge_lora.py
```

## 🗺️ 路线图 (Roadmap)

根据 `STRATEGY.md`，本项目的演进计划如下：

*   **Phase 1: 闭环验证与数据引擎** (当前阶段)
    *   [x] 实现基础的专家迭代 (ExIt) 流程。
    *   [ ] 深度集成 `lean_gym` 到数据生成脚本。
    *   [ ] 利用 Teacher Model 对 Mathlib 代码进行“去高尔夫化”。

*   **Phase 2: 检索增强与状态交互**
    *   [ ] 部署向量数据库，索引 Mathlib。
    *   [ ] 改造推理 Prompt，加入 RAG 检索信息。

*   **Phase 3: 搜索算法与共识升级**
    *   [ ] 实现基于树搜索的推理引擎 (R-GTS)。
    *   [ ] 将“共识裁决”训练为轻量级价值网络。

## 📊 技术指标

*   **Base Model**: Qwen/Qwen2.5-Math-7B-Instruct
*   **Training Strategy**: Rejection Sampling Fine-Tuning (RFT) + RSR
*   **Hardware**: Optimized for Consumer GPUs (RTX 3090/4090)

## 📝 引用与致谢

本项目深受 DeepSeek-Prover, AlphaProof 及 LeanDojo 等前沿工作的启发。


