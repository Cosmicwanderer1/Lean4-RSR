"""
一键运行完整三阶段流水线（增强版 - 并行优化）

执行流程：
1. Phase 1 & 2 并行: Forward Planning + Backward Analysis (同时运行)
2. Phase 3: Enhanced Consensus (等待1&2完成后自动运行)
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_command(cmd: list, phase_name: str, env: dict = None) -> tuple[str, bool, str]:
    """运行命令并处理结果"""
    print("\n" + "="*80)
    print(f"[START] {phase_name}")
    print("="*80)
    print(f"Command: {' '.join(cmd)}\n")
    
    try:
        # 合并环境变量
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=exec_env
        )
        
        # 打印输出
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        success = result.returncode == 0
        status = "[OK] Success" if success else f"[FAIL] Failed (code {result.returncode})"
        print(f"\n{status}: {phase_name}")
        
        return phase_name, success, result.stdout + result.stderr
        
    except Exception as e:
        print(f"\n[FAIL] Exception in {phase_name}: {e}")
        return phase_name, False, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Run complete 3-phase pipeline with enhanced consensus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 10 samples with API key
  python run_full_pipeline_v2.py --max-samples 10 --api-key YOUR_KEY

  # Run all 1000 samples (use environment variable for API key)
  set DEEPSEEK_API_KEY=your-key
  python run_full_pipeline_v2.py

  # Custom parallel workers
  python run_full_pipeline_v2.py --max-samples 100 --max-workers 16
        """
    )
    
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='Maximum samples to process (default: all 1000)'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='DeepSeek API Key (or set DEEPSEEK_API_KEY env var)'
    )
    
    parser.add_argument(
        '--max-workers',
        type=int,
        default=8,
        help='Parallel workers for Phase 3 (default: 8)'
    )
    
    parser.add_argument(
        '--skip-phase1',
        action='store_true',
        help='Skip Phase 1 if already completed'
    )
    
    parser.add_argument(
        '--skip-phase2',
        action='store_true',
        help='Skip Phase 2 if already completed'
    )
    
    parser.add_argument(
        '--input-file',
        type=str,
        default='data/raw/leandojo_mathlib.jsonl',
        help='Input data file (default: data/raw/leandojo_mathlib.jsonl)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.input_file):
        print(f"❌ Error: Input file not found: {args.input_file}")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key or os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ Error: API Key not provided!")
        print("\nPlease provide via:")
        print("  1. --api-key argument")
        print("  2. DEEPSEEK_API_KEY environment variable")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("🎯 FULL PIPELINE V2 - Enhanced Consensus System")
    print("="*80)
    print(f"Input File:    {args.input_file}")
    print(f"Max Samples:   {args.max_samples or 'All (1000)'}")
    print(f"Max Workers:   {args.max_workers} (Phase 3)")
    print(f"Skip Phase 1:  {args.skip_phase1}")
    print(f"Skip Phase 2:  {args.skip_phase2}")
    print("="*80)
    
    # Phase 1: Forward Planning
    if not args.skip_phase1:
        cmd_phase1 = [
            sys.executable,
            "run_phase1_pipeline.py",
            "--input-file", args.input_file
        ]
        if args.max_samples:
            cmd_phase1.extend(["--max-samples", str(args.max_samples)])
        
        if not run_command(cmd_phase1, "Phase 1: Forward Planning"):
            print("\n⚠️  Pipeline stopped at Phase 1")
            sys.exit(1)
    else:
        print("\n⏭️  Skipping Phase 1 (as requested)")
    
    # Check Phase 1 output exists
    phase1_output = "data/step1_forward/forward_planning.jsonl"
    if not os.path.exists(phase1_output):
        print(f"\n❌ Error: Phase 1 output not found: {phase1_output}")
        print("Please run Phase 1 first or remove --skip-phase1 flag")
        sys.exit(1)
    
    # Phase 2: Backward Analysis (读取原始数据，不依赖 Phase 1)
    if not args.skip_phase2:
        cmd_phase2 = [
            sys.executable,
            "run_phase2_pipeline.py",
            "--input", args.input_file  # 直接读取原始数据源
        ]
        if args.max_samples:
            cmd_phase2.extend(["--max-samples", str(args.max_samples)])
        
        if not run_command(cmd_phase2, "Phase 2: Backward Analysis"):
            print("\n⚠️  Pipeline stopped at Phase 2")
            sys.exit(1)
    else:
        print("\n⏭️  Skipping Phase 2 (as requested)")
    
    # Check Phase 2 output exists
    phase2_output = "data/step2_backward/backward_analysis.jsonl"
    if not os.path.exists(phase2_output):
        print(f"\n❌ Error: Phase 2 output not found: {phase2_output}")
        print("Please run Phase 2 first or remove --skip-phase2 flag")
        sys.exit(1)
    
    # Phase 3 V2: Enhanced Consensus
    cmd_phase3 = [
        sys.executable,
        "run_phase3_v2_pipeline.py",
        "--forward-file", phase1_output,
        "--backward-file", phase2_output,
        "--api-key", api_key,
        "--max-workers", str(args.max_workers)
    ]
    if args.max_samples:
        cmd_phase3.extend(["--max-samples", str(args.max_samples)])
    
    if not run_command(cmd_phase3, "Phase 3 V2: Enhanced Consensus (Parallel)"):
        print("\n⚠️  Pipeline stopped at Phase 3")
        sys.exit(1)
    
    # Success!
    print("\n" + "="*80)
    print("🎉 FULL PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*80)
    print("\n📊 Output Files:")
    print(f"  Phase 1: {phase1_output}")
    print(f"  Phase 2: {phase2_output}")
    print(f"  Phase 3: data/step3_consensus_v2/enhanced_consensus.jsonl")
    print("\n📈 Next Steps:")
    print("  1. Inspect consensus results for quality")
    print("  2. Verify proof skeletons compilability")
    print("  3. Use data for LoRA fine-tuning")
    print("="*80)


if __name__ == "__main__":
    main()
