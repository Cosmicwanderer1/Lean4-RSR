#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查所有prompt文件的字段一致性"""

import json
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 数据集字段（真实来源）
DATASET_FIELDS = {
    'commit', 'context', 'difficulty', 'end_line', 'file_path',
    'full_name', 'goal', 'imports', 'is_complete', 'num_tactics',
    'proof', 'start_line', 'state', 'theorem', 'url', 'used_theorems'
}

# Forward/Backward输出字段
FORWARD_OUTPUT_FIELDS = {
    'decl_name', 'statement', 'state', 'problem_type', 'strategy'
}

BACKWARD_OUTPUT_FIELDS = {
    'decl_name', 'statement', 'state', 'proof_structure',
    'key_transitions', 'reasoning_chain'
}

print("=" * 70)
print("字段一致性检查")
print("=" * 70)

# 读取真实数据样本
with open('data/raw/train_samples_1000.jsonl', 'r', encoding='utf-8') as f:
    sample = json.loads(f.readline())

print("\n1. 数据集实际字段:")
actual_fields = set(sample.keys())
print(f"   {sorted(actual_fields)}")

print("\n2. 关键字段检查:")
key_fields = {
    'full_name': '定理名称',
    'state': '完整proof state',
    'context': '上下文（⊢左边）',
    'goal': '目标（⊢右边）',
    'theorem': '定理声明',
    'proof': 'tactic序列',
    'imports': '导入模块',
    'difficulty': '难度标签'
}

for field, desc in key_fields.items():
    exists = field in sample
    status = "✓" if exists else "✗"
    value_preview = ""
    if exists:
        val = sample[field]
        if isinstance(val, str):
            value_preview = f" (示例: {val[:50]}...)" if len(val) > 50 else f" (值: {val})"
        elif isinstance(val, list):
            value_preview = f" (列表长度: {len(val)})"
    print(f"   {status} {field:15s} - {desc}{value_preview}")

print("\n3. Prompt模板使用的字段:")

# 检查backward_v1.py
from src.data_engine.prompts.backward_v1 import BackwardAnalysisV1
bp = BackwardAnalysisV1()

print("\n   Backward Prompt:")
test_msg = bp.render_user_message(sample)
if '{golden_proof}' in bp._USER_TEMPLATE:
    print("   ✗ 错误: 使用了 {golden_proof} 而不是 {proof}")
else:
    print("   ✓ 正确: 使用 {proof}")

# 检查forward_v1.py  
from src.data_engine.prompts.forward_v1 import ForwardPlanV1
fp = ForwardPlanV1()

print("\n   Forward Prompt:")
test_msg = fp.render_user_message(sample)
print("   ✓ 字段检查通过")

# 检查consensus
from src.data_engine.prompts.consensus_v2 import ScoringJudgeV2, StepByStepReasonerV2, SkeletonGeneratorV2

print("\n   Consensus Prompts:")
judge = ScoringJudgeV2()
test_data = {
    **sample,
    'decl_name': sample['full_name'],
    'statement': sample['theorem'],
    'forward_type': 'test',
    'forward_strategy': 'test',
    'backward_structure': 'test',
    'backward_transitions': 'test',
    'backward_reasoning': 'test'
}
try:
    msg = judge.render_user_message(test_data)
    print("   ✓ ScoringJudge 字段检查通过")
except Exception as e:
    print(f"   ✗ ScoringJudge 错误: {e}")

print("\n4. Pipeline字段映射检查:")
print("   数据集字段          → Pipeline字段")
print("   full_name          → decl_name (Forward/Backward输出)")
print("   theorem            → statement")
print("   proof              → (Backward输入)")
print("   state/context/goal → (所有组件)")

print("\n5. 关键发现:")
issues = []

if '{golden_proof}' in bp._USER_TEMPLATE:
    issues.append("✗ backward_v1.py使用{golden_proof}应改为{proof}")

if not all(f in sample for f in ['context', 'goal', 'difficulty']):
    issues.append("✗ 数据集缺少必要字段")

if issues:
    print("   发现问题:")
    for issue in issues:
        print(f"   {issue}")
else:
    print("   ✓ 所有字段一致性检查通过")

print("\n" + "=" * 70)
