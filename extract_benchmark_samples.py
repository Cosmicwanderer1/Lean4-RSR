"""
从 LeanDojo Benchmark 筛选 1000 个多样化样本
难度分布: 10% Easy, 70% Medium, 20% Hard
类型要求: 覆盖多个数学领域
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any

def estimate_difficulty(theorem_data: Dict[str, Any]) -> str:
    """
    根据证明复杂度估算难度
    - Easy: 证明步骤 <= 5
    - Medium: 证明步骤 6-15
    - Hard: 证明步骤 > 15
    """
    tactics = theorem_data.get('traced_tactics', [])
    num_tactics = len(tactics)
    
    if num_tactics <= 5:
        return 'easy'
    elif num_tactics <= 15:
        return 'medium'
    else:
        return 'hard'

def extract_math_domain(file_path: str) -> str:
    """
    从文件路径提取数学领域
    例如: src/analysis/... -> analysis
    """
    parts = file_path.split('/')
    if len(parts) >= 2 and parts[0] == 'src':
        return parts[1]  # analysis, algebra, topology, etc.
    return 'other'

def select_diverse_samples(
    data: List[Dict[str, Any]], 
    target_count: int = 1000,
    easy_ratio: float = 0.1,
    medium_ratio: float = 0.7,
    hard_ratio: float = 0.2
) -> List[Dict[str, Any]]:
    """
    选择多样化样本
    """
    # 按难度和领域分组
    grouped = defaultdict(lambda: defaultdict(list))
    
    print("Analyzing dataset...")
    for item in data:
        difficulty = estimate_difficulty(item)
        domain = extract_math_domain(item['file_path'])
        grouped[difficulty][domain].append(item)
    
    # 统计信息
    print("\n=== Dataset Statistics ===")
    for diff in ['easy', 'medium', 'hard']:
        total = sum(len(items) for items in grouped[diff].values())
        domains = list(grouped[diff].keys())
        print(f"{diff.capitalize()}: {total} samples across {len(domains)} domains")
        print(f"  Domains: {', '.join(sorted(domains)[:10])}{'...' if len(domains) > 10 else ''}")
    
    # 计算目标数量
    target_easy = int(target_count * easy_ratio)
    target_medium = int(target_count * medium_ratio)
    target_hard = target_count - target_easy - target_medium
    
    print(f"\n=== Target Distribution ===")
    print(f"Easy:   {target_easy} ({easy_ratio*100:.0f}%)")
    print(f"Medium: {target_medium} ({medium_ratio*100:.0f}%)")
    print(f"Hard:   {target_hard} ({hard_ratio*100:.0f}%)")
    
    # 从每个难度级别均匀抽取
    selected = []
    
    for difficulty, target in [('easy', target_easy), ('medium', target_medium), ('hard', target_hard)]:
        domains = list(grouped[difficulty].keys())
        if not domains:
            print(f"Warning: No {difficulty} samples found!")
            continue
        
        # 计算每个领域应该抽取多少样本
        samples_per_domain = max(1, target // len(domains))
        
        for domain in domains:
            available = grouped[difficulty][domain]
            take = min(samples_per_domain, len(available))
            selected.extend(random.sample(available, take))
            
            if len(selected) >= target_easy + target_medium + target_hard:
                break
        
        # 如果还不够,从所有领域补充
        if len([s for s in selected if estimate_difficulty(s) == difficulty]) < target:
            remaining = target - len([s for s in selected if estimate_difficulty(s) == difficulty])
            all_samples = [item for domain_items in grouped[difficulty].values() for item in domain_items]
            additional = random.sample([s for s in all_samples if s not in selected], 
                                      min(remaining, len(all_samples)))
            selected.extend(additional)
    
    # 打乱顺序
    random.shuffle(selected)
    
    return selected[:target_count]

def parse_state_to_theorem(state: str, theorem_name: str) -> tuple[str, str]:
    """
    从 state_before 解析出完整的定理声明和类型上下文

    state 格式:
    ```
    α : Type u_1,
    x : α,
    h : P x
    ⊢ Q x
    ```

    Returns:
        (theorem_statement, type_context)
        theorem_statement: "theorem name {α : Type u_1} (x : α) (h : P x) : Q x :="
        type_context: 原始 state（用于 prompt）
    """
    if not state or '⊢' not in state:
        return f"theorem {theorem_name} :=", state

    # 分离变量声明和目标
    parts = state.split('⊢')
    var_section = parts[0].strip()
    goal = parts[-1].strip()

    # 解析变量声明
    # 格式: "name : Type," 每行一个
    implicit_vars = []  # 类型参数 {α : Type*}
    instance_vars = []  # 类型类实例 [inst : Class α]
    explicit_vars = []  # 显式参数 (x : α)

    for line in var_section.split('\n'):
        line = line.strip().rstrip(',')
        if not line or ':' not in line:
            continue

        # 解析 "name : type"
        colon_idx = line.find(':')
        var_name = line[:colon_idx].strip()
        var_type = line[colon_idx + 1:].strip()

        # 判断变量类型
        if var_type.startswith('Type') or var_type.startswith('Sort'):
            # 类型参数，使用隐式绑定
            implicit_vars.append(f"{{{var_name} : {var_type}}}")
        elif var_name.startswith('_inst') or var_name.startswith('inst'):
            # 类型类实例
            instance_vars.append(f"[{var_name} : {var_type}]")
        elif var_type.startswith('∀') or '→' in var_type:
            # 函数类型的假设，作为显式参数
            explicit_vars.append(f"({var_name} : {var_type})")
        else:
            # 普通变量或假设
            explicit_vars.append(f"({var_name} : {var_type})")

    # 构建完整定理声明
    params = ' '.join(implicit_vars + instance_vars + explicit_vars)
    if params:
        theorem_stmt = f"theorem {theorem_name} {params} : {goal} :="
    else:
        theorem_stmt = f"theorem {theorem_name} : {goal} :="

    return theorem_stmt, state


def convert_to_training_format(benchmark_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将 LeanDojo Benchmark 格式转换为训练格式

    关键改进：
    - 从 state_before 提取完整类型签名
    - 构建完整的定理声明（包括所有参数）
    - 保留原始 state 用于 prompt
    """
    converted = []

    for item in benchmark_data:
        # 提取定理声明 (从 traced_tactics 的第一个状态)
        tactics = item.get('traced_tactics', [])
        if not tactics:
            continue

        # 获取第一个 tactic 的初始状态
        first_state = tactics[0].get('state_before', '')

        # 重构完整证明
        proof_tactics = [t.get('tactic', '') for t in tactics if t.get('tactic')]
        if not proof_tactics:
            continue

        proof = 'by\n  ' + '\n  '.join(proof_tactics)

        # 估算难度
        difficulty = estimate_difficulty(item)

        # 提取领域
        domain = extract_math_domain(item['file_path'])

        # 提取定理名
        theorem_name = item.get('full_name', 'unknown')

        # 【关键改进】从 state 解析完整定理声明
        theorem_stmt, type_context = parse_state_to_theorem(first_state, theorem_name)

        converted.append({
            'theorem': theorem_stmt,  # ✅ 完整定理声明，包括类型签名
            'proof': proof,
            'difficulty': difficulty,
            'source': f"{domain}/{item['file_path'].split('/')[-1]}",
            'full_name': theorem_name,
            'file_path': item['file_path'],
            'state': type_context,  # ✅ 原始 state，用于 prompt 中的类型上下文
            'domain': domain  # ✅ 新增：数学领域标注
        })

    return converted

def main():
    print("="*80)
    print("LEANDOJO BENCHMARK SAMPLE EXTRACTOR")
    print("="*80)
    
    # 读取训练数据
    benchmark_path = Path('data/leandojo_benchmark/random/train.json')
    print(f"\nReading from: {benchmark_path}")
    
    with open(benchmark_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Total theorems in benchmark: {len(data)}")
    
    # 设置随机种子以保证可复现
    random.seed(42)
    
    # 选择多样化样本
    selected = select_diverse_samples(
        data, 
        target_count=1200,  # 增加目标数量以补偿转换失败的样本
        easy_ratio=0.1,
        medium_ratio=0.7,
        hard_ratio=0.2
    )
    
    print(f"\n=== Selected {len(selected)} samples ===")
    
    # 验证分布
    easy_count = sum(1 for s in selected if estimate_difficulty(s) == 'easy')
    medium_count = sum(1 for s in selected if estimate_difficulty(s) == 'medium')
    hard_count = sum(1 for s in selected if estimate_difficulty(s) == 'hard')
    
    print(f"Actual distribution:")
    print(f"  Easy:   {easy_count} ({easy_count/len(selected)*100:.1f}%)")
    print(f"  Medium: {medium_count} ({medium_count/len(selected)*100:.1f}%)")
    print(f"  Hard:   {hard_count} ({hard_count/len(selected)*100:.1f}%)")
    
    # 验证领域多样性
    domains = defaultdict(int)
    for s in selected:
        domain = extract_math_domain(s['file_path'])
        domains[domain] += 1
    
    print(f"\nDomain diversity: {len(domains)} different domains")
    print("Top domains:")
    for domain, count in sorted(domains.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {domain}: {count}")
    
    # 转换格式
    print("\nConverting to training format...")
    converted = convert_to_training_format(selected)
    
    # 保存结果
    output_path = Path('data/raw/leandojo_benchmark_1000.jsonl')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in converted:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"\n✅ Saved {len(converted)} samples to: {output_path}")
    print("\nNext steps:")
    print(f"  python run_full_pipeline_v2.py --input-file {output_path} --max-samples 1000")
    print("="*80)

if __name__ == '__main__':
    main()
