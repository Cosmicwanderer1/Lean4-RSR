"""
运行增强版共识流水线 (Phase 3 V2)

特性：
- 评分机制：对 Forward 和 Backward 分别评分
- 加权融合：根据评分动态调整权重
- 逐步推理：生成详细的 step-by-step 思考过程
- 骨架生成：基于推理过程生成可编译的骨架
"""

import sys
import os

# 修复 Windows 控制台 Unicode 输出问题
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data_engine.pipelines.consensus_pipeline_v2 import run_enhanced_consensus_pipeline


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Enhanced Consensus Pipeline V2 with Scoring Mechanism",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process 5 samples
  python run_phase3_v2_pipeline.py --max-samples 5

  # Full run with custom output
  python run_phase3_v2_pipeline.py --output-file data/custom_consensus.jsonl

  # Disable resume (start from scratch)
  python run_phase3_v2_pipeline.py --no-resume
        """
    )
    
    parser.add_argument(
        '--forward-file',
        type=str,
        default='data/step1_forward/forward_planning.jsonl',
        help='Path to Forward Planning results (default: data/step1_forward/forward_planning.jsonl)'
    )
    
    parser.add_argument(
        '--backward-file',
        type=str,
        default='data/step2_backward/backward_analysis.jsonl',
        help='Path to Backward Analysis results (default: data/step2_backward/backward_analysis.jsonl)'
    )
    
    parser.add_argument(
        '--output-file',
        type=str,
        default='data/step3_consensus_v2/enhanced_consensus.jsonl',
        help='Output file path (default: data/step3_consensus_v2/enhanced_consensus.jsonl)'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='DeepSeek API Key (or set DEEPSEEK_API_KEY environment variable)'
    )
    
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='Maximum number of samples to process (default: all)'
    )
    
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Disable resume from existing output'
    )
    
    parser.add_argument(
        '--max-workers',
        type=int,
        default=8,
        help='Number of parallel workers (default: 8, recommended: 4-16)'
    )
    
    args = parser.parse_args()
    
    # Validate input files
    if not os.path.exists(args.forward_file):
        print(f"Error: Forward file not found: {args.forward_file}")
        print("\nPlease run Phase 1 first:")
        print("  python run_phase1_pipeline.py --max-samples 10")
        sys.exit(1)
    
    if not os.path.exists(args.backward_file):
        print(f"Error: Backward file not found: {args.backward_file}")
        print("\nPlease run Phase 2 first:")
        print("  python run_phase2_pipeline.py --max-samples 10")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key or os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("Error: API Key not provided!")
        print("\nPlease provide API key via:")
        print("  1. --api-key argument")
        print("  2. DEEPSEEK_API_KEY environment variable")
        sys.exit(1)
    
    # Run pipeline
    print("\n" + "="*80)
    print("ENHANCED CONSENSUS PIPELINE V2")
    print("="*80)
    print(f"Forward File:  {args.forward_file}")
    print(f"Backward File: {args.backward_file}")
    print(f"Output File:   {args.output_file}")
    print(f"Max Samples:   {args.max_samples or 'All'}")
    print(f"Max Workers:   {args.max_workers}")
    print(f"Resume:        {not args.no_resume}")
    print("="*80 + "\n")
    
    try:
        run_enhanced_consensus_pipeline(
            forward_file=args.forward_file,
            backward_file=args.backward_file,
            output_file=args.output_file,
            api_key=api_key,
            max_samples=args.max_samples,
            resume=not args.no_resume,
            max_workers=args.max_workers
        )
        
        print("\n[OK] Pipeline completed successfully!")
        print(f"\nNext steps:")
        print(f"  1. Inspect results: {args.output_file}")
        print(f"  2. Extract final skeletons for training")
        print(f"  3. Verify skeleton compilability in Lean 4")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
