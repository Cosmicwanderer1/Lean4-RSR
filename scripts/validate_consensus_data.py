"""
验证共识数据集质量

检查项目：
1. 连续 sorry 问题
2. sorry 前是否有指导注释
3. 步骤映射是否完整
4. 骨架是否可能编译
"""

import json
import argparse
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import Counter


def validate_skeleton(skeleton: str) -> Tuple[bool, List[str]]:
    """
    验证骨架质量

    Returns:
        (is_valid, issues): 是否有效，以及问题列表
    """
    issues = []
    lines = skeleton.split('\n')

    # 检测连续 sorry（忽略注释和空行）
    consecutive_sorry_count = 0
    last_was_sorry = False
    last_sorry_line = -1
    sorry_positions = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 跳过空行和纯注释行
        if not stripped or stripped.startswith('--'):
            continue

        if stripped == 'sorry':
            sorry_positions.append(i + 1)
            if last_was_sorry:
                consecutive_sorry_count += 1
                if consecutive_sorry_count == 1:
                    issues.append(
                        f"Consecutive sorry at lines {last_sorry_line + 1} and {i + 1}"
                    )
            last_was_sorry = True
            last_sorry_line = i
        else:
            last_was_sorry = False

    # 检测 sorry 前是否有指导注释
    sorry_without_guidance = []
    for i, line in enumerate(lines):
        if line.strip() == 'sorry':
            has_guidance = False
            for j in range(max(0, i - 5), i):
                prev_line = lines[j].strip()
                if prev_line.startswith('--') and len(prev_line) > 10:
                    has_guidance = True
                    break
                elif prev_line and not prev_line.startswith('--') and prev_line != 'sorry':
                    has_guidance = True
                    break

            if not has_guidance:
                sorry_without_guidance.append(i + 1)

    if sorry_without_guidance:
        issues.append(f"Sorry without guidance at lines: {sorry_without_guidance}")

    # 检测 sorry 数量
    sorry_count = len(sorry_positions)
    if sorry_count > 10:
        issues.append(f"Too many sorry ({sorry_count})")

    # 检测是否有 theorem 声明
    has_theorem = any('theorem' in line.lower() or 'lemma' in line.lower()
                      for line in lines[:10])
    if not has_theorem:
        issues.append("No theorem/lemma declaration found")

    # 检测是否有 := by
    has_by = ':= by' in skeleton or ':=by' in skeleton
    if not has_by:
        issues.append("Missing ':= by' tactic mode marker")

    is_valid = len(issues) == 0
    return is_valid, issues


def validate_reasoning(reasoning: str) -> Tuple[bool, List[str]]:
    """验证推理步骤质量"""
    issues = []

    # 检查是否有结构化步骤
    step_count = len(re.findall(r'<step\s+number=', reasoning))

    if step_count == 0:
        # 旧格式：检查 Step N 模式
        step_count = len(re.findall(r'Step\s+\d+', reasoning, re.IGNORECASE))

    if step_count < 2:
        issues.append(f"Too few steps ({step_count})")

    # 检查是否有 subgoal 定义（新格式）
    subgoal_count = len(re.findall(r'<subgoal>', reasoning))
    if subgoal_count > 0 and subgoal_count < step_count:
        issues.append(f"Missing subgoals: {subgoal_count}/{step_count}")

    is_valid = len(issues) == 0
    return is_valid, issues


def validate_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    """验证单个样本"""
    full_name = sample.get('full_name', 'unknown')
    skeleton = sample.get('final_skeleton', '')
    reasoning = sample.get('step_by_step_reasoning', '')

    # 验证骨架
    skeleton_valid, skeleton_issues = validate_skeleton(skeleton)

    # 验证推理
    reasoning_valid, reasoning_issues = validate_reasoning(reasoning)

    return {
        'full_name': full_name,
        'skeleton_valid': skeleton_valid,
        'skeleton_issues': skeleton_issues,
        'reasoning_valid': reasoning_valid,
        'reasoning_issues': reasoning_issues,
        'overall_valid': skeleton_valid and reasoning_valid
    }


def main():
    parser = argparse.ArgumentParser(description='Validate consensus dataset')
    parser.add_argument(
        '--input',
        type=str,
        default='data/step3_consensus_v2/enhanced_consensus.jsonl',
        help='Input JSONL file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file for validation report (optional)'
    )
    parser.add_argument(
        '--filter-invalid',
        type=str,
        default=None,
        help='Output file for filtered valid samples (optional)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed issues for each sample'
    )

    args = parser.parse_args()

    # 读取数据
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return

    print(f"Loading data from: {input_path}")
    samples = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    print(f"Loaded {len(samples)} samples")
    print("=" * 60)

    # 验证每个样本
    results = []
    issue_counter = Counter()
    valid_samples = []
    invalid_samples = []

    for sample in samples:
        result = validate_sample(sample)
        results.append(result)

        if result['overall_valid']:
            valid_samples.append(sample)
        else:
            invalid_samples.append(sample)
            # 统计问题类型
            for issue in result['skeleton_issues'] + result['reasoning_issues']:
                # 提取问题类型
                issue_type = issue.split(' at ')[0].split(':')[0].strip()
                issue_counter[issue_type] += 1

        if args.verbose and not result['overall_valid']:
            print(f"\n[INVALID] {result['full_name']}")
            if result['skeleton_issues']:
                print(f"  Skeleton issues:")
                for issue in result['skeleton_issues']:
                    print(f"    - {issue}")
            if result['reasoning_issues']:
                print(f"  Reasoning issues:")
                for issue in result['reasoning_issues']:
                    print(f"    - {issue}")

    # 打印统计
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total samples: {len(samples)}")
    print(f"Valid samples: {len(valid_samples)} ({len(valid_samples)/len(samples)*100:.1f}%)")
    print(f"Invalid samples: {len(invalid_samples)} ({len(invalid_samples)/len(samples)*100:.1f}%)")

    if issue_counter:
        print("\nIssue breakdown:")
        for issue_type, count in issue_counter.most_common():
            print(f"  {issue_type}: {count}")

    # 保存验证报告
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            'total': len(samples),
            'valid': len(valid_samples),
            'invalid': len(invalid_samples),
            'issue_breakdown': dict(issue_counter),
            'invalid_samples': [
                {
                    'full_name': r['full_name'],
                    'skeleton_issues': r['skeleton_issues'],
                    'reasoning_issues': r['reasoning_issues']
                }
                for r in results if not r['overall_valid']
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\nValidation report saved to: {output_path}")

    # 保存过滤后的有效样本
    if args.filter_invalid:
        filter_path = Path(args.filter_invalid)
        filter_path.parent.mkdir(parents=True, exist_ok=True)

        with open(filter_path, 'w', encoding='utf-8') as f:
            for sample in valid_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')

        print(f"Filtered valid samples saved to: {filter_path}")
        print(f"  {len(valid_samples)} valid samples retained")
        print(f"  {len(invalid_samples)} invalid samples removed")


if __name__ == '__main__':
    main()
