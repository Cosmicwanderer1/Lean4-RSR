import sys
import os
import argparse

# 确保能找到 src 模块
sys.path.append(os.path.abspath("."))

from src.data_engine.data_gen.extract_mathlib_prompts import MathlibExtractor
from src.data_engine.pipelines.forward_pipeline import run_planning_pipeline

def main():
    # 添加命令行参数支持
    parser = argparse.ArgumentParser(description='LEAN-RSR Phase 1: Forward Planning Engine')
    parser.add_argument('--max-samples', type=int, default=10, 
                        help='Maximum number of theorems to process (default: 10)')
    parser.add_argument('--skip-extraction', action='store_true',
                        help='Skip theorem extraction step')
    parser.add_argument('--input-file', type=str, default='./data/raw/leandojo_mathlib.jsonl',
                        help='Input data file (default: ./data/raw/leandojo_mathlib.jsonl)')
    parser.add_argument('--max-workers', type=int, default=4,
                        help='Number of concurrent threads (default: 4)')
    args = parser.parse_args()
    
    print("==================================================")
    print("   LEAN-RSR PHASE 1: FORWARD PLANNING ENGINE      ")
    print("==================================================")
    print(f"Input file: {args.input_file}")
    print(f"Max samples: {args.max_samples}")

    # 1. 提取数据 (Extraction)
    print("\n[Step 1] Using input data...")
    raw_data_path = args.input_file
    # 1. 提取数据 (Extraction)
    print("\n[Step 1] Using input data...")
    raw_data_path = args.input_file
    
    # 检查文件是否存在
    if not os.path.exists(raw_data_path):
        print(f"❌ Error: Input file not found: {raw_data_path}")
        sys.exit(1)
    
    print(f"[OK] Found data at {raw_data_path}")

    # 2. 运行正向规划 (AI Planning)
    print("\n[Step 2] Running DeepSeek Forward Planning...")
    output_path = "./data/step1_forward/forward_planning.jsonl"
    
    # 这里调用之前写好的 pipeline
    run_planning_pipeline(
        input_file=raw_data_path, 
        output_file=output_path, 
        max_samples=args.max_samples,
        max_workers=args.max_workers
    )

    print("\n[OK] Phase 1 Pipeline Completed!")
    print(f"[OUTPUT] Check results in: {output_path}")

if __name__ == "__main__":
    main()