import sys
sys.path.insert(0, 'src')
from src.data_gen.validate_lean_code import LeanCodeValidator
import json
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def quick_validate(limit=20, timeout=60):
    """
    快速验证工具 - 用较短超时测试更多样本
    """
    validator = LeanCodeValidator()
    
    # 读取数据
    data_file = Path('data/step3_consensus_v2/enhanced_consensus.jsonl')
    with open(data_file, encoding='utf-8') as f:
        samples = [json.loads(line) for line in f if line.strip()][:limit]
    
    logger.info(f"开始验证 {len(samples)} 个样本 (超时: {timeout}秒)...")
    
    valid_samples = []
    error_samples = []
    
    for i, data in enumerate(samples, 1):
        theorem_name = data.get('full_name', 'unknown')
        logger.info(f"\n[{i}/{len(samples)}] {theorem_name}")
        
        # 验证
        is_valid, error_msg = validator.validate_sample(data, timeout=timeout)
        
        if is_valid:
            logger.info(f"  ✅ 通过")
            valid_samples.append(data)
        else:
            logger.info(f"  ❌ 失败: {error_msg[:80]}...")
            error_samples.append({
                'theorem': data.get('theorem', ''),
                'full_name': theorem_name,
                'error': error_msg,
                'data': data
            })
    
    # 保存结果
    output_dir = Path('data/validated')
    output_dir.mkdir(exist_ok=True)
    
    with open(output_dir / 'quick_valid.jsonl', 'w', encoding='utf-8') as f:
        for sample in valid_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    with open(output_dir / 'quick_errors.jsonl', 'w', encoding='utf-8') as f:
        for sample in error_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    # 生成报告
    report = f"""
{'='*60}
快速验证报告
{'='*60}

总样本数: {len(samples)}
验证通过: {len(valid_samples)} ({len(valid_samples)/len(samples)*100:.1f}%)
验证失败: {len(error_samples)} ({len(error_samples)/len(samples)*100:.1f}%)
超时设置: {timeout}秒

失败样本详情:
"""
    for i, err in enumerate(error_samples[:10], 1):  # 只显示前10个
        report += f"\n{i}. {err['full_name']}\n"
        report += f"   错误: {err['error'][:120]}\n"
    
    if len(error_samples) > 10:
        report += f"\n... 还有 {len(error_samples)-10} 个失败样本\n"
    
    report_file = output_dir / 'quick_report.txt'
    report_file.write_text(report, encoding='utf-8')
    
    print(report)
    logger.info(f"\n结果已保存到: {output_dir}")

if __name__ == '__main__':
    quick_validate(limit=20, timeout=60)
