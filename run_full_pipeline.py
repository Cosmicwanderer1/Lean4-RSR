import sys
import os
import argparse

sys.path.append(os.path.abspath("."))

from src.data_engine.pipelines.forward_pipeline import run_planning_pipeline
from src.data_engine.pipelines.backward_pipeline import run_backward_pipeline
from src.data_engine.pipelines.consensus_pipeline import run_consensus_pipeline

def main():
    parser = argparse.ArgumentParser(description='LEAN-RSR Complete Data Engine Pipeline')
    parser.add_argument('--max-samples', type=int, default=10,
                        help='Maximum samples for each phase')
    parser.add_argument('--skip-phase1', action='store_true',
                        help='Skip Phase 1 (Forward Planning)')
    parser.add_argument('--skip-phase2', action='store_true',
                        help='Skip Phase 2 (Backward Analysis)')
    parser.add_argument('--skip-phase3', action='store_true',
                        help='Skip Phase 3 (Consensus)')
    args = parser.parse_args()
    
    print("=" * 60)
    print("  LEAN-RSR: COMPLETE DATA ENGINE PIPELINE")
    print("  (Forward → Backward → Consensus)")
    print("=" * 60)
    print(f"📊 Max samples per phase: {args.max_samples}")
    print()
    
    # 定义文件路径
    raw_data = "./data/raw/mathlib_theorems.jsonl"
    forward_output = "./data/step1_planning/mathlib_plans.jsonl"
    backward_output = "./data/step2_backward/backward_analysis.jsonl"
    consensus_output = "./data/step3_consensus/final_training_data.jsonl"
    
    # Phase 1: Forward Planning
    if not args.skip_phase1:
        print("🔹 PHASE 1: FORWARD PLANNING")
        print("-" * 60)
        if not os.path.exists(raw_data):
            print(f"❌ Error: Raw data not found at {raw_data}")
            print("Please run: python src/data_engine/data_gen/extract_mathlib_prompts.py")
            sys.exit(1)
        
        run_planning_pipeline(
            input_file=raw_data,
            output_file=forward_output,
            max_samples=args.max_samples
        )
        print(f"✅ Phase 1 complete → {forward_output}\n")
    else:
        print("⏭️  Skipping Phase 1 (Forward Planning)\n")
    
    # Phase 2: Backward Analysis
    if not args.skip_phase2:
        print("🔹 PHASE 2: BACKWARD ANALYSIS")
        print("-" * 60)
        if not os.path.exists(raw_data):
            print(f"❌ Error: Raw data not found at {raw_data}")
            sys.exit(1)
        
        run_backward_pipeline(
            input_file=raw_data,
            output_file=backward_output,
            max_samples=args.max_samples
        )
        print(f"✅ Phase 2 complete → {backward_output}\n")
    else:
        print("⏭️  Skipping Phase 2 (Backward Analysis)\n")
    
    # Phase 3: Consensus
    if not args.skip_phase3:
        print("🔹 PHASE 3: CONSENSUS JUDGMENT")
        print("-" * 60)
        if not os.path.exists(forward_output):
            print(f"❌ Error: Forward output not found: {forward_output}")
            print("Please run Phase 1 first or use --skip-phase3")
            sys.exit(1)
        if not os.path.exists(backward_output):
            print(f"❌ Error: Backward output not found: {backward_output}")
            print("Please run Phase 2 first or use --skip-phase3")
            sys.exit(1)
        
        run_consensus_pipeline(
            forward_file=forward_output,
            backward_file=backward_output,
            output_file=consensus_output,
            max_samples=args.max_samples
        )
        print(f"✅ Phase 3 complete → {consensus_output}\n")
    else:
        print("⏭️  Skipping Phase 3 (Consensus)\n")
    
    print("=" * 60)
    print("🎉 PIPELINE COMPLETE!")
    print("=" * 60)
    print(f"📂 Final training data: {consensus_output}")
    print()
    print("🎯 Next Steps:")
    print("   1. Inspect the data: cat", consensus_output)
    print("   2. Train model: python src/training/train.py")
    print()

if __name__ == "__main__":
    main()
