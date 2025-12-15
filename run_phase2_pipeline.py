import sys
import os
import argparse

# 确保能找到 src 模块
sys.path.append(os.path.abspath("."))

from src.data_engine.pipelines.backward_pipeline import run_backward_pipeline

def main():
    parser = argparse.ArgumentParser(description='LEAN-RSR Phase 2: Backward Analysis Engine')
    parser.add_argument('--input', type=str, default='./data/raw/leandojo_benchmark_1000.jsonl',
                        help='Input file with golden proofs from original dataset (default: leandojo_benchmark_1000.jsonl)')
    parser.add_argument('--output', type=str, default='./data/step2_backward/backward_analysis.jsonl',
                        help='Output file path')
    parser.add_argument('--max-samples', type=int, default=10,
                        help='Maximum number of proofs to analyze (default: 10)')
    parser.add_argument('--max-workers', type=int, default=4,
                        help='Number of concurrent threads (default: 4)')
    args = parser.parse_args()
    
    print("==================================================")
    print("   LEAN-RSR PHASE 2: BACKWARD ANALYSIS ENGINE    ")
    print("==================================================")
    print(f"Input: {args.input}")
    print(f"Max samples: {args.max_samples}")
    print(f"Output: {args.output}")
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input):
        print(f"\n❌ Error: Input file not found at {args.input}")
        print("Please run Phase 1 (Forward Planning) first.")
        sys.exit(1)
    
    print("\n[Step 1] Running Backward Analysis (Retrospective)...")
    run_backward_pipeline(
        input_file=args.input,
        output_file=args.output,
        max_samples=args.max_samples,
        max_workers=args.max_workers
    )
    
    print("\n[OK] Phase 2 Pipeline Completed!")
    print(f"[OUTPUT] Check results in: {args.output}")

if __name__ == "__main__":
    main()
