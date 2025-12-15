"""
增强版共识流水线 - V2
带评分机制的三阶段共识系统

Pipeline:
1. Scoring Judge: 对 Forward 和 Backward 打分
2. Step-by-Step Reasoner: 生成详细推理过程（根据分数加权）
3. Skeleton Generator: 基于推理生成骨架
"""

import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from pathlib import Path
from openai import OpenAI
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm
from ..prompts.consensus_v2 import ScoringJudgeV2, StepByStepReasonerV2, SkeletonGeneratorV2

# 修复 Windows 控制台 Unicode 输出问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


@dataclass
class ScoreResult:
    """评分结果 - 使用不同维度评估 Forward vs Backward"""
    # Forward Planning 评分维度
    forward_strategy_appropriateness: int
    forward_step_coverage: int
    forward_technical_accuracy: int
    forward_guidance_value: int
    forward_total: int
    forward_justification: str

    # Backward Analysis 评分维度
    backward_structural_clarity: int
    backward_transition_accuracy: int
    backward_reasoning_depth: int
    backward_extraction_value: int
    backward_total: int
    backward_justification: str

    priority: str  # "Forward" | "Backward" | "Balanced"
    priority_reason: str
    confidence: str  # "High" | "Medium" | "Low"

    # 一致性检查（新增）
    agreement_level: str = "Medium"  # "High" | "Medium" | "Low"
    key_conflicts: str = ""
    resolution: str = ""


@dataclass
class EnhancedConsensusSample:
    """增强版共识样本"""
    theorem: str
    full_name: str
    
    # Phase 1: Scoring
    score_result: Dict[str, Any]
    forward_weight: float  # 0-100
    backward_weight: float  # 0-100
    
    # Phase 2: Step-by-Step Reasoning
    step_by_step_reasoning: str
    key_insights: List[str]
    
    # Phase 3: Skeleton Generation
    final_skeleton: str
    skeleton_metadata: Dict[str, Any]
    difficulty_level: str  # Easy/Medium/Hard (Original/Inferred)
    generation_mode: str  # Complete Elegant Proof/Structured Roadmap/Detailed Blueprint
    
    # Original sources
    forward_source: Dict[str, Any]
    backward_source: Dict[str, Any]


class EnhancedConsensusJudge:
    """增强版共识裁判 - 三阶段流水线"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat"
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        
        # Initialize prompts
        self.scoring_judge = ScoringJudgeV2()
        self.step_reasoner = StepByStepReasonerV2()
        self.skeleton_generator = SkeletonGeneratorV2()
    
    def _call_api(self, prompt_template, data: Dict[str, Any], temperature: float = 0.3) -> str:
        """调用 DeepSeek API"""
        messages = [
            {"role": "system", "content": prompt_template.system_prompt},
            {"role": "user", "content": prompt_template.render_user_message(data)}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=4096
        )
        
        return response.choices[0].message.content
    
    def _parse_scores(self, raw_text: str) -> ScoreResult:
        """解析评分结果"""
        # Extract forward scores
        forward_match = re.search(
            r'<forward_score>(.*?)</forward_score>',
            raw_text,
            re.DOTALL
        )
        forward_text = forward_match.group(1) if forward_match else ""

        # Extract backward scores
        backward_match = re.search(
            r'<backward_score>(.*?)</backward_score>',
            raw_text,
            re.DOTALL
        )
        backward_text = backward_match.group(1) if backward_match else ""

        # 调试：如果解析失败，打印原始文本片段
        if not forward_text:
            print(f"  [DEBUG] forward_score tag not found!")
            print(f"  [DEBUG] Raw text preview: {raw_text[:500]}...")
        if not backward_text:
            print(f"  [DEBUG] backward_score tag not found!")
            # 尝试更宽松的匹配
            backward_match_loose = re.search(
                r'backward[_\s]?score[:\s]*(.*?)(?=<|$)',
                raw_text,
                re.DOTALL | re.IGNORECASE
            )
            if backward_match_loose:
                backward_text = backward_match_loose.group(1)
                print(f"  [DEBUG] Found backward score with loose match")

        # Extract priority
        priority_match = re.search(
            r'<priority_recommendation>(.*?)</priority_recommendation>',
            raw_text,
            re.DOTALL
        )
        priority_text = priority_match.group(1) if priority_match else ""

        # Helper function to extract score - 更健壮的匹配
        def extract_score(text: str, criterion: str) -> int:
            # 尝试多种格式: "Criterion: 8/10", "Criterion: 8", "Criterion - 8"
            patterns = [
                rf'{criterion}[:\s]+(\d+)\s*/\s*10',  # "Criterion: 8/10"
                rf'{criterion}[:\s]+(\d+)',           # "Criterion: 8"
                rf'{criterion}\s*[-–—]\s*(\d+)',      # "Criterion - 8"
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            return 0

        def extract_total(text: str) -> int:
            # 尝试多种格式: "Total: 32/40", "Total: 32", "**Total**: 32"
            patterns = [
                r'\*?\*?Total\*?\*?[:\s]+(\d+)\s*/\s*\d+',  # "Total: 32/40" 或 "**Total**: 32/40"
                r'\*?\*?Total\*?\*?[:\s]+(\d+)',             # "Total: 32"
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            # 如果还是找不到，尝试计算各项得分之和
            scores = re.findall(r':\s*(\d+)\s*/?\s*10', text)
            if scores:
                total = sum(int(s) for s in scores)
                print(f"  [DEBUG] Total not found, calculated from items: {total}")
                return total
            return 0

        def extract_justification(text: str) -> str:
            match = re.search(r'Justification:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
            return match.group(1).strip() if match else ""
        
        # Extract priority info
        priority = "Balanced"
        if "Forward" in priority_text and "Backward" not in priority_text.split("Priority:")[1].split("\n")[0]:
            priority = "Forward"
        elif "Backward" in priority_text:
            priority = "Backward"
        
        priority_reason = ""
        reason_match = re.search(r'Reason:\s*(.+?)(?:\n|Confidence:)', priority_text, re.IGNORECASE | re.DOTALL)
        if reason_match:
            priority_reason = reason_match.group(1).strip()
        
        confidence = "Medium"
        if "High" in priority_text:
            confidence = "High"
        elif "Low" in priority_text:
            confidence = "Low"

        # 解析一致性检查（新增）
        consistency_match = re.search(
            r'<consistency_check>(.*?)</consistency_check>',
            raw_text,
            re.DOTALL
        )
        consistency_text = consistency_match.group(1) if consistency_match else ""

        agreement_level = "Medium"
        if "Agreement_Level:" in consistency_text:
            if "High" in consistency_text.split("Agreement_Level:")[1].split("\n")[0]:
                agreement_level = "High"
            elif "Low" in consistency_text.split("Agreement_Level:")[1].split("\n")[0]:
                agreement_level = "Low"

        key_conflicts = ""
        conflicts_match = re.search(r'Key_Conflicts:\s*(.+?)(?:\n|Resolution:)', consistency_text, re.IGNORECASE | re.DOTALL)
        if conflicts_match:
            key_conflicts = conflicts_match.group(1).strip()

        resolution = ""
        resolution_match = re.search(r'Resolution:\s*(.+?)(?:\n|$)', consistency_text, re.IGNORECASE | re.DOTALL)
        if resolution_match:
            resolution = resolution_match.group(1).strip()

        return ScoreResult(
            forward_strategy_appropriateness=extract_score(forward_text, "Strategy_Appropriateness"),
            forward_step_coverage=extract_score(forward_text, "Step_Coverage"),
            forward_technical_accuracy=extract_score(forward_text, "Technical_Accuracy"),
            forward_guidance_value=extract_score(forward_text, "Guidance_Value"),
            forward_total=extract_total(forward_text),
            forward_justification=extract_justification(forward_text),

            backward_structural_clarity=extract_score(backward_text, "Structural_Clarity"),
            backward_transition_accuracy=extract_score(backward_text, "Transition_Accuracy"),
            backward_reasoning_depth=extract_score(backward_text, "Reasoning_Depth"),
            backward_extraction_value=extract_score(backward_text, "Extraction_Value"),
            backward_total=extract_total(backward_text),
            backward_justification=extract_justification(backward_text),

            priority=priority,
            priority_reason=priority_reason,
            confidence=confidence,

            # 一致性检查字段
            agreement_level=agreement_level,
            key_conflicts=key_conflicts,
            resolution=resolution
        )
    
    def _calculate_weights(self, score_result: ScoreResult) -> tuple[float, float]:
        """
        增强版权重计算 - 体现 "Forward 质量高更难得" 的原则

        核心理念：
        - Forward 是盲猜（不知道答案），高分更难得，应给予更高权重
        - Backward 看过答案，高分是预期的，不应获得额外优势
        - 用"难度系数"放大 Forward 的贡献

        改进点：
        1. Forward 难度系数：Forward 分数越高，乘数越大（奖励准确预测）
        2. Backward 惩罚系数：Backward 分数高是预期的，不额外奖励
        3. 关键维度加权
        4. 一致性检查（Forward 预测与 Backward 实际吻合时更可信）
        """
        # 1. 基础分数
        f_total = max(score_result.forward_total, 1)
        b_total = max(score_result.backward_total, 1)

        # 2. Forward 难度系数：分数越高，乘数越大（奖励"盲猜准确"）
        # 逻辑：Forward 30分 = 1.25x，Forward 35分 = 1.375x，Forward 40分 = 1.5x
        # 低分时乘数较低（Forward 20分 = 1.0x）
        forward_difficulty_multiplier = 1.0 + max(0, (f_total - 20) / 40)  # 范围 [1.0, 1.5]

        # 3. Backward 预期系数：看过答案，高分是预期的，用较低乘数
        # 逻辑：Backward 即使满分也只有 1.0x，因为"看过答案做对不难"
        backward_expectation_multiplier = 0.85 + (b_total / 40) * 0.15  # 范围 [0.85, 1.0]

        # 4. 计算关键维度得分
        # Forward: Technical_Accuracy 和 Guidance_Value 最重要（预测准确性）
        f_key = (score_result.forward_technical_accuracy * 1.5 +
                 score_result.forward_guidance_value * 1.3 +
                 score_result.forward_strategy_appropriateness +
                 score_result.forward_step_coverage) / 4.8 * 10

        # Backward: Transition_Accuracy 和 Structural_Clarity 最重要
        b_key = (score_result.backward_transition_accuracy * 1.5 +
                 score_result.backward_structural_clarity * 1.3 +
                 score_result.backward_reasoning_depth +
                 score_result.backward_extraction_value) / 4.8 * 10

        # 5. 一致性奖励：Forward 预测与 Backward 分析吻合时，说明 Forward 真的理解了
        # 这时应该更信任 Forward
        score_diff = abs(f_total - b_total)
        if score_diff <= 5:  # 分数很接近，Forward 预测准确
            forward_consistency_bonus = 1.1  # Forward 额外 +10%
            backward_consistency_bonus = 1.0
        elif score_diff <= 10:
            forward_consistency_bonus = 1.05
            backward_consistency_bonus = 1.0
        else:  # 分数差距大，可能 Forward 预测不准
            forward_consistency_bonus = 1.0
            backward_consistency_bonus = 1.0

        # 6. 计算加权分数
        f_weighted = (f_total * 0.6 + f_key * 0.4) * forward_difficulty_multiplier * forward_consistency_bonus
        b_weighted = (b_total * 0.6 + b_key * 0.4) * backward_expectation_multiplier * backward_consistency_bonus

        # 7. 基础权重
        total = f_weighted + b_weighted
        forward_weight = (f_weighted / total) * 100
        backward_weight = (b_weighted / total) * 100

        # 8. Priority 调整（基于裁判判断，但限制幅度）
        if score_result.priority == "Forward":
            boost = 8 if score_result.confidence == "High" else 5
            forward_weight = min(forward_weight + boost, 75)
        elif score_result.priority == "Backward":
            # Backward 优先时，boost 较小（因为看过答案）
            boost = 5 if score_result.confidence == "High" else 3
            backward_weight = min(backward_weight + boost, 65)

        # 9. 归一化
        total = forward_weight + backward_weight
        return round(forward_weight / total * 100, 1), round(backward_weight / total * 100, 1)
    
    def _parse_reasoning(self, raw_text: str) -> tuple[str, List[str]]:
        """解析推理过程"""
        # Extract step-by-step reasoning
        reasoning_match = re.search(
            r'<step_by_step_reasoning>(.*?)</step_by_step_reasoning>',
            raw_text,
            re.DOTALL
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else raw_text
        
        # Extract key insights
        insights = []
        insights_match = re.search(
            r'<key_insights>(.*?)</key_insights>',
            raw_text,
            re.DOTALL
        )
        if insights_match:
            insights_text = insights_match.group(1)
            # Try to extract bullet points or numbered items
            for line in insights_text.split('\n'):
                line = line.strip()
                if line and (line.startswith('-') or line.startswith('•') or re.match(r'\d+\.', line)):
                    insights.append(re.sub(r'^[-•\d\.]\s*', '', line))
        
        return reasoning, insights
    
    def _parse_skeleton(self, raw_text: str) -> tuple[str, Dict[str, Any], str, str]:
        """解析骨架代码,返回(skeleton, metadata, difficulty_level, generation_mode)"""
        # Extract skeleton code
        skeleton_match = re.search(
            r'<proof_skeleton>\s*```lean\s*(.*?)\s*```\s*</proof_skeleton>',
            raw_text,
            re.DOTALL
        )
        if not skeleton_match:
            # Fallback: try without tags
            skeleton_match = re.search(r'```lean\s*(.*?)\s*```', raw_text, re.DOTALL)
        
        skeleton = skeleton_match.group(1).strip() if skeleton_match else ""
        
        # Extract metadata
        metadata = {}
        metadata_match = re.search(
            r'<skeleton_metadata>(.*?)</skeleton_metadata>',
            raw_text,
            re.DOTALL
        )
        if metadata_match:
            metadata_text = metadata_match.group(1)
            # Parse key-value pairs
            for line in metadata_text.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip('- ').strip()
                    value = value.strip()
                    metadata[key] = value
        
        # Extract difficulty_level and generation_mode from metadata or raw text
        difficulty_level = metadata.get('Difficulty', 'Unknown')
        generation_mode = metadata.get('Generation Mode', 'Unknown')
        
        # Try to extract from raw text if not in metadata
        if difficulty_level == 'Unknown':
            diff_match = re.search(r'Difficulty:\s*([^\n|]+)', raw_text)
            if diff_match:
                difficulty_level = diff_match.group(1).strip()
        
        if generation_mode == 'Unknown':
            mode_match = re.search(r'Score:\s*\d+/\d+', raw_text)
            if mode_match:
                # Fallback: infer from metadata
                generation_mode = 'Inferred'
        
        return skeleton, metadata, difficulty_level, generation_mode

    def _validate_skeleton(self, skeleton: str) -> tuple[bool, List[str]]:
        """
        验证骨架质量，检测连续 sorry 等问题

        Returns:
            (is_valid, issues): 是否有效，以及问题列表
        """
        issues = []
        lines = skeleton.split('\n')

        # 检测连续 sorry
        consecutive_sorry_count = 0
        last_was_sorry = False
        last_sorry_line = -1

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 跳过空行和纯注释行
            if not stripped or stripped.startswith('--'):
                continue

            if stripped == 'sorry':
                if last_was_sorry:
                    consecutive_sorry_count += 1
                    if consecutive_sorry_count == 1:  # 第一次检测到连续
                        issues.append(
                            f"Consecutive sorry at lines {last_sorry_line + 1} and {i + 1} "
                            f"(no guidance between them)"
                        )
                last_was_sorry = True
                last_sorry_line = i
            else:
                last_was_sorry = False

        # 检测 sorry 前是否有指导注释
        sorry_without_guidance = []
        for i, line in enumerate(lines):
            if line.strip() == 'sorry':
                # 检查前面的行是否有指导性注释
                has_guidance = False
                for j in range(max(0, i - 5), i):  # 检查前5行
                    prev_line = lines[j].strip()
                    if prev_line.startswith('--') and len(prev_line) > 10:
                        # 有一定长度的注释算作指导
                        has_guidance = True
                        break
                    elif prev_line and not prev_line.startswith('--') and prev_line != 'sorry':
                        # 有实际代码也算
                        has_guidance = True
                        break

                if not has_guidance:
                    sorry_without_guidance.append(i + 1)

        if sorry_without_guidance:
            issues.append(
                f"Sorry without guidance at lines: {sorry_without_guidance}"
            )

        # 检测 sorry 数量
        sorry_count = skeleton.count('sorry')
        if sorry_count > 10:
            issues.append(f"Too many sorry ({sorry_count}), may indicate poor structure")

        is_valid = len(issues) == 0
        return is_valid, issues

    def judge_consensus(
        self,
        forward_sample: Dict[str, Any],
        backward_sample: Dict[str, Any]
    ) -> EnhancedConsensusSample:
        """
        三阶段共识判断
        
        Stage 1: Scoring - 评分
        Stage 2: Reasoning - 生成逐步推理
        Stage 3: Skeleton - 生成骨架
        """
        # 修正：从pipeline输出获取decl_name字段
        full_name = forward_sample.get('decl_name', '') or backward_sample.get('decl_name', 'unknown')
        print(f"\n{'='*60}")
        print(f"Processing: {full_name}")
        print(f"{'='*60}")
        
        # 提取原始难度标注(如果存在)
        original_difficulty = forward_sample.get('difficulty', None)
        if original_difficulty:
            print(f"  Original Difficulty: {original_difficulty}")
        
        # ========== Stage 1: Scoring ==========
        print("\n[Stage 1/3] Scoring Forward and Backward...")
        
        # Extract backward_analysis data safely
        backward_analysis = backward_sample.get('backward_analysis', {})
        key_transitions = backward_analysis.get('key_transitions', [])
        transitions_str = '\n'.join(key_transitions) if isinstance(key_transitions, list) else str(key_transitions)
        
        # 提取完整的定理声明（包括类型签名）
        # state 包含完整的类型上下文，是理解定理的关键
        theorem_statement = forward_sample.get('statement', '') or backward_sample.get('statement', '')
        state_context = forward_sample.get('state', '') or backward_sample.get('state', '')
        
        # 提取分离的context和goal
        context = forward_sample.get('context', '') or backward_sample.get('context', '')
        goal = forward_sample.get('goal', '') or backward_sample.get('goal', '')
        
        # 如果没有分离字段，从state解析
        if not context or not goal:
            if '⊢' in state_context:
                parts = state_context.split('⊢', 1)
                context = parts[0].strip()
                goal = parts[1].strip()

        # 如果 theorem 不完整，尝试从 goal 中提取目标
        if goal and theorem_statement.endswith(':='):
            # 补全定理声明
            theorem_statement = theorem_statement.rstrip(':=').strip() + ' : ' + goal + ' :='

        scoring_data = {
            'decl_name': full_name,
            'full_name': full_name,
            'statement': theorem_statement,  # 新增：完整定理声明
            'state': state_context,  # 新增：类型上下文
            'context': context,  # 分离的上下文
            'goal': goal,  # 分离的目标
            'forward_type': forward_sample.get('problem_type', ''),
            'forward_strategy': forward_sample.get('proof_strategy', ''),
            'backward_structure': backward_analysis.get('proof_structure', ''),
            'backward_transitions': transitions_str,
            'backward_reasoning': backward_analysis.get('reasoning_chain', '')
        }

        # 调试：检查输入数据是否完整
        if not scoring_data['backward_structure']:
            print(f"  [WARNING] backward_structure is empty!")
        if not scoring_data['backward_reasoning']:
            print(f"  [WARNING] backward_reasoning is empty!")

        score_raw = self._call_api(self.scoring_judge, scoring_data, temperature=0.2)
        score_result = self._parse_scores(score_raw)
        forward_weight, backward_weight = self._calculate_weights(score_result)

        # 调试：如果分数异常，打印更多信息
        if score_result.backward_total == 0:
            print(f"  [WARNING] Backward total is 0! Check API response format.")
            print(f"  [DEBUG] API Response (first 1000 chars):")
            print(f"  {score_raw[:1000]}...")
        
        print(f"  Forward:  {score_result.forward_total}/40  (Weight: {forward_weight}%)")
        print(f"  Backward: {score_result.backward_total}/40 (Weight: {backward_weight}%)")
        print(f"  Priority: {score_result.priority} ({score_result.confidence} confidence)")
        print(f"  Agreement: {score_result.agreement_level}" +
              (f" | Conflicts: {score_result.key_conflicts[:50]}..." if score_result.key_conflicts else ""))
        
        # ========== Stage 2: Step-by-Step Reasoning ==========
        print("\n[Stage 2/3] Generating Step-by-Step Reasoning...")
        reasoning_data = {
            'decl_name': full_name,
            'full_name': full_name,
            'statement': theorem_statement,  # 使用补全后的定理声明
            'state': state_context,  # 类型上下文
            'context': context,  # 分离的上下文
            'goal': goal,  # 分离的目标
            'priority': score_result.priority,
            'confidence': score_result.confidence,
            'forward_score': score_result.forward_total,
            'backward_score': score_result.backward_total,
            'forward_weight': forward_weight,
            'backward_weight': backward_weight,
            'forward_strategy': forward_sample.get('proof_strategy', ''),
            'backward_structure': backward_analysis.get('proof_structure', ''),
            'backward_reasoning': backward_analysis.get('reasoning_chain', '')
        }
        
        reasoning_raw = self._call_api(self.step_reasoner, reasoning_data, temperature=0.5)
        step_by_step, key_insights = self._parse_reasoning(reasoning_raw)
        
        print(f"  Generated {len(step_by_step.split('Step'))-1} reasoning steps")
        print(f"  Extracted {len(key_insights)} key insights")
        
        # ========== Stage 3: Skeleton Generation ==========
        print("\n[Stage 3/3] Generating Proof Skeleton...")
        skeleton_data = {
            'statement': theorem_statement,  # 使用补全后的定理声明
            'state': state_context,  # 类型上下文（用于提取完整签名）
            'context': context,  # 分离的上下文
            'goal': goal,  # 分离的目标
            'step_by_step_reasoning': step_by_step,
            'forward_score': score_result.forward_total,
            'backward_score': score_result.backward_total,
            'original_difficulty': original_difficulty  # 传递原始难度
        }
        
        skeleton_raw = self._call_api(self.skeleton_generator, skeleton_data, temperature=0.3)
        final_skeleton, skeleton_metadata, difficulty_level, generation_mode = self._parse_skeleton(skeleton_raw)
        
        print(f"  Skeleton generated ({len(final_skeleton)} chars)")
        print(f"  Difficulty: {difficulty_level} | Mode: {generation_mode}")
        print(f"  Metadata: {skeleton_metadata}")

        # ========== Validate Skeleton ==========
        is_valid, validation_issues = self._validate_skeleton(final_skeleton)
        if not is_valid:
            print(f"  [WARNING] Skeleton validation issues:")
            for issue in validation_issues:
                print(f"    - {issue}")
        else:
            print(f"  [OK] Skeleton validation passed")

        # 将验证结果添加到 metadata
        skeleton_metadata['validation_passed'] = is_valid
        skeleton_metadata['validation_issues'] = validation_issues

        # ========== Package Result ==========
        return EnhancedConsensusSample(
            theorem=theorem_statement,  # 使用提取的statement字段
            full_name=full_name,
            
            score_result=asdict(score_result),
            forward_weight=forward_weight,
            backward_weight=backward_weight,
            
            step_by_step_reasoning=step_by_step,
            key_insights=key_insights,
            
            final_skeleton=final_skeleton,
            skeleton_metadata=skeleton_metadata,
            difficulty_level=difficulty_level,
            generation_mode=generation_mode,
            
            forward_source=forward_sample,
            backward_source=backward_sample
        )


def run_enhanced_consensus_pipeline(
    forward_file: str,
    backward_file: str,
    output_file: str,
    api_key: str,
    max_samples: Optional[int] = None,
    resume: bool = True,
    max_workers: int = 8
):
    """
    运行增强版共识流水线（并行版本）
    
    Args:
        forward_file: Phase 1 输出文件
        backward_file: Phase 2 输出文件
        output_file: 输出文件路径
        api_key: DeepSeek API Key
        max_samples: 最大处理样本数
        resume: 是否支持断点续传
        max_workers: 并发线程数（默认8）
    """
    print("="*80)
    print("Enhanced Consensus Pipeline V2 - With Parallel Processing")
    print("="*80)
    
    # Load data
    print(f"\nLoading forward samples from: {forward_file}")
    with open(forward_file, 'r', encoding='utf-8') as f:
        forward_samples = [json.loads(line) for line in f]
    
    print(f"Loading backward samples from: {backward_file}")
    with open(backward_file, 'r', encoding='utf-8') as f:
        backward_samples = [json.loads(line) for line in f]
    
    # Create ID mappings (use decl_name which is the actual field name)
    forward_map = {s['decl_name']: s for s in forward_samples}
    backward_map = {s['decl_name']: s for s in backward_samples}
    
    # Find intersection
    common_ids = set(forward_map.keys()) & set(backward_map.keys())
    print(f"\nFound {len(common_ids)} theorems with both Forward and Backward analysis")
    
    if max_samples:
        common_ids = list(common_ids)[:max_samples]
        print(f"Processing first {max_samples} samples")
    else:
        common_ids = list(common_ids)
    
    # Resume support
    processed_ids = set()
    if resume and os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            for line in f:
                sample = json.loads(line)
                processed_ids.add(sample['full_name'])
        print(f"Resuming: {len(processed_ids)} samples already processed")
    
    # Filter out processed samples
    samples_to_process = [sid for sid in common_ids if sid not in processed_ids]
    
    if not samples_to_process:
        print("\nAll samples already processed!")
        return
    
    print(f"\nProcessing {len(samples_to_process)} samples with {max_workers} workers...")
    
    # Initialize judge (thread-safe)
    judge = EnhancedConsensusJudge(api_key=api_key)
    
    # Create output directory
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Thread-safe file writing
    write_lock = threading.Lock()
    success_count = 0
    error_count = 0
    
    def process_sample(sample_id: str, max_retries: int = 2) -> Optional[Dict[str, Any]]:
        """处理单个样本（线程安全，带重试）"""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                forward = forward_map[sample_id]
                backward = backward_map[sample_id]

                result = judge.judge_consensus(forward, backward)
                return asdict(result)

            except Exception as e:
                last_error = e
                import traceback
                print(f"\n[ERROR] Error processing {sample_id} (attempt {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    print(f"  Retrying...")
                    import time
                    time.sleep(2 ** attempt)  # 指数退避: 1s, 2s
                else:
                    print(f"  Full traceback:")
                    traceback.print_exc()

        return None
    
    # Parallel processing with progress bar
    with open(output_file, 'a' if resume else 'w', encoding='utf-8') as f_out:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_id = {
                executor.submit(process_sample, sample_id): sample_id 
                for sample_id in samples_to_process
            }
            
            # Process completed tasks with progress bar
            with tqdm(total=len(samples_to_process), desc="Processing", unit="sample") as pbar:
                for future in as_completed(future_to_id):
                    sample_id = future_to_id[future]
                    result = future.result()
                    
                    if result:
                        # Thread-safe write
                        with write_lock:
                            f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
                            f_out.flush()
                            success_count += 1
                    else:
                        error_count += 1
                    
                    pbar.update(1)
                    pbar.set_postfix(success=success_count, errors=error_count)
    
    print("\n" + "="*80)
    print("Pipeline Complete!")
    print(f"Success: {success_count} | Errors: {error_count}")
    print(f"Output saved to: {output_file}")
    print("="*80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Consensus Pipeline V2")
    parser.add_argument(
        '--forward-file',
        type=str,
        default='data/step1_forward/forward_planning.jsonl',
        help='Path to Forward Planning results'
    )
    parser.add_argument(
        '--backward-file',
        type=str,
        default='data/step2_backward/backward_analysis.jsonl',
        help='Path to Backward Analysis results'
    )
    parser.add_argument(
        '--output-file',
        type=str,
        default='data/step3_consensus_v2/enhanced_consensus.jsonl',
        help='Output file path'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        required=True,
        help='DeepSeek API Key'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='Maximum number of samples to process'
    )
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Disable resume from existing output'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=8,
        help='Number of parallel workers (default: 8)'
    )
    
    args = parser.parse_args()
    
    run_enhanced_consensus_pipeline(
        forward_file=args.forward_file,
        backward_file=args.backward_file,
        output_file=args.output_file,
        api_key=args.api_key,
        max_samples=args.max_samples,
        resume=not args.no_resume,
        max_workers=args.max_workers
    )
