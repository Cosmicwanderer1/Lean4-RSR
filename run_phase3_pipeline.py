import sys
import os
import argparse

sys.path.append(os.path.abspath("."))

from src.data_engine.pipelines.consensus_pipeline import run_consensus_pipeline

def main():
    parser = argparse.ArgumentParser(description='LEAN-RSR Phase 3: Consensus Engine')
    parser.add_argument('--forward', type=str, default='./data/step1_planning/mathlib_plans.jsonl',
                        help='Forward planning results from Phase 1')
    parser.add_argument('--backward', type=str, default='./data/step2_backward/backward_analysis.jsonl',
                        help='Backward analysis results from Phase 2')
    parser.add_argument('--output', type=str, default='./data/step3_consensus/final_training_data.jsonl',
                        help='Final consensus output')
    parser.add_argument('--max-samples', type=int, default=10,
                        help='Maximum samples to process')
    args = parser.parse_args()
    
    print("==================================================")
    print("   LEAN-RSR PHASE 3: CONSENSUS ENGINE            ")
    print("==================================================")
    print(f"📥 Forward input: {args.forward}")
    print(f"📥 Backward input: {args.backward}")
    print(f"📊 Max samples: {args.max_samples}")
    print(f"💾 Output: {args.output}")
    
    # 检查输入文件
    if not os.path.exists(args.forward):
        print(f"\n❌ Error: Forward file not found: {args.forward}")
        print("Please run Phase 1 first: python run_phase1_pipeline.py")
        sys.exit(1)
    
    if not os.path.exists(args.backward):
        print(f"\n❌ Error: Backward file not found: {args.backward}")
        print("Please run Phase 2 first: python run_phase2_pipeline.py")
        sys.exit(1)
    
    print("\n[Step 1] Running Consensus Judgment...")
    run_consensus_pipeline(
        forward_file=args.forward,
        backward_file=args.backward,
        output_file=args.output,
        max_samples=args.max_samples
    )
    
    print("\n✅ Phase 3 Pipeline Completed!")
    print(f"👉 Final training data: {args.output}")
    print("\n🎯 Next Steps:")
    print("   Use this data for fine-tuning with: python src/training/train.py")

if __name__ == "__main__":
    main()
