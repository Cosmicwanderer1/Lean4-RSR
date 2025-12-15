"""
并行运行 Phase 1 (Forward) 和 Phase 2 (Backward)
利用两阶段都读取原始数据的特性，实现真正的并行处理
"""

import subprocess
import sys
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def run_phase(phase_name: str, command: list) -> tuple[str, bool, str]:
    """运行单个 Phase"""
    print(f"\n{'='*60}")
    print(f"Starting {phase_name}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(command)}\n")
    
    # 继承当前环境变量（包括 DEEPSEEK_API_KEY）
    env = os.environ.copy()
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=env  # 传递环境变量
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
        print(f"\n❌ Exception in {phase_name}: {e}")
        return phase_name, False, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Run Phase 1 (Forward) and Phase 2 (Backward) in parallel"
    )
    parser.add_argument(
        '--input-file',
        type=str,
        default='data/raw/leandojo_benchmark_1000.jsonl',
        help='Input data file'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=10,
        help='Maximum samples to process (default: 10)'
    )
    parser.add_argument(
        '--python',
        type=str,
        default='python',
        help='Python executable path (default: python)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of concurrent threads per phase (default: 8)'
    )
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input_file):
        print(f"❌ Error: Input file not found: {args.input_file}")
        sys.exit(1)
    
    print("="*80)
    print("🎯 PARALLEL PIPELINE - Phase 1 & 2")
    print("="*80)
    print(f"Input File:    {args.input_file}")
    print(f"Max Samples:   {args.max_samples}")
    print(f"Workers/Phase: {args.workers} concurrent threads")
    print(f"Python:        {args.python}")
    print(f"Strategy:      2 phases parallel + {args.workers} threads per phase")
    print("="*80)
    
    # 准备命令
    phase1_cmd = [
        args.python,
        "run_phase1_pipeline.py",
        "--input-file", args.input_file,
        "--max-samples", str(args.max_samples),
        "--max-workers", str(args.workers)
    ]
    
    phase2_cmd = [
        args.python,
        "run_phase2_pipeline.py",
        "--input", args.input_file,
        "--max-samples", str(args.max_samples),
        "--max-workers", str(args.workers)
    ]
    
    # 并行执行
    print("\n🔄 Starting parallel execution...")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(run_phase, "Phase 1: Forward Planning", phase1_cmd): "phase1",
            executor.submit(run_phase, "Phase 2: Backward Analysis", phase2_cmd): "phase2"
        }
        
        results = {}
        for future in as_completed(futures):
            phase_id = futures[future]
            phase_name, success, output = future.result()
            results[phase_id] = success
    
    # 检查结果
    print("\n" + "="*80)
    print("📊 PARALLEL EXECUTION SUMMARY")
    print("="*80)
    
    phase1_ok = results.get('phase1', False)
    phase2_ok = results.get('phase2', False)
    
    print(f"Phase 1 (Forward):  {'[OK] Success' if phase1_ok else '[FAIL] Failed'}")
    print(f"Phase 2 (Backward): {'[OK] Success' if phase2_ok else '[FAIL] Failed'}")
    
    if phase1_ok and phase2_ok:
        print("\n[OK] Both phases completed successfully!")
        print("\n📁 Output files:")
        print("  - data/step1_forward/forward_planning.jsonl")
        print("  - data/step2_backward/backward_analysis.jsonl")
        print("\n💡 Next step: Run Phase 3 (Consensus)")
        print(f"  {args.python} run_phase3_v2_pipeline.py --max-samples {args.max_samples}")
        sys.exit(0)
    else:
        print("\n⚠️  Some phases failed. Check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
