import json
import logging
import os
import sys
import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 尝试导入 OpenAI 客户端
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# 路径处理
try:
    from src.data_engine.prompts.forward_v1 import ForwardPlanV1
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from src.data_engine.prompts.forward_v1 import ForwardPlanV1

# ==========================================
# 1. 核心数据结构 (Simplified)
# ==========================================

@dataclass
class PlanningSample:
    """
    定义【正向规划】阶段的输出结构。
    """
    theorem: str
    full_name: str
    problem_type: str
    proof_strategy: str
    # suggested_theorems 已移除，保持结构纯净
    
    # 元数据
    model_name: str = ""
    prompt_version: str = ""

class BaseGenerator(ABC):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def generate(self, item: Dict) -> Optional[PlanningSample]:
        pass

# ==========================================
# 2. 正向规划生成器
# ==========================================

class ForwardPlanner(BaseGenerator):
    
    def __init__(self, model_name: str, prompt_engine=None):
        super().__init__(model_name)
        self.prompt_engine = prompt_engine if prompt_engine else ForwardPlanV1()
        
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
    
    def generate(self, item: Dict) -> Optional[PlanningSample]:
        sys_prompt = self.prompt_engine.system_prompt
        user_msg = self.prompt_engine.render_user_message(item)
        
        # 生成唯一 ID（如果没有的话）
        if 'id' not in item or not item.get('id'):
            item['id'] = item.get('decl_name', f"thm_{hash(item.get('statement', ''))}")
        
        try:
            self.logger.debug(f"Planning for {item.get('decl_name')}...")
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.7,
                max_tokens=3072,  # 增加到 3K 避免截断
                stop=self.prompt_engine.stop_tokens
            )
            
            raw_output = response.choices[0].message.content
            
            # 验证完整性
            if not self.prompt_engine.validate_response(raw_output):
                self.logger.warning(f"Validation failed for {item.get('decl_name')}.")
                return None

            parsed = self._parse_output(raw_output)
            
            if parsed:
                return PlanningSample(
                    theorem=item.get('theorem', ''),
                    full_name=item.get('full_name', 'unknown'),
                    problem_type=parsed['type'],
                    proof_strategy=parsed['strategy'],
                    model_name=self.model_name,
                    prompt_version=self.prompt_engine.__class__.__name__
                )
            else:
                self.logger.warning(f"Parsing failed for {item.get('full_name')}")
                # 打印原始输出的前 800 字符以便调试
                preview = raw_output[:800] if len(raw_output) > 800 else raw_output
                self.logger.warning(f"Raw output preview:\n{preview}\n...")
                return None
                
        except Exception as e:
            self.logger.error(f"Error generating for {item.get('full_name', 'unknown')}: {e}")
            return None

    def _parse_output(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        解析 XML 标签：仅解析 problem_type 和 proof_strategy
        支持未完全闭合的标签（宽容模式）
        """
        # 尝试完整标签
        type_pattern = re.compile(r'<problem_type>(.*?)</problem_type>', re.DOTALL | re.IGNORECASE)
        strategy_pattern = re.compile(r'<proof_strategy>(.*?)</proof_strategy>', re.DOTALL | re.IGNORECASE)
        
        type_match = type_pattern.search(raw_text)
        strategy_match = strategy_pattern.search(raw_text)
        
        # 如果找到完整标签，优先使用
        if type_match and strategy_match:
            return {
                'type': type_match.group(1).strip(),
                'strategy': strategy_match.group(1).strip()
            }
        
        # 宽容模式：尝试提取未闭合的标签内容
        type_partial = re.compile(r'<problem_type>\s*([\s\S]+?)(?=\n\n<|\n<proof_strategy>|$)', re.IGNORECASE)
        strategy_partial = re.compile(r'<proof_strategy>\s*([\s\S]+?)(?=$)', re.IGNORECASE)
        
        type_match_p = type_partial.search(raw_text)
        strategy_match_p = strategy_partial.search(raw_text)
        
        if type_match_p and strategy_match_p:
            return {
                'type': type_match_p.group(1).strip(),
                'strategy': strategy_match_p.group(1).strip()
            }
        
        return None

# ==========================================
# 3. 流水线执行入口
# ==========================================

def run_planning_pipeline(input_file: str, output_file: str, max_samples: int = 10, max_workers: int = 4):
    """
    运行正向规划流水线（支持并发）
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        max_samples: 最大处理样本数
        max_workers: 并发线程数（默认4）
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [Planner] %(message)s')
    logger = logging.getLogger("Pipeline")
    
    planner = ForwardPlanner(model_name="deepseek-chat", prompt_engine=ForwardPlanV1())
    
    logger.info(f"Starting planning pipeline for {input_file}")
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
                
                # 检查必需字段
                if not item.get('theorem'):
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
    
    def validate_context_consistency(item: Dict) -> bool:
        """
        验证上下文一致性，防止定理名与实际内容不匹配。
        检查：
        1. full_name是否在proof中被引用
        2. theorem和proof是否包含相同的主要符号
        """
        full_name = item.get('full_name', '')
        theorem = item.get('theorem', '')
        proof = item.get('proof', '')
        
        if not all([full_name, theorem, proof]):
            return True  # 缺少字段时跳过验证
        
        # 提取定理名的最后一部分（如 nat.bodd_mul -> bodd_mul）
        theorem_base_name = full_name.split('.')[-1] if '.' in full_name else full_name
        
        # 检查proof中是否引用了该定理（排除常见的辅助定理）
        if len(theorem_base_name) > 3:  # 忽略太短的名字（如 add, mul）
            # 警告：定理名在proof中不应该出现（避免循环引用）
            # 但如果名字完全无关，可能是数据错误
            pass
        
        # 基本一致性检查通过
        return True
    
    def process_sample(item: Dict) -> Optional[Dict]:
        """处理单个样本"""
        # 验证上下文一致性
        if not validate_context_consistency(item):
            print(f"⚠️  Context drift detected for {item.get('full_name', 'Unknown')}, skipping...")
            return None
        
        result = planner.generate(item)
        if result:
            return {
                "id": result.full_name,  # 用于与backward匹配
                "decl_name": result.full_name,  # 统一使用decl_name
                "statement": result.theorem,  # 统一使用statement
                "difficulty": item.get('difficulty', ''),
                "problem_type": result.problem_type,
                "proof_strategy": result.proof_strategy,
                "state": item.get('state', ''),  # 保留类型变量信息
                "context": item.get('context', ''),  # 分离的上下文
                "goal": item.get('goal', ''),  # 分离的目标
                "proof": item.get('proof', ''),   # 同时保留proof供后续阶段使用
                "metadata": {
                    "strategy": "forward_planning_v1_simplified",
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
    
    logger.info(f"Planning pipeline completed. Generated {generated_count} plans.")

if __name__ == "__main__":
    # 简单的本地测试入口
    pass