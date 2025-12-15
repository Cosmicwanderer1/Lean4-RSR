import yaml
import os
import re
import concurrent.futures
from typing import Optional, Dict, Any, Tuple
from openai import OpenAI
from src.common.types import TheoremState
from src.data_gen.reasoners import BackwardAnalyst, ForwardExplorer, ConsensusJudge

class ProofSynthesisPipeline:
    """
    证明合成流水线 - 调度层
    职责：并行调度 -> 结果校验 -> 骨架提取与清洗
    """
    
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r", encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.client = OpenAI(
            api_key=os.getenv("TEACHER_API_KEY"),
            base_url=self.config["model"]["teacher_api_base"]
        )
        self.model_name = self.config["model"]["teacher_model_name"]

        # 初始化推理器
        # 注意：具体的提取和修复逻辑已封装在 Reasoner 类中
        self.backward_analyst = BackwardAnalyst(self.client, self.model_name)
        self.forward_explorer = ForwardExplorer(self.client, self.model_name)
        self.consensus_judge = ConsensusJudge(self.client, self.model_name)
        
        # 统计信息
        self.stats = {
            'total': 0,
            'success': 0,
            'skipped_backward': 0,
            'skipped_forward': 0,
            'skipped_consensus': 0,
            'skipped_skeleton': 0
        }

    def _extract_skeleton(self, text: str) -> str:
        """
        专门从 Consensus 输出中提取 Skeleton
        (ConsensusJudge 的 run 方法主要提取 Thought，这里我们需要 Raw Output 里的 Code)
        """
        if not text:
            return ""
        
        # 1. 优先尝试标准标签
        match = re.search(r"<SKELETON>(.*?)</SKELETON>", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
        # 2. 尝试 Markdown 代码块 (容错)
        match = re.search(r"```lean\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
        # 3. 尝试直接匹配 theorem ... := by (兜底)
        match = re.search(r"(theorem\s+[\s\S]*?:=[\s\S]*?)(?=\n\s*(?:theorem|lemma|def|#|$))", text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        return ""

    def _clean_skeleton(self, skeleton: str) -> str:
        """
        清洗骨架代码：保留结构性注释，移除废话
        """
        if not skeleton:
            return ""
        
        lines = skeleton.split('\n')
        cleaned_lines = []
        
        for line in lines:
            stripped = line.strip()
            # 移除普通注释，但保留我们约定的结构化注释
            if stripped.startswith('--'):
                # 保留 Fact/TODO/Note/uses 等关键信息
                if any(k in stripped for k in ['Fact:', 'TODO:', 'Note:', 'uses:', 'sura']):
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
        
        # 移除多余空行
        result = '\n'.join(cleaned_lines)
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        return result.strip()

    def _debug_skip(self, stage: str, reason: str, raw_output: str = ""):
        """记录跳过原因"""
        print(f"⚠️ Skipping [{stage}]: {reason}")
        if raw_output:
            snippet = raw_output[-100:].replace('\n', ' ')
            print(f"   [Tail]: ...{snippet}")
        
        key = f'skipped_{stage}'
        if key in self.stats:
            self.stats[key] += 1

    def process_single_theorem(self, theorem_str: str, proof_code: str) -> Optional[Dict[str, Any]]:
        """
        处理单个定理的主流程
        """
        self.stats['total'] += 1
        theorem_state = TheoremState(goal=theorem_str)
        
        # ---------------------------------------------------------
        # 1. 并行执行 Backward 和 Forward
        # ---------------------------------------------------------
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_back = executor.submit(self.backward_analyst.run, theorem_state, proof_code=proof_code)
                future_fwd = executor.submit(self.forward_explorer.run, theorem_state)
                
                backward_step = future_back.result()
                forward_step = future_fwd.result()
        except Exception as e:
            print(f"❌ Pipeline Error: {e}")
            return None

        # ---------------------------------------------------------
        # 2. 校验中间结果
        # ---------------------------------------------------------
        # Backward 校验
        if not backward_step.content:
            self._debug_skip('backward', "Content empty (Extraction failed)", backward_step.raw_output)
            return None
        # 双重保险：检查是否发生严重截断（Raw Tag 泄露）
        # 如果 reasoners.py 修复成功，content 里不应有标签。如果有，说明修复失败。
        if "<BACKWARD" in backward_step.content:
            self._debug_skip('backward', "Raw tag leak (Truncated)", backward_step.raw_output)
            return None

        # Forward 校验
        if not forward_step.content:
            self._debug_skip('forward', "Content empty", forward_step.raw_output)
            return None
        if "<FORWARD" in forward_step.content:
            self._debug_skip('forward', "Raw tag leak (Truncated)", forward_step.raw_output)
            return None

        # ---------------------------------------------------------
        # 3. 执行 Consensus (合成)
        # ---------------------------------------------------------
        consensus_step = self.consensus_judge.run(
            theorem_state,
            backward_content=backward_step.content,
            forward_content=forward_step.content
        )

        if not consensus_step.content:
            self._debug_skip('consensus', "Content empty", consensus_step.raw_output)
            return None

        # ---------------------------------------------------------
        # 4. 提取与清洗骨架 (Skeleton)
        # ---------------------------------------------------------
        # 从 raw_output 中提取，因为 content 只包含 <CONSENSUS_THOUGHT>
        raw_skeleton = self._extract_skeleton(consensus_step.raw_output)
        
        if not raw_skeleton:
            self._debug_skip('consensus', "No <SKELETON> found", consensus_step.raw_output)
            self.stats['skipped_skeleton'] += 1
            return None

        final_skeleton = self._clean_skeleton(raw_skeleton)
        
        # 最后的质量守门：骨架不能太短
        if len(final_skeleton) < 20:
            self._debug_skip('skeleton', "Skeleton too short/empty")
            self.stats['skipped_skeleton'] += 1
            return None

        # ---------------------------------------------------------
        # 5. 成功返回
        # ---------------------------------------------------------
        self.stats['success'] += 1
        
        # 打印一些元数据供调试（可选）
        b_info = backward_step.metadata.get('extraction_info', {})
        f_info = forward_step.metadata.get('extraction_info', {})
        if b_info.get('repaired') or f_info.get('repaired'):
            print(f"   [Info] Auto-repaired truncated input.")

        return {
            "input": theorem_str,
            "target": consensus_step.raw_output, # 保留包含 Thought 和 Skeleton 的完整输出用于训练
            "metadata": {
                "backward_thought": backward_step.content,
                "forward_thought": forward_step.content,
                # 记录是否经过了自动修复，方便后续分析数据质量
                "is_repaired": b_info.get('repaired') or f_info.get('repaired')
            }
        }

    def print_stats(self):
        """打印统计摘要"""
        print("\n=== Pipeline Statistics ===")
        print(f"Total Processed:   {self.stats['total']}")
        print(f"Success Generated: {self.stats['success']}")
        print(f"Skipped (Backward): {self.stats['skipped_backward']}")
        print(f"Skipped (Forward):  {self.stats['skipped_forward']}")
        print(f"Skipped (Consensus):{self.stats['skipped_consensus']}")
        print(f"Skipped (Skeleton): {self.stats['skipped_skeleton']}")
        print("===========================\n")