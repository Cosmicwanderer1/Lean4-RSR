import json
import os
from tqdm import tqdm
from src.data_gen.pipeline import ProofSynthesisPipeline

def main():
    # 路径配置
    raw_path = "./data/raw/leandojo_mathlib.jsonl"
    save_path = "./data/synthetic/mathlib_consensus.jsonl"
    
    # 初始化管道
    pipeline = ProofSynthesisPipeline()
    
    print(f"🚀 Starting OOP Parallel Synthesis (with Resume support)...")
    print(f"📖 Reading from: {raw_path}")
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # ---------------------------------------------------------
    # 1. 断点续传逻辑 (Resume Logic)
    # ---------------------------------------------------------
    processed_theorems = set()
    
    if os.path.exists(save_path):
        print(f"🔄 Found existing file at {save_path}, scanning for resume...")
        with open(save_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # 我们用 'input' (即定理内容) 作为唯一标识
                    if 'input' in data:
                        processed_theorems.add(data['input'])
                except json.JSONDecodeError:
                    continue # 跳过损坏的行
                    
        print(f"⏩ Found {len(processed_theorems)} already processed samples. They will be skipped.")

    # ---------------------------------------------------------
    # 2. 开始处理
    # ---------------------------------------------------------
    success_count = 0
    skipped_count = 0
    
    # 注意：这里使用 'a' (append) 模式，确保新数据追加到文件末尾，而不是覆盖
    with open(raw_path, 'r', encoding='utf-8') as f_in, \
         open(save_path, 'a', encoding='utf-8') as f_out:
        
        lines = f_in.readlines()
        
        for line in tqdm(lines, desc="Synthesizing"):
            try:
                item = json.loads(line)
            except:
                continue

            theorem = item.get("theorem")
            proof = item.get("proof")
            
            if not theorem or not proof:
                continue

            # Check Resume: 如果这个定理已经在结果文件里了，直接跳过
            if theorem in processed_theorems:
                skipped_count += 1
                continue

            # 调用管道处理
            result = pipeline.process_single_theorem(theorem, proof)
            
            if result:
                f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                f_out.flush() # 每次写入都刷新缓冲区，确保断电也不丢数据
                success_count += 1
    
    print(f"🎉 Synthesis complete!")
    print(f"   - Newly generated: {success_count}")
    print(f"   - Skipped (already done): {skipped_count}")

if __name__ == "__main__":
    main()