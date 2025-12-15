"""
从LeanDojo Benchmark的train.json提取样本
优化版：完整提取state、proof、imports、open_namespaces等所有必要字段
"""

import json
from pathlib import Path
from typing import Dict, List, Set
from tqdm import tqdm
from collections import defaultdict

def load_corpus_imports(corpus_file: str) -> Dict[str, List[str]]:
    """
    从corpus.jsonl加载每个文件的imports信息
    
    Returns:
        file_path -> imports列表的映射
    """
    print(f"Loading imports from {corpus_file}...")
    file_imports = {}
    
    with open(corpus_file, 'r', encoding='utf-8') as f:
        for line in tqdm(f, desc="Loading corpus imports"):
            try:
                item = json.loads(line)
                file_path = item.get('path', '')
                imports = item.get('imports', [])
                if file_path:
                    file_imports[file_path] = imports
            except json.JSONDecodeError:
                continue
    
    print(f"Loaded imports for {len(file_imports)} files")
    return file_imports

def extract_used_theorems_from_tactics(traced_tactics: List[Dict]) -> List[Dict]:
    """
    从traced_tactics的annotated_tactic中提取证明过程中使用的定理/引理/定义
    
    Returns:
        使用的定理列表，每个包含: full_name, def_path, def_pos, module
    """
    used_theorems = []
    seen = set()  # 去重
    
    for tactic in traced_tactics:
        annotated = tactic.get('annotated_tactic', [])
        if isinstance(annotated, list) and len(annotated) > 1:
            # annotated_tactic格式: [tactic_text, [{'full_name': ..., 'def_path': ..., 'def_pos': ...}, ...]]
            deps_list = annotated[1]
            if isinstance(deps_list, list):
                for dep in deps_list:
                    if isinstance(dep, dict) and 'full_name' in dep:
                        full_name = dep['full_name']
                        if full_name not in seen:
                            seen.add(full_name)
                            
                            # 从def_path推断模块名
                            def_path = dep.get('def_path', '')
                            module = extract_module_from_path(def_path)
                            
                            used_theorems.append({
                                'full_name': full_name,
                                'def_path': def_path,
                                'def_pos': dep.get('def_pos', [0, 0]),
                                'module': module
                            })
    
    return used_theorems

def extract_module_from_path(def_path: str) -> str:
    """
    从定理定义路径推断所属模块
    例如: src/data/nat/basic.lean -> Data.Nat.Basic
    """
    if not def_path:
        return ''
    
    # 移除常见前缀
    path = def_path.replace('\\', '/')
    
    # 处理mathlib路径
    if 'src/' in path:
        parts = path.split('src/', 1)[1]
    elif '_target/deps/lean/library/' in path:
        parts = path.split('_target/deps/lean/library/', 1)[1]
        return f"Lean.{parts.replace('/', '.').replace('.lean', '')}"
    else:
        parts = path
    
    # 转换为模块名格式
    module = parts.replace('/', '.').replace('.lean', '')
    
    # 首字母大写
    module_parts = module.split('.')
    module = '.'.join(p.capitalize() for p in module_parts)
    
    return f"Mathlib.{module}"

def extract_open_namespaces_from_state(state: str) -> List[str]:
    """
    从state中提取可能的命名空间
    例如: 从 "nat.add" 可以推断 open Nat
    """
    # 这个比较难准确提取，因为state不包含open信息
    # 我们可以从类型和函数名推断常见的命名空间
    namespaces = set()
    
    # 常见的命名空间模式
    common_patterns = {
        'nat.': 'Nat',
        'int.': 'Int',
        'list.': 'List',
        'finset.': 'Finset',
        'set.': 'Set',
        'real.': 'Real',
        'complex.': 'Complex',
    }
    
    state_lower = state.lower()
    for pattern, namespace in common_patterns.items():
        if pattern in state_lower:
            namespaces.add(namespace)
    
    return sorted(list(namespaces))

def infer_difficulty(proof: str, num_tactics: int, used_theorems: List[Dict]) -> str:
    """
    基于多个特征推断证明难度
    
    Args:
        proof: tactic序列
        num_tactics: tactic数量
        used_theorems: 使用的定理列表
    
    Returns:
        'easy', 'medium', 'hard'
    """
    proof_lower = proof.lower()
    
    # 因子1: tactic数量
    if num_tactics <= 3:
        tactic_score = 0  # easy
    elif num_tactics <= 10:
        tactic_score = 1  # medium
    else:
        tactic_score = 2  # hard
    
    # 因子2: 复杂tactic关键词
    hard_keywords = [
        'induction', 'cases', 'obtain', 'rcases', 'match',
        'have', 'suffices', 'calc', 'conv', 'funext',
        'ext', 'split', 'constructor', 'refine', 'apply'
    ]
    easy_keywords = [
        'rfl', 'exact', 'trivial', 'simp', 'ring', 
        'omega', 'decide', 'norm_num', 'rw', 'rewrite'
    ]
    
    hard_count = sum(1 for kw in hard_keywords if kw in proof_lower)
    easy_count = sum(1 for kw in easy_keywords if kw in proof_lower)
    
    # 因子3: 使用的定理数量
    theorem_count = len(used_theorems)
    
    # 综合评分
    complexity_score = 0
    
    # tactic数量权重
    complexity_score += tactic_score * 3
    
    # 复杂关键词权重
    if hard_count > easy_count:
        complexity_score += min(hard_count - easy_count, 3)
    elif easy_count > hard_count:
        complexity_score -= min(easy_count - hard_count, 2)
    
    # 使用定理数量
    if theorem_count > 10:
        complexity_score += 2
    elif theorem_count > 5:
        complexity_score += 1
    
    # 最终判断
    if complexity_score <= 2:
        return 'easy'
    elif complexity_score <= 6:
        return 'medium'
    else:
        return 'hard'

def extract_from_traced_tactics(
    sample: Dict
) -> Dict:
    """
    从train.json的traced_tactics中提取完整训练数据
    
    Args:
        sample: train.json中的一个样本
    
    Returns:
        包含完整字段的字典
    """
    full_name = sample.get('full_name', '')
    file_path = sample.get('file_path', '')
    traced_tactics = sample.get('traced_tactics', [])
    
    if not traced_tactics:
        return None
    
    # 从第一个tactic获取初始state（证明的起点）
    first_tactic = traced_tactics[0]
    initial_state = first_tactic.get('state_before', '')
    
    # 从最后一个tactic验证是否完成
    last_tactic = traced_tactics[-1]
    final_state = last_tactic.get('state_after', '')
    
    # 提取所有tactic组成proof
    proof_tactics = [t.get('tactic', '') for t in traced_tactics]
    proof = '\n'.join(proof_tactics)
    
    # 从traced_tactics提取证明中使用的定理/引理
    used_theorems = extract_used_theorems_from_tactics(traced_tactics)
    
    # 提取使用的模块列表（去重）- 这就是实际需要的imports
    imports = sorted(list(set(t['module'] for t in used_theorems if t['module'])))
    
    # 解析initial_state
    if '⊢' in initial_state:
        parts = initial_state.split('⊢', 1)
        context = parts[0].strip()
        goal = parts[1].strip()
        state = initial_state
        theorem_statement = goal
    else:
        state = initial_state
        context = initial_state
        theorem_statement = initial_state
        goal = initial_state
    
    # 构造完整的theorem声明
    # 注意：我们从goal构造theorem，因为这是实际要证明的内容
    theorem = f'theorem {full_name} : {goal}'
    
    # 推断难度
    difficulty = infer_difficulty(proof, len(traced_tactics), used_theorems)
    
    return {
        'full_name': full_name,
        'state': state,  # 完整的Lean proof state (context ⊢ goal)
        'theorem': theorem,  # 完整的定理声明
        'proof': proof,  # tactic序列
        'imports': imports,  # 证明中实际使用的模块列表
        'used_theorems': used_theorems,  # 证明中使用的定理/引理（详细信息）
        'file_path': file_path,
        'url': sample.get('url', ''),
        'commit': sample.get('commit', ''),
        'start_line': sample.get('start', [0, 0])[0],
        'end_line': sample.get('end', [0, 0])[0],
        'num_tactics': len(traced_tactics),
        'is_complete': 'no goals' in final_state.lower(),
        'context': context,  # 上下文部分（⊢左边）
        'goal': goal,  # 目标部分（⊢右边）
        'difficulty': difficulty,  # 推断的难度: easy/medium/hard
    }

def extract_train_samples(
    train_json: str,
    output_file: str,
    num_samples: int = 1000,
    min_tactics: int = 1,
    max_tactics: int = 100,
    require_complete: bool = True,
    difficulty_distribution: Dict[str, float] = None
):
    """
    从train.json提取样本，支持按难度分布采样
    
    Args:
        train_json: random/train.json路径
        output_file: 输出JSONL文件
        num_samples: 提取样本数量
        min_tactics: 最少tactic数量
        max_tactics: 最多tactic数量（避免太复杂的证明）
        require_complete: 是否要求证明完整
        difficulty_distribution: 难度分布，例如 {'easy': 0.1, 'medium': 0.7, 'hard': 0.2}
    """
    # 默认难度分布（均匀）
    if difficulty_distribution is None:
        difficulty_distribution = {'easy': 0.33, 'medium': 0.34, 'hard': 0.33}
    # 加载train.json
    print(f"Loading train samples from {train_json}...")
    with open(train_json, 'r', encoding='utf-8') as f:
        train_data = json.load(f)
    
    print(f"Total train samples: {len(train_data)}")
    print(f"Extracting with filters:")
    print(f"  - Sample count: {num_samples}")
    print(f"  - Tactic range: [{min_tactics}, {max_tactics}]")
    print(f"  - Require complete: {require_complete}")
    print(f"  - Difficulty distribution: {difficulty_distribution}")
    
    # 第一阶段：提取所有符合条件的样本并分类
    print("\n阶段1: 提取并分类所有样本...")
    samples_by_difficulty = {'easy': [], 'medium': [], 'hard': []}
    stats = {
        'no_tactics': 0,
        'too_short': 0,
        'too_long': 0,
        'incomplete': 0,
        'extraction_failed': 0,
    }
    
    for sample in tqdm(train_data, desc="Processing all samples"):
        traced_tactics = sample.get('traced_tactics', [])
        
        if not traced_tactics:
            stats['no_tactics'] += 1
            continue
        
        num_tactics = len(traced_tactics)
        
        if num_tactics < min_tactics:
            stats['too_short'] += 1
            continue
        
        if num_tactics > max_tactics:
            stats['too_long'] += 1
            continue
        
        # 检查是否完整
        if require_complete:
            last_state = traced_tactics[-1].get('state_after', '')
            if 'no goals' not in last_state.lower():
                stats['incomplete'] += 1
                continue
        
        # 提取数据
        data = extract_from_traced_tactics(sample)
        if data:
            difficulty = data.get('difficulty', 'medium')
            samples_by_difficulty[difficulty].append(data)
        else:
            stats['extraction_failed'] += 1
    
    # 显示提取的原始分布
    total_extracted = sum(len(v) for v in samples_by_difficulty.values())
    print(f"\n提取到的样本总数: {total_extracted}")
    print("原始难度分布:")
    for diff in ['easy', 'medium', 'hard']:
        count = len(samples_by_difficulty[diff])
        percentage = (count / total_extracted * 100) if total_extracted > 0 else 0
        print(f"  {diff.capitalize()}: {count} ({percentage:.1f}%)")
    
    # 第二阶段：按目标分布采样
    print("\n阶段2: 按目标分布采样...")
    import random
    extracted = []
    
    for difficulty, ratio in difficulty_distribution.items():
        target_count = int(num_samples * ratio)
        available = samples_by_difficulty[difficulty]
        
        if len(available) >= target_count:
            # 随机采样
            selected = random.sample(available, target_count)
        else:
            # 不够就全部使用
            selected = available
            print(f"  ⚠ {difficulty}: 需要 {target_count} 条，但只有 {len(available)} 条可用")
        
        extracted.extend(selected)
        print(f"  ✓ {difficulty.capitalize()}: 采样 {len(selected)} 条 (目标: {target_count})")
    
    # 如果总数不足，从剩余样本中补充
    if len(extracted) < num_samples:
        shortage = num_samples - len(extracted)
        print(f"\n  ⚠ 总数不足 {num_samples}，缺少 {shortage} 条")
        
        # 收集所有未使用的样本
        remaining = []
        for diff, samples in samples_by_difficulty.items():
            for s in samples:
                if s not in extracted:
                    remaining.append(s)
        
        if remaining:
            补充数 = min(shortage, len(remaining))
            补充样本 = random.sample(remaining, 补充数)
            extracted.extend(补充样本)
            print(f"  ✓ 从剩余样本中补充 {补充数} 条")
    
    # 打乱顺序
    random.shuffle(extracted)
    
    # 保存结果
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\nSaving to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in extracted:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    # 统计信息
    print("\n" + "=" * 70)
    print("提取完成!")
    print("=" * 70)
    print(f"✓ 成功提取: {len(extracted)} 条")
    print(f"\n跳过统计:")
    for reason, count in stats.items():
        if count > 0:
            print(f"  ⊘ {reason}: {count} 条")
    print(f"\n✓ 输出文件: {output_file}")
    
    # 显示样本示例
    if extracted:
        print("\n" + "=" * 70)
        print("示例数据 (第1条):")
        print("=" * 70)
        sample = extracted[0]
        print(f"Full Name: {sample.get('full_name', 'N/A')}")
        print(f"File Path: {sample.get('file_path', 'N/A')}")
        print(f"Num Tactics: {sample.get('num_tactics', 0)}")
        print(f"Difficulty: {sample.get('difficulty', 'N/A')}")
        print(f"Is Complete: {sample.get('is_complete', False)}")
        
        print(f"\nImports (证明中使用的模块) ({len(sample.get('imports', []))}):")
        imports = sample.get('imports', [])
        for imp in imports[:10]:
            print(f"  - {imp}")
        if len(imports) > 10:
            print(f"  ... and {len(imports) - 10} more")
        
        print(f"\n证明中使用的定理/引理 ({len(sample.get('used_theorems', []))}):")
        theorems = sample.get('used_theorems', [])
        for thm in theorems[:5]:
            print(f"  - {thm['full_name']}")
            print(f"    模块: {thm['module']}")
            print(f"    定义: {thm['def_path']}")
        if len(theorems) > 5:
            print(f"  ... and {len(theorems) - 5} more")
        
        print(f"\nContext (变量和假设):")
        context = sample.get('context', '')
        print(context[:200] + ('...' if len(context) > 200 else ''))
        
        print(f"\nGoal (要证明的目标):")
        goal = sample.get('goal', '')
        print(goal[:200] + ('...' if len(goal) > 200 else ''))
        
        print(f"\nProof (前3个tactics):")
        proof_lines = sample.get('proof', '').split('\n')
        for line in proof_lines[:3]:
            print(f"  {line}")
        if len(proof_lines) > 3:
            print(f"  ... (total {len(proof_lines)} tactics)")
        
        # 检查关键字段
        print("\n" + "=" * 70)
        print("关键字段检查:")
        print("=" * 70)
        required_fields = [
            'full_name', 'state', 'theorem', 'proof', 
            'imports', 'used_theorems', 'context', 'goal', 'difficulty'
        ]
        for field in required_fields:
            value = sample.get(field)
            has_value = bool(value)
            status = "✓" if has_value else "✗"
            print(f"{status} {field}: {'有值' if has_value else '缺失'}")
        
        # 验证state格式
        if '⊢' in sample.get('state', ''):
            print(f"\n✓ State包含turnstile (⊢)，格式正确")
        else:
            print(f"\n⚠ State缺少turnstile符号")
    
    # 导出统计信息
    if extracted:
        tactics_counts = [s['num_tactics'] for s in extracted]
        imports_counts = [len(s.get('imports', [])) for s in extracted]
        theorems_counts = [len(s.get('used_theorems', [])) for s in extracted]
        
        # 难度分布
        difficulty_counts = defaultdict(int)
        for s in extracted:
            difficulty_counts[s.get('difficulty', 'unknown')] += 1
        
        print("\n" + "=" * 70)
        print("数据统计:")
        print("=" * 70)
        print(f"Tactics数量: min={min(tactics_counts)}, max={max(tactics_counts)}, avg={sum(tactics_counts)/len(tactics_counts):.1f}")
        print(f"使用的模块数量: min={min(imports_counts)}, max={max(imports_counts)}, avg={sum(imports_counts)/len(imports_counts):.1f}")
        print(f"使用的定理数量: min={min(theorems_counts)}, max={max(theorems_counts)}, avg={sum(theorems_counts)/len(theorems_counts):.1f}")
        print(f"\n难度分布:")
        for diff in ['easy', 'medium', 'hard']:
            count = difficulty_counts[diff]
            percentage = (count / len(extracted)) * 100
            print(f"  {diff.capitalize()}: {count} ({percentage:.1f}%)")
    
    return extracted

if __name__ == '__main__':
    # 配置路径
    BENCHMARK_DIR = Path("data/leandojo_benchmark")
    TRAIN_JSON = BENCHMARK_DIR / "random" / "train.json"
    OUTPUT_FILE = "data/raw/train_samples_1000.jsonl"
    
    # 目标难度分布：简单10%，中等70%，难20%
    TARGET_DISTRIBUTION = {
        'easy': 0.10,    # 100条
        'medium': 0.70,  # 700条
        'hard': 0.20     # 200条
    }
    
    # 提取样本
    samples = extract_train_samples(
        train_json=str(TRAIN_JSON),
        output_file=OUTPUT_FILE,
        num_samples=1000,
        min_tactics=1,  # 至少1个tactic
        max_tactics=50,  # 最多50个tactic（避免太复杂）
        require_complete=True,  # 要求证明完整
        difficulty_distribution=TARGET_DISTRIBUTION  # 按难度分布采样
    )
    
    print("\n" + "=" * 70)
    print("使用方法:")
    print("=" * 70)
    print(f"  数据文件: {OUTPUT_FILE}")
    print("  格式: JSONL (每行一个JSON对象)")
    print("\n字段说明:")
    print("  - full_name: 定理全名")
    print("  - state: 完整Lean proof state (context ⊢ goal)")
    print("  - theorem: 定理声明")
    print("  - proof: tactic序列")
    print("  - imports: 文件级别的imports")
    print("  - open_namespaces: 推断的命名空间")
    print("  - dependencies: 证明中使用的定理/定义")
    print("  - context: 上下文（变量、假设）")
    print("  - goal: 证明目标")
    print("  - difficulty: 推断难度 (easy/medium/hard)")
    print("\n可以用这个数据测试Forward/Backward/Consensus pipeline!")
