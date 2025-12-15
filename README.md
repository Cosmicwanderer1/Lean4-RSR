# Lean4-RSR / lean-proof

## 简要说明

这是你的本地项目 `lean-proof`（又名 `Lean4-RSR`），目标是通过逆向结构化推理（RSR）与专家迭代管线生成高质量训练数据并改进自动化证明能力。

主要目录概览：
- `src/`：项目源码
- `data/`：原始与处理后的数据（在 `.gitignore` 中已排除大数据）
- `models/`：模型/权重（建议使用 Git LFS 存储大型模型文件）
- `requirements.txt`：Python 依赖

## 快速开始

```powershell
cd D:\lean-proof
git init            # 若尚未初始化
git add .           # 添加文件（.gitignore 会排除大文件）
git commit -m "Initial commit"
# 在 GitHub 上创建远程仓库后：
git remote add origin git@github.com:Cosmicwanderer1/Lean4-RSR.git
git push -u origin main
```

## 重要说明
1.  **逆向结构化推理 (RSR)**：不仅仅学习“如何写代码”，更学习“如何思考”。通过 Teacher Model 逆向分析正确的证明代码，提取出**思维链 (Thought Chain)** 和 **证明骨架 (Proof Skeleton)**，让模型学会先规划后执行。
