import sys
sys.path.insert(0, 'src')
from src.data_gen.validate_lean_code import LeanCodeValidator
import json

validator = LeanCodeValidator()

# 读取所有之前失败的样本
with open('data/validated/test_consensus_valid_errors.jsonl', encoding='utf-8') as f:
    lines = [json.loads(line) for line in f]

print(f"=== 检查 {len(lines)} 个之前失败的样本 ===\n")

errors = []
for i, item in enumerate(lines, 1):
    data = item['original_data']
    theorem_name = item['full_name']
    original_error = item['message']
    
    # 提取代码
    code = validator.extract_lean_code(data)
    first_line = code.split('\n')[0]
    
    # 检查常见语法错误
    has_double_colon = ': :=' in first_line
    has_unexpected_equals = first_line.count('=') > 1 and ':=' not in first_line
    
    status = "❌" if (has_double_colon or has_unexpected_equals) else "✅"
    
    print(f"{status} 样本 {i}: {theorem_name}")
    print(f"   第1行: {first_line[:100]}...")
    
    if has_double_colon:
        errors.append((i, theorem_name, "双冒号 ': :='"))
    elif has_unexpected_equals:
        errors.append((i, theorem_name, "多余的等号"))
    
    print()

print(f"\n=== 总结 ===")
print(f"总样本数: {len(lines)}")
print(f"格式正确: {len(lines) - len(errors)}")
print(f"仍有错误: {len(errors)}")

if errors:
    print("\n仍有错误的样本:")
    for i, name, err_type in errors:
        print(f"  - 样本{i} ({name}): {err_type}")
