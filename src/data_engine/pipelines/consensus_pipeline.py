import json
import logging
import os
import sys
import re
from typing import Dict, Optional, Any
from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from src.data_engine.prompts.consensus_v1 import ConsensusJudgeV1
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from src.data_engine.prompts.consensus_v1 import ConsensusJudgeV1

# ==========================================
# 1. 数据结构
# ==========================================

@dataclass
class ConsensusSample:
    """
    共识阶段的最终输出
    """
    original_id: str
    decl_name: str
    statement: str
    
    # 共识结果
    consensus_strategy: str
    verified_skeleton: str
    unified_reasoning: str
    
    # 元数据
    model_name: str = ""
    prompt_version: str = ""

# ==========================================
# 2. 共识裁决器
# ==========================================

class ConsensusJudge:
    """
    共识裁决器：融合正向和逆向分析结果
    """
    
    def __init__(self, model_name: str, prompt_engine=None):
        self.model_name = model_name
        self.prompt_engine = prompt_engine if prompt_engine else ConsensusJudgeV1()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        if OpenAI is None:
            self.logger.error("OpenAI library not installed.")
            sys.exit(1)
            
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            self.logger.error("❌ DEEPSEEK_API_KEY not found!")
            sys.exit(1)
            
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    
    def judge(self, forward_data: Dict, backward_data: Dict) -> Optional[ConsensusSample]:
        """
        对单个定理进行共识裁决
        
        Args:
            forward_data: 正向分析结果
            backward_data: 逆向分析结果
        """
        # 验证数据一致性 - 防止上下文漂移
        forward_name = forward_data.get('decl_name', '')
        backward_name = backward_data.get('decl_name', '')
        
        if not forward_name or not backward_name:
            self.logger.error(f"❌ Missing decl_name: forward='{forward_name}', backward='{backward_name}'")
            return None
        
        if forward_name != backward_name:
            self.logger.error(f"❌ Context drift: forward='{forward_name}' != backward='{backward_name}'")
            return None
        
        # 合并数据
        merged_data = {
            'decl_name': forward_name,  # 已验证一致性
            'statement': forward_data.get('statement', ''),
            'state': forward_data.get('state', ''),  # 添加类型变量信息
            'forward_type': forward_data.get('problem_type', ''),
            'forward_strategy': forward_data.get('proof_strategy', ''),
            'backward_structure': backward_data.get('backward_analysis', {}).get('proof_structure', ''),
            'backward_transitions': backward_data.get('backward_analysis', {}).get('key_transitions', []),
            'backward_skeleton': backward_data.get('backward_analysis', {}).get('proof_skeleton', ''),
            'backward_reasoning': backward_data.get('backward_analysis', {}).get('reasoning_chain', '')
        }
        
        sys_prompt = self.prompt_engine.system_prompt
        user_msg = self.prompt_engine.render_user_message(merged_data)
        
        try:
            self.logger.debug(f"Judging consensus for {merged_data['decl_name']}...")
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.2,  # 共识阶段需要最保守
                max_tokens=4096,
                stop=self.prompt_engine.stop_tokens
            )
            
            raw_output = response.choices[0].message.content
            
            if not self.prompt_engine.validate_response(raw_output):
                self.logger.warning(f"Validation failed for {merged_data['decl_name']}.")
                return None

            parsed = self._parse_output(raw_output)
            
            if parsed:
                return ConsensusSample(
                    original_id=forward_data.get('id', 'unknown'),
                    decl_name=merged_data['decl_name'],
                    statement=merged_data['statement'],
                    consensus_strategy=parsed['strategy'],
                    verified_skeleton=parsed['skeleton'],
                    unified_reasoning=parsed['reasoning'],
                    model_name=self.model_name,
                    prompt_version=self.prompt_engine.__class__.__name__
                )
            else:
                self.logger.warning(f"Parsing failed for {merged_data['decl_name']}")
                preview = raw_output[:800] if len(raw_output) > 800 else raw_output
                self.logger.warning(f"Raw output preview:\n{preview}\n...")
                return None
                
        except Exception as e:
            self.logger.error(f"Error judging {merged_data['decl_name']}: {e}")
            return None

    def _parse_output(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """解析共识判断的输出"""
        strategy_pattern = re.compile(
            r'<consensus_strategy>(.*?)</consensus_strategy>', 
            re.DOTALL | re.IGNORECASE
        )
        skeleton_pattern = re.compile(
            r'<verified_skeleton>(.*?)</verified_skeleton>', 
            re.DOTALL | re.IGNORECASE
        )
        reasoning_pattern = re.compile(
            r'<unified_reasoning>(.*?)</unified_reasoning>', 
            re.DOTALL | re.IGNORECASE
        )
        
        strategy_match = strategy_pattern.search(raw_text)
        skeleton_match = skeleton_pattern.search(raw_text)
        reasoning_match = reasoning_pattern.search(raw_text)
        
        if strategy_match and skeleton_match:
            return {
                'strategy': strategy_match.group(1).strip(),
                'skeleton': skeleton_match.group(1).strip(),
                'reasoning': reasoning_match.group(1).strip() if reasoning_match else ""
            }
        
        # 宽容模式
        strategy_partial = re.compile(
            r'<consensus_strategy>\s*([\s\S]+?)(?=\n\n<|$)', 
            re.IGNORECASE
        )
        skeleton_partial = re.compile(
            r'<verified_skeleton>\s*([\s\S]+?)(?=\n\n<|$)', 
            re.IGNORECASE
        )
        
        strategy_match_p = strategy_partial.search(raw_text)
        skeleton_match_p = skeleton_partial.search(raw_text)
        
        if strategy_match_p and skeleton_match_p:
            return {
                'strategy': strategy_match_p.group(1).strip(),
                'skeleton': skeleton_match_p.group(1).strip(),
                'reasoning': ""
            }
        
        return None

# ==========================================
# 3. 流水线执行
# ==========================================

def run_consensus_pipeline(
    forward_file: str, 
    backward_file: str, 
    output_file: str, 
    max_samples: int = 10
):
    """
    运行共识裁决流水线
    
    Args:
        forward_file: Phase 1 输出文件
        backward_file: Phase 2 输出文件
        output_file: 最终输出文件
        max_samples: 最大处理样本数
    """
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - [Consensus] %(message)s')
    logger = logging.getLogger("ConsensusPipeline")
    logger.setLevel(logging.INFO)
    
    judge = ConsensusJudge(model_name="deepseek-chat", prompt_engine=ConsensusJudgeV1())
    
    logger.info("Loading forward and backward analysis results...")
    
    # 加载正向分析结果
    forward_data = {}
    with open(forward_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                forward_data[item['id']] = item
            except:
                continue
    
    # 加载逆向分析结果
    backward_data = {}
    with open(backward_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                backward_data[item['id']] = item
            except:
                continue
    
    # 找到交集
    common_ids = set(forward_data.keys()) & set(backward_data.keys())
    logger.info(f"Found {len(common_ids)} common theorems to judge.")
    
    generated_count = 0
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f_out:
        for theorem_id in list(common_ids)[:max_samples]:
            result = judge.judge(forward_data[theorem_id], backward_data[theorem_id])
            
            if result:
                output_data = {
                    "id": result.original_id,
                    "decl_name": result.decl_name,
                    "statement": result.statement,
                    "consensus": {
                        "strategy": result.consensus_strategy,
                        "verified_skeleton": result.verified_skeleton,
                        "unified_reasoning": result.unified_reasoning
                    },
                    "metadata": {
                        "strategy": "consensus_v1",
                        "model": result.model_name
                    }
                }
                f_out.write(json.dumps(output_data, ensure_ascii=False) + '\n')
                f_out.flush()
                generated_count += 1
                
                if generated_count % 5 == 0:
                    logger.info(f"Processed {generated_count} consensus judgments...")
    
    logger.info(f"Consensus pipeline completed. Generated {generated_count} final samples.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Consensus Judge Pipeline')
    parser.add_argument('--forward', type=str, default='./data/step1_planning/mathlib_plans.jsonl')
    parser.add_argument('--backward', type=str, default='./data/step2_backward/backward_analysis.jsonl')
    parser.add_argument('--output', type=str, default='./data/step3_consensus/final_training_data.jsonl')
    parser.add_argument('--max-samples', type=int, default=10)
    args = parser.parse_args()
    
    run_consensus_pipeline(args.forward, args.backward, args.output, args.max_samples)
