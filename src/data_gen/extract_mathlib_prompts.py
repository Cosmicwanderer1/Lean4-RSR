import os
import re
import json
import random
import argparse
from pathlib import Path
from tqdm import tqdm

def extract_theorems_from_file(file_path):
    """
    从单个 Lean 文件中提取定理声明，掩盖证明部分。
    这是一个基于正则的启发式提取，适用于大规模构建数据集。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

    # 正则表达式逻辑：
    # 1. 匹配 (protected) theorem 或 lemma
    # 2. 捕获名称
    # 3. 捕获类型签名，直到遇到 := 或 by 或 where
    # 注意：这无法处理跨越多行的极其复杂的类型定义，但对大多数 mathlib 定理有效。
    
    pattern = r'^\s*(?:protected\s+)?(?:theorem|lemma)\s+([\w\.]+)\s*(.*?)(?::=|by|where)'
    
    # 使用 MULTILINE 模式，但 . 不匹配换行符，我们需要手动处理多行签名的情况
    # 这里简化处理，假设声明头在几行内结束，或者我们只取匹配到的部分作为 Prompt
    
    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
    
    extracted = []
    for m in matches:
        name = m.group(1)
        signature = m.group(2).strip()
        
        # 构建 Prompt：保留声明，加上 := by 
        # 这样模型就会被迫开始写证明脚本
        prompt = f"theorem {name} {signature} := by"
        
        # 简单的过滤：太短的可能是噪音
        if len(signature) < 5:
            continue

        extracted.append({
            "task_id": name,
            "file_path": str(file_path),
            "prompt": prompt,
            "original_decl": m.group(0).strip()
        })
    
    return extracted

def main():
    parser = argparse.ArgumentParser(description="Extract theorems from Mathlib for generation tasks.")
    parser.add_argument("--mathlib_path", type=str, required=True, help="Path to the mathlib source folder (e.g., .lake/packages/mathlib/Mathlib)")
    parser.add_argument("--output_file", type=str, default="data/mathlib_10k_prompts.jsonl", help="Output JSONL file path")
    parser.add_argument("--num_samples", type=int, default=10000, help="Number of theorems to sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    
    args = parser.parse_args()
    
    random.seed(args.seed)
    
    all_theorems = []
    mathlib_path = Path(args.mathlib_path)
    
    print(f"Scanning {mathlib_path} for Lean files...")
    
    lean_files = list(mathlib_path.rglob("*.lean"))
    print(f"Found {len(lean_files)} Lean files.")
    
    # 遍历文件提取定理
    for file_path in tqdm(lean_files, desc="Extracting theorems"):
        theorems = extract_theorems_from_file(file_path)
        all_theorems.extend(theorems)
        
    print(f"Total theorems found: {len(all_theorems)}")
    
    # 随机采样
    if len(all_theorems) > args.num_samples:
        print(f"Sampling {args.num_samples} theorems...")
        selected_theorems = random.sample(all_theorems, args.num_samples)
    else:
        print(f"Warning: Only found {len(all_theorems)} theorems, using all of them.")
        selected_theorems = all_theorems
        
    # 确保输出目录存在
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    
    # 写入文件
    print(f"Writing to {args.output_file}...")
    with open(args.output_file, 'w', encoding='utf-8') as f:
        for item in selected_theorems:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print("Done!")

if __name__ == "__main__":
    main()