"""
统一流水线 - 一条命令完成所有三个阶段

特性：
- Phase 1 & 2 并行执行（充分利用架构优势）
- Phase 3 自动启动（等待前两阶段完成）
- 多线程并发（每个阶段内部加速）
- 健壮的错误处理和进度显示
"""

import sys
import os
import subprocess
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# 修复 Windows 控制台 Unicode 输出问题
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def run_command(cmd: list, phase_name: str, env: dict = None) -> tuple[str, bool, str]:
    """运行单个命令"""
    print(f"\n{'='*70}")
    print(f"[START] {phase_name}")
    print(f"{'='*70}")

    try:
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        # 强制使用 UTF-8 编码，避免 Windows GBK 编码问题
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=exec_env,
            encoding='utf-8',
            errors='replace'  # 无法解码的字符用替代符号
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if stdout:
            print(stdout)
        if stderr and result.returncode != 0:
            print(stderr, file=sys.stderr)

        success = result.returncode == 0
        print(f"{'='*70}")
        print(f"[{'OK' if success else 'FAIL'}] {phase_name} - Exit Code: {result.returncode}")
        print(f"{'='*70}")

        return phase_name, success, stdout + stderr

    except Exception as e:
        print(f"\n[EXCEPTION] {phase_name}: {e}")
        return phase_name, False, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Unified Pipeline - Run all 3 phases with one command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with 10 samples
  python run_pipeline_unified.py --max-samples 10

  # Full run with 100 samples and 8 workers
  python run_pipeline_unified.py --max-samples 100 --max-workers 8

  # Custom Python path
  python run_pipeline_unified.py --python D:\\Anaconda3\\python.exe --max-samples 50
        """
    )
    
    parser.add_argument(
        '--max-samples',
        type=int,
        default=10,
        help='Maximum samples to process (default: 10)'
    )
    
    parser.add_argument(
        '--max-workers',
        type=int,
        default=6,
        help='Concurrent workers per phase (default: 6)'
    )
    
    parser.add_argument(
        '--input-file',
        type=str,
        default='data/raw/train_samples_1000.jsonl',
        help='Input data file'
    )
    
    parser.add_argument(
        '--python',
        type=str,
        default=sys.executable,
        help='Python executable path'
    )
    
    args = parser.parse_args()
    
    # 验证输入
    if not os.path.exists(args.input_file):
        print(f"[ERROR] Input file not found: {args.input_file}")
        sys.exit(1)
    
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("[ERROR] DEEPSEEK_API_KEY not set!")
        print("Please set it in PowerShell:")
        print('  $env:DEEPSEEK_API_KEY = "your-key-here"')
        sys.exit(1)
    
    # 显示配置
    print("="*80)
    print("UNIFIED PIPELINE - Parallel Optimized")
    print("="*80)
    print(f"Input File:     {args.input_file}")
    print(f"Max Samples:    {args.max_samples}")
    print(f"Workers/Phase:  {args.max_workers}")
    print(f"Python:         {args.python}")
    print(f"Execution:      Phase 1 & 2 parallel -> Phase 3 auto")
    print("="*80)
    
    env = {'DEEPSEEK_API_KEY': api_key}
    
    # ========== 并行执行 Phase 1 & 2 ==========
    print("\n[PARALLEL] Launching Phase 1 and Phase 2 simultaneously...\n")
    
    phase1_cmd = [
        args.python, "run_phase1_pipeline.py",
        "--input-file", args.input_file,
        "--max-samples", str(args.max_samples),
        "--max-workers", str(args.max_workers)
    ]
    
    phase2_cmd = [
        args.python, "run_phase2_pipeline.py",
        "--input", args.input_file,
        "--max-samples", str(args.max_samples),
        "--max-workers", str(args.max_workers)
    ]
    
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(run_command, phase1_cmd, "Phase 1: Forward Planning", env)
        future2 = executor.submit(run_command, phase2_cmd, "Phase 2: Backward Analysis", env)
        
        for future in as_completed([future1, future2]):
            phase_name, success, output = future.result()
            phase_id = "phase1" if "Phase 1" in phase_name else "phase2"
            results[phase_id] = success
    
    # 检查并行阶段结果
    phase1_ok = results.get('phase1', False)
    phase2_ok = results.get('phase2', False)
    
    print("\n" + "="*80)
    print("PARALLEL PHASE RESULTS")
    print("="*80)
    print(f"  Phase 1 (Forward):   {'[OK]' if phase1_ok else '[FAIL]'}")
    print(f"  Phase 2 (Backward):  {'[OK]' if phase2_ok else '[FAIL]'}")
    print("="*80)
    
    if not (phase1_ok and phase2_ok):
        print("\n[ERROR] One or both parallel phases failed - stopping pipeline")
        sys.exit(1)
    
    # 验证输出文件
    phase1_output = "data/step1_forward/forward_planning.jsonl"
    phase2_output = "data/step2_backward/backward_analysis.jsonl"
    
    for path in [phase1_output, phase2_output]:
        if not os.path.exists(path):
            print(f"[ERROR] Output file missing: {path}")
            sys.exit(1)
    
    # ========== 自动运行 Phase 3 ==========
    print("\n[AUTO-RUN] Both phases completed - starting Phase 3...\n")
    
    phase3_cmd = [
        args.python, "run_phase3_v2_pipeline.py",
        "--forward-file", phase1_output,
        "--backward-file", phase2_output,
        "--api-key", api_key,
        "--max-workers", str(args.max_workers),
        "--max-samples", str(args.max_samples)
    ]
    
    _, phase3_ok, _ = run_command(phase3_cmd, "Phase 3: Enhanced Consensus", env)
    
    # 最终汇总
    print("\n" + "="*80)
    print("PIPELINE COMPLETION SUMMARY")
    print("="*80)
    print(f"  Phase 1 (Forward Planning):     {'[OK]' if phase1_ok else '[FAIL]'}")
    print(f"  Phase 2 (Backward Analysis):    {'[OK]' if phase2_ok else '[FAIL]'}")
    print(f"  Phase 3 (Enhanced Consensus):   {'[OK]' if phase3_ok else '[FAIL]'}")
    print("="*80)
    
    if phase1_ok and phase2_ok and phase3_ok:
        print("\n[SUCCESS] All phases completed!")
        print("\nOutput Files:")
        print(f"  - {phase1_output}")
        print(f"  - {phase2_output}")
        print("  - data/step3_consensus_v2/enhanced_consensus.jsonl")
        print("\n" + "="*80)
        sys.exit(0)
    else:
        print("\n[FAILURE] Pipeline completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
