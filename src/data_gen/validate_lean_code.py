"""
Lean 4 代码验证模块
用于验证训练数据中的 Lean 4 代码是否能通过编译
只有能通过编译的数据才保留用于训练
"""

import json
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LeanCodeValidator:
    """Lean 4 代码验证器"""
    
    def __init__(self, lean_project_path: str = "lean_gym", timeout: int = 180):
        """
        初始化验证器
        
        Args:
            lean_project_path: Lean 项目路径 (包含 lakefile.lean 或 lakefile.toml)
            timeout: 编译超时时间(秒)，默认180秒（Mathlib依赖需要较长时间）
        """
        self.lean_project_path = Path(lean_project_path).absolute()
        self.timeout = timeout
        
        # 检查 Lean 项目是否存在
        if not self.lean_project_path.exists():
            raise FileNotFoundError(f"Lean 项目路径不存在: {self.lean_project_path}")
        
        # 简单检查项目配置文件
        if not (self.lean_project_path / "lakefile.toml").exists() and \
           not (self.lean_project_path / "lakefile.lean").exists() and \
           not (self.lean_project_path / "leanpkg.toml").exists():
            logger.warning(f"警告: 在 {self.lean_project_path} 未找到标准的 Lean 配置文件 (lakefile/leanpkg)")
        
        logger.info(f"Lean 项目路径: {self.lean_project_path}")
        
    def extract_lean_code(self, data: Dict) -> Optional[str]:
        """
        从数据中提取 Lean 代码
        
        **策略: 分离提取定理签名和证明部分,然后组合验证**
        
        Args:
            data: 包含 Lean 代码的数据字典
            
        Returns:
            提取的 Lean 代码或 None
        """
        # Step 1: 提取完整的定理签名（带类型声明）
        theorem_signature = None
        
        # 尝试从 final_skeleton 中提取签名(支持多行定理声明)
        if 'final_skeleton' in data and data['final_skeleton']:
            skeleton = data['final_skeleton'].strip()
            lines = skeleton.split('\n')
            
            # 找到定理开始行
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if line_stripped.startswith('theorem '):
                    # 收集定理签名的所有行,直到遇到 := 或 by
                    sig_lines = []
                    j = i
                    while j < len(lines):
                        current_line = lines[j].strip()
                        if not current_line or current_line.startswith('--'):
                            # 跳过空行和注释
                            j += 1
                            continue
                        
                        # 检查是否包含 := by (完整形式)
                        if ':= by' in current_line:
                            # 提取 := by 之前的部分
                            before_by = current_line.split(':= by')[0].strip()
                            sig_lines.append(before_by)
                            theorem_signature = ' '.join(sig_lines) + ' := by'
                            break
                        # 检查是否只有 :=
                        elif ':=' in current_line:
                            before_assign = current_line.split(':=')[0].strip()
                            sig_lines.append(before_assign)
                            theorem_signature = ' '.join(sig_lines) + ' :='
                            break
                        else:
                            # 继续收集签名行
                            sig_lines.append(current_line)
                            j += 1
                    break
        
        # 如果没找到完整签名，尝试从backward_source构建
        if not theorem_signature and 'backward_source' in data:
            backward = data['backward_source']
            if isinstance(backward, dict) and 'theorem' in backward:
                theorem_signature = backward['theorem'].strip()
        
        # Step 2: 提取证明部分
        proof_body = None
        
        # 【最高优先级】提取 final_skeleton 中的证明骨架
        # 注意：final_skeleton 中的 sorry 是预期的（教学用途），应该保留
        if 'final_skeleton' in data and data['final_skeleton']:
            skeleton = data['final_skeleton'].strip()
            lines = skeleton.split('\n')
            
            # 找到定理声明后的证明部分
            proof_lines = []
            found_theorem = False
            found_proof_start = False  # 标记是否找到 := by
            
            for line in lines:
                line_stripped = line.strip()
                
                # 跳过注释和空行(定理声明前的)
                if not found_theorem and (not line_stripped or line_stripped.startswith('--')):
                    continue
                
                # 检测定理开始
                if not found_theorem and line_stripped.startswith('theorem '):
                    found_theorem = True
                
                # 如果已经找到定理但还没找到证明开始
                if found_theorem and not found_proof_start:
                    # 检查这一行是否包含 := by (证明开始)
                    if ':= by' in line:
                        found_proof_start = True
                        # 提取 := by 后面的内容
                        after_by = line.split(':= by', 1)[1]
                        if after_by.strip():
                            proof_lines.append(after_by)
                    # 跳过定理签名的其他行
                    continue
                
                # 如果已经找到证明开始,收集所有后续非空行
                if found_proof_start:
                    if line_stripped:  # 保留所有非空行，包括注释
                        proof_lines.append(line)
            
            if proof_lines:
                proof_body = '\n'.join(proof_lines).strip()
        
        # 【次优先级】从 backward_source 提取完整证明
        if not proof_body and 'backward_source' in data:
            backward = data['backward_source']
            if isinstance(backward, dict) and 'proof' in backward:
                proof_body = backward['proof'].strip()
        
        # Step 3: 组合签名和证明
        if theorem_signature and proof_body:
            # 检查theorem_signature是否已经包含 := by
            if ':= by' in theorem_signature:
                # 如果已经有 := by, 直接添加证明体
                full_code = f"{theorem_signature}\n  {proof_body}"
            elif theorem_signature.endswith(':='):
                # 如果只有 :=, 添加 by 和证明体  
                full_code = f"{theorem_signature} by\n  {proof_body}"
            else:
                # 没有 :=, 需要添加
                full_code = f"{theorem_signature} := by\n  {proof_body}"
            
            logger.debug(f"组合定理代码: {full_code[:150]}...")
            logger.info(f"完整提取的代码:\n{full_code}")  # 临时调试
            return full_code
        elif theorem_signature:
            # 只有签名，没有证明体
            logger.warning("只找到定理签名，没有证明部分")
            return theorem_signature
        
        # 如果有顶层的 theorem 和 proof 字段
        if 'theorem' in data and 'proof' in data:
            theorem_decl = data['theorem']
            proof = data['proof']
            if isinstance(theorem_decl, str) and isinstance(proof, str):
                full_code = f"{theorem_decl.strip()} := {proof.strip()}"
                if 'sorry' not in full_code.lower():
                    return full_code
        
        # 尝试其他可能的字段(但跳过包含sorry的)
        possible_fields = [
            'lean_code',
            'code',
            'complete_proof'
        ]
        
        for field in possible_fields:
            if field in data and data[field]:
                code = data[field]
                if isinstance(code, str) and code.strip():
                    # 跳过包含sorry的不完整代码
                    if 'sorry' not in code.lower():
                        return code.strip()
        
        return None
    
    def validate_code(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        验证 Lean 代码是否能通过编译
        
        Args:
            code: 要验证的 Lean 代码
            
        Returns:
            (是否通过, 错误信息)
        """
        # 确保临时验证目录存在
        validation_dir = self.lean_project_path / "LeanGym"
        validation_dir.mkdir(exist_ok=True)

        # 生成唯一的文件名，避免多线程冲突 (虽然验证是串行的，但好习惯)
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        temp_filename = f"TempValidation_{unique_id}.lean"
        temp_file = validation_dir / temp_filename
        
        try:
            # 写入代码
            lean_content = f"""-- Auto-generated validation file
import Mathlib

{code}
"""
            temp_file.write_text(lean_content, encoding='utf-8')
            
            # 构造命令: 使用 lake env lean 直接验证文件
            # 这种方式比 lake build 更灵活，不需要修改 lakefile 配置
            # 路径使用相对路径，基于 cwd
            relative_path = os.path.join("LeanGym", temp_filename)
            
            cmd = ["lake", "env", "lean", relative_path]
            
            # 运行验证
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.lean_project_path,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    encoding='utf-8',
                    errors='replace'
                )
                
                # Lean 编译器: 成功通常无输出或只有警告，返回码为0
                if result.returncode == 0:
                    return True, None
                else:
                    # 提取错误信息
                    error_msg = result.stderr if result.stderr else result.stdout
                    # 过滤掉一些无关的警告信息，只保留 Error
                    return False, error_msg
                    
            except subprocess.TimeoutExpired:
                return False, f"编译超时 (>{self.timeout}秒) - 请检查 Lean 环境是否已 build Mathlib"
            
        except Exception as e:
            return False, f"验证过程系统错误: {str(e)}"
            
        finally:
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass

    def validate_dataset(
        self,
        input_file: str,
        output_file: str,
        max_workers: int = 4,
        max_samples: Optional[int] = None
    ) -> Dict:
        """
        验证整个数据集
        
        Args:
            input_file: 输入 JSONL 文件路径
            output_file: 输出 JSONL 文件路径 (仅包含验证通过的数据)
            max_workers: 并行验证的最大工作线程数
            max_samples: 最大验证样本数 (用于测试)
            
        Returns:
            验证统计信息
        """
        input_path = Path(input_file)
        output_path = Path(output_file)
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取数据
        logger.info(f"读取数据: {input_path}")
        data_list = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if max_samples and len(data_list) >= max_samples:
                    break
                # 跳过空行
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    data_list.append(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"跳过无效 JSON (行 {i+1}): {e}")
        
        total_samples = len(data_list)
        logger.info(f"总样本数: {total_samples}")
        
        # 统计信息
        stats = {
            'total': total_samples,
            'valid': 0,
            'invalid': 0,
            'no_code': 0,
            'errors': []
        }
        
        # 写入有效数据
        valid_count = 0
        
        with open(output_path, 'w', encoding='utf-8') as f_out:
            # 使用线程池进行并行验证
            # 注意: 如果 max_workers > 1, 确保机器性能足够
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_data = {}
                for data in data_list:
                    code = self.extract_lean_code(data)
                    if code:
                        future = executor.submit(self.validate_code, code)
                        future_to_data[future] = data
                    else:
                        stats['no_code'] += 1
                        logger.warning(f"跳过无代码的样本: {data.get('theorem', 'unknown')}")
                
                # 处理结果
                with tqdm(total=len(future_to_data), desc="验证进度") as pbar:
                    for future in as_completed(future_to_data):
                        data = future_to_data[future]
                        try:
                            is_valid, error_msg = future.result()
                            
                            if is_valid:
                                # 写入有效数据
                                f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                                stats['valid'] += 1
                                valid_count += 1
                            else:
                                stats['invalid'] += 1
                                stats['errors'].append({
                                    'theorem': data.get('theorem', 'unknown'),
                                    'error': error_msg
                                })
                                # 仅在DEBUG模式下打印详细失败信息，避免刷屏
                                logger.debug(f"验证失败: {data.get('theorem', 'unknown')}")
                                
                        except Exception as e:
                            stats['invalid'] += 1
                            stats['errors'].append({
                                'theorem': data.get('theorem', 'unknown'),
                                'error': str(e)
                            })
                            logger.error(f"处理出错: {e}")
                        
                        pbar.update(1)
        
        # 输出统计信息
        logger.info("\n" + "="*60)
        logger.info("验证完成!")
        logger.info(f"总样本数: {stats['total']}")
        logger.info(f"有效样本: {stats['valid']} ({stats['valid']/stats['total']*100:.2f}%)")
        logger.info(f"无效样本: {stats['invalid']} ({stats['invalid']/stats['total']*100:.2f}%)")
        logger.info(f"无代码样本: {stats['no_code']}")
        logger.info(f"输出文件: {output_path}")
        logger.info("="*60)
        
        # 保存错误日志
        if stats['errors']:
            error_log = output_path.parent / f"{output_path.stem}_errors.jsonl"
            with open(error_log, 'w', encoding='utf-8') as f:
                for error in stats['errors']:
                    f.write(json.dumps(error, ensure_ascii=False) + '\n')
            logger.info(f"错误日志: {error_log}")
        
        return stats