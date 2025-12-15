<<<<<<< HEAD
=======
<<<<<<< HEAD
# Lean4-RSR
=======
# Lean4-RSR / lean-proof

这是合并后的 `README.md`，保留了本地项目简介并整合了远端的历史说明。下面是简要可用版，若你希望保留更多细节我可以再展开。

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

- 推送前请确认不应公开的敏感文件或大文件（API keys、模型权重）。如需，我可以帮助配置 Git LFS 或清理 Git 历史。
- 项目包含 Lean 4 相关组件，若需要在本地运行请确保已安装 Lean 与 Lake。

---

若你同意这个合并结果，我将把它提交并继续将更改推送到远程。若需保留更详尽的远端 README 内容，请告知我想保留的部分，我会把它并入此文件。
1.  **逆向结构化推理 (RSR)**：不仅仅学习“如何写代码”，更学习“如何思考”。通过 Teacher Model 逆向分析正确的证明代码，提取出**思维链 (Thought Chain)** 和 **证明骨架 (Proof Skeleton)**，让模型学会先规划后执行。
