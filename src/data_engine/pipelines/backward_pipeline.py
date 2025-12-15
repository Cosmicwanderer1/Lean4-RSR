import json
import logging
import os
import sys
import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 导入 OpenAI 客户端
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# 导入提示词模板
try:
    from src.data_engine.prompts.backward_v1 import BackwardAnalysisV1
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from src.data_engine.prompts.backward_v1 import BackwardAnalysisV1

# ==========================================
# 1. 核心数据结构
# ==========================================

@dataclass
class BackwardSample:
    """
    逆向分析阶段的输出结构
    """
    theorem: str
    full_name: str
    proof: str
    
    # 逆向分析结果
    proof_structure: str          # 证明模式 (如 "Induction on n")
    key_transitions: List[str]    # 关键状态转换
    reasoning_chain: str          # 逻辑推理链
    
    # 元数据
    model_name: str = ""
    prompt_version: str = ""

# ==========================================
# 2. 逆向分析器
# ==========================================

class BackwardAnalyzer:
    """
    逆向分析器：从已验证的证明中提取结构
    """
    
    def __init__(self, model_name: str, prompt_engine=None):
        self.model_name = model_name
        self.prompt_engine = prompt_engine if prompt_engine else BackwardAnalysisV1()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化 API 客户端
        if OpenAI is None:
            self.logger.error("OpenAI library not installed. Please run `pip install openai`.")
            sys.exit(1)
            
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            self.logger.error("=" * 60)
            self.logger.error("❌ DEEPSEEK_API_KEY not found!")
            self.logger.error("=" * 60)
            self.logger.error("Please set your DeepSeek API Key in PowerShell:")
            self.logger.error('  $env:DEEPSEEK_API_KEY = "your-api-key-here"')
            self.logger.error("")
            self.logger.error("Or get your API key at: https://platform.deepseek.com")
            self.logger.error("=" * 60)
            sys.exit(1)
            
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    
    def analyze(self, item: Dict) -> Optional[BackwardSample]:
        """
        对单个定理进行逆向分析
        
        Args:
            item: 包含 statement, proof, imports 等字段的字典
        """
        # 确保 ID存在，与Forward保持一致：优先使用decl_name
        if 'decl_name' in item and item.get('decl_name'):
            item['id'] = item['decl_name']
        elif 'id' not in item or not item.get('id'):
            item['id'] = f"thm_{hash(item.get('statement', ''))}"
        
        sys_prompt = self.prompt_engine.system_prompt
        user_msg = self.prompt_engine.render_user_message(item)
        
        try:
            full_name = item.get('full_name', 'unknown')
            self.logger.debug(f"Analyzing proof for {full_name}...")
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.3,  # 逆向分析需要更保守，温度较低
                max_tokens=4096,  # 骨架可能很长
                stop=self.prompt_engine.stop_tokens
            )
            
            raw_output = response.choices[0].message.content
            
            # 验证完整性
            if not self.prompt_engine.validate_response(raw_output):
                self.logger.warning(f"Validation failed for {item.get('decl_name')}.")
                return None

            parsed = self._parse_output(raw_output)
            
            if parsed:
                return BackwardSample(
                    theorem=item.get('theorem', ''),
                    full_name=item.get('full_name', 'unknown'),
                    proof=item.get('proof', ''),
                    proof_structure=parsed['structure'],
                    key_transitions=parsed['transitions'],
                    reasoning_chain=parsed['reasoning'],
                    model_name=self.model_name,
                    prompt_version=self.prompt_engine.__class__.__name__
                )
            else:
                self.logger.warning(f"Parsing failed for {item.get('full_name', 'unknown')}")
                preview = raw_output[:800] if len(raw_output) > 800 else raw_output
                self.logger.warning(f"Raw output preview:\n{preview}\n...")
                return None
                
        except Exception as e:
            self.logger.error(f"Error analyzing {item.get('full_name', 'unknown')}: {e}")
            return None

    def _parse_output(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        解析 XML 标签提取逆向分析结果
        """
        # 定义正则模式
        structure_pattern = re.compile(
            r'<proof_structure>(.*?)</proof_structure>', 
            re.DOTALL | re.IGNORECASE
        )
        transitions_pattern = re.compile(
            r'<key_transitions>(.*?)</key_transitions>', 
            re.DOTALL | re.IGNORECASE
        )
        reasoning_pattern = re.compile(
            r'<reasoning_chain>(.*?)</reasoning_chain>', 
            re.DOTALL | re.IGNORECASE
        )
        
        # 提取完整标签
        structure_match = structure_pattern.search(raw_text)
        transitions_match = transitions_pattern.search(raw_text)
        reasoning_match = reasoning_pattern.search(raw_text)
        
        if structure_match:  # skeleton 可选
            # 处理 transitions（可能是多行列表）
            transitions_raw = transitions_match.group(1).strip() if transitions_match else ""
            transitions_list = [
                line.strip() 
                for line in transitions_raw.split('\n') 
                if line.strip() and not line.strip().startswith('#')
            ]
            
            return {
                'structure': structure_match.group(1).strip(),
                'transitions': transitions_list,
                'reasoning': reasoning_match.group(1).strip() if reasoning_match else ""
            }
        
        # 宽容模式：提取未闭合的标签
        structure_partial = re.compile(
            r'<proof_structure>\s*([\s\S]+?)(?=\n\n<|$)', 
            re.IGNORECASE
        )
        structure_match_p = structure_partial.search(raw_text)
        
        if structure_match_p:
            return {
                'structure': structure_match_p.group(1).strip(),
                'transitions': [],
                'reasoning': reasoning_match.group(1).strip() if reasoning_match else ""
            }
        
        return None

# ==========================================
# 3. 流水线执行入口
# ==========================================

def run_backward_pipeline(input_file: str, output_file: str, max_samples: int = 10, max_workers: int = 4):
    """
    运行逆向分析流水线（支持并发）
    
    Args:
        input_file: 输入文件路径（包含 proof 的 JSONL）
        output_file: 输出文件路径
        max_samples: 最大处理样本数
        max_workers: 并发线程数（默认4）
    """
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - [Backward] %(message)s')
    logger = logging.getLogger("BackwardPipeline")
    logger.setLevel(logging.INFO)
    
    analyzer = BackwardAnalyzer(model_name="deepseek-chat", prompt_engine=BackwardAnalysisV1())
    
    logger.info(f"Starting backward analysis pipeline for {input_file}")
    logger.info(f"Using {max_workers} concurrent threads")
    
    # 读取所有样本
    samples = []
    try:
        with open(input_file, 'r', encoding='utf-8') as f_in:
            for line in f_in:
                if len(samples) >= max_samples:
                    break
                
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # 跳过没有 proof 的项
                if 'proof' not in item or not item['proof']:
                    continue
                    
                samples.append(item)
                
    except FileNotFoundError:
        logger.error(f"Input file not found: {input_file}")
        return
    
    logger.info(f"Loaded {len(samples)} samples, starting concurrent processing...")
    
    # 并发处理
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    write_lock = threading.Lock()
    generated_count = 0
    
    def process_sample(item: Dict) -> Optional[Dict]:
        """处理单个样本"""
        result = analyzer.analyze(item)
        if result:
            return {
                "id": result.full_name,  # 用于与forward匹配
                "decl_name": result.full_name,  # 统一使用decl_name
                "statement": result.theorem,  # 统一使用statement
                "proof": result.proof,
                "difficulty": item.get('difficulty', ''),
                "state": item.get('state', ''),  # 保留类型变量信息
                "context": item.get('context', ''),  # 分离的上下文
                "goal": item.get('goal', ''),  # 分离的目标
                "backward_analysis": {
                    "proof_structure": result.proof_structure,
                    "key_transitions": result.key_transitions,
                    "reasoning_chain": result.reasoning_chain
                },
                "metadata": {
                    "strategy": "backward_v1",
                    "model": result.model_name
                }
            }
        return None
    
    with open(output_file, 'w', encoding='utf-8') as f_out:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_sample, sample): sample for sample in samples}
            
            for future in as_completed(futures):
                output_data = future.result()
                if output_data:
                    with write_lock:
                        f_out.write(json.dumps(output_data, ensure_ascii=False) + '\n')
                        f_out.flush()
                        generated_count += 1
                        
                        if generated_count % 5 == 0:
                            logger.info(f"Progress: {generated_count}/{len(samples)} completed")
    
    logger.info(f"Backward analysis pipeline completed. Processed {generated_count} proofs.")

if __name__ == "__main__":
    # 快速测试
    import argparse
    parser = argparse.ArgumentParser(description='Backward Analysis Pipeline')
    parser.add_argument('--input', type=str, default='./data/raw/mathlib_theorems.jsonl')
    parser.add_argument('--output', type=str, default='./data/step2_backward/backward_analysis.jsonl')
    parser.add_argument('--max-samples', type=int, default=10)
    args = parser.parse_args()
    
    run_backward_pipeline(args.input, args.output, args.max_samples)
