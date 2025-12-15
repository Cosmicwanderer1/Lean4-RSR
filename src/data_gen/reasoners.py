import os
import time
import random
import re
from typing import Optional, Tuple, Dict, Any
from openai import OpenAI
from src.common.types import TheoremState, ReasoningStep, ReasoningType
from src.common.rsr_prompts import (
    TEACHER_BACKWARD_PROMPT,
    TEACHER_FORWARD_PROMPT,
    TEACHER_CONSENSUS_PROMPT
)

# -------------------------------------------------------------
# 基类定义
# -------------------------------------------------------------
class Reasoner:
    """推理角色基类 - 极强鲁棒性版本"""
    
    def __init__(
        self, 
        client: OpenAI, 
        model_name: str, 
        name: str, 
        output_tag: str, 
        max_tokens: int = 4096,
        max_retries: int = 5,
        temperature: float = 0.7
    ):
        self.client = client
        self.model_name = model_name
        self.name = name
        self.output_tag = output_tag
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.temperature = temperature
        
        # 动态构建带防护的 System Prompt
        self.system_prompt = self._get_system_prompt()
        
        # 统计面板
        self.stats = {
            'requests': 0,
            'success': 0,
            'failures': 0,
            'truncated': 0,
            'repaired': 0
        }

    def _get_system_prompt(self) -> str:
        raise NotImplementedError

    def _format_user_input(self, theorem: TheoremState, **kwargs) -> str:
        raise NotImplementedError

    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """智能判断是否需要重试"""
        error_str = str(error).lower()
        if "authentication" in error_str or "invalid request" in error_str or "context_length" in error_str:
            return False
        retry_keywords = ["timeout", "connection", "rate limit", "500", "502", "503", "504", "service unavailable"]
        if any(k in error_str for k in retry_keywords):
            return True
        return attempt < self.max_retries

    def _calculate_backoff(self, attempt: int) -> float:
        """计算等待时间"""
        base = 2.0
        cap = 60.0
        delay = min(cap, base * (2 ** attempt))
        return delay * (1 + random.uniform(-0.1, 0.1))

    def run(self, theorem: TheoremState, **kwargs) -> ReasoningStep:
        """执行推理的核心流程"""
        user_content = self._format_user_input(theorem, **kwargs)
        
        # 1. 全局输入保护
        if len(user_content) > 12000:
            if "\n\n" in user_content[:6000]:
                head_cut = user_content[:6000].rfind("\n\n")
                head = user_content[:head_cut]
            else:
                head = user_content[:6000]
            tail = user_content[-4000:] 
            user_content = f"{head}\n\n...[Input Truncated for Length]...\n\n{tail}"
        
        self.stats['requests'] += 1
        
        for attempt in range(self.max_retries):
            try:
                current_temp = max(0.2, self.temperature - (attempt * 0.1))
                
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=current_temp,
                    max_tokens=self.max_tokens,
                    timeout=90,
                    frequency_penalty=0.1,
                    presence_penalty=0.1
                )
                
                raw_output = response.choices[0].message.content.strip()
                finish_reason = response.choices[0].finish_reason
                
                if finish_reason == 'length':
                    self.stats['truncated'] += 1
                    # print(f"[{self.name}] ⚠️ Token limit reached.") # 减少刷屏，只在统计里看
                
                # 2. 提取与自动修复
                extracted_content, info = self._extract_and_repair(raw_output)
                
                if info.get('repaired'):
                    self.stats['repaired'] += 1
                
                # 3. 强力兜底检查
                # 如果提取为空，但尝试次数还没用完，就抛出异常触发重试
                if not extracted_content:
                    if attempt < self.max_retries - 1:
                        # 打印一下 raw_output 的开头，方便调试
                        snippet = raw_output[:50].replace('\n', ' ')
                        raise ValueError(f"Empty extraction result (Raw: {snippet}...)")
                    else:
                        # 最后一次尝试如果还是空，但原文很长，就死马当活马医，直接用原文
                        if len(raw_output) > 100:
                            extracted_content = raw_output
                            info['repaired'] = True
                            print(f"[{self.name}] ⚠️ Force using raw output as fallback.")

                self.stats['success'] += 1
                return ReasoningStep(
                    step_type=ReasoningType(self.name),
                    content=extracted_content,
                    raw_output=raw_output,
                    metadata={
                        'attempt': attempt + 1,
                        'finish_reason': finish_reason,
                        'extraction_info': info
                    }
                )
            
            except Exception as e:
                self.stats['failures'] += 1
                if not self._should_retry(e, attempt):
                    print(f"[{self.name}] ❌ Fatal Error: {e}")
                    break
                
                delay = self._calculate_backoff(attempt)
                print(f"[{self.name}] ⚠️ Error ({str(e)[:50]}...). Retry {attempt+1}/{self.max_retries} in {delay:.1f}s...")
                time.sleep(delay)

        return ReasoningStep(ReasoningType(self.name), "", "")

    def _extract_and_repair(self, text: str) -> Tuple[str, dict]:
        """统一的提取与修复逻辑"""
        info = {'repaired': False, 'truncated': False}
        if not text:
            return "", info
            
        text = text.strip()
        
        # 1. 清理 Markdown 代码块
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n", "", text)
            text = re.sub(r"\n```$", "", text)
            text = text.strip()

        # 2. 尝试精确匹配 <TAG>...</TAG>
        pattern = f"<{self.output_tag}>(.*?)</{self.output_tag}>"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip(), info
            
        # 3. 尝试模糊匹配（修复模式）
        tag_prefix = self.output_tag.split('_')[0] 
        start_pattern = f"<{tag_prefix}"
        start_match = re.search(start_pattern, text, re.IGNORECASE)
        
        if start_match:
            content_start = text.find('>', start_match.start()) + 1
            if content_start == 0: return "", info
                
            end_pattern = f"</{tag_prefix}"
            end_match = re.search(end_pattern, text[content_start:], re.IGNORECASE)
            
            if end_match:
                content_end = content_start + end_match.start()
                info['repaired'] = True
                return text[content_start:content_end].strip(), info
            else:
                info['repaired'] = True
                info['truncated'] = True
                # 强行闭合
                return text[content_start:].strip(), info
        
        # 4. 最后的兜底：如果没标签但有关键词
        keywords = ["Strategy:", "Transitions:", "Steps:", "Plan:", "Analysis:"]
        if any(k in text for k in keywords):
            info['repaired'] = True
            return text, info
            
        # 5. 超级兜底：如果文本够长，且看起来像是在说话，就直接返回
        if len(text) > 100 and not text.startswith("<"):
             info['repaired'] = True
             return text, info

        return "", info

# -------------------------------------------------------------
# 具体角色实现
# -------------------------------------------------------------
class BackwardAnalyst(Reasoner):
    def __init__(self, client, model_name):
        super().__init__(
            client, model_name, "backward", "BACKWARD_THOUGHT", 
            max_tokens=3072,  
            temperature=0.5   
        )

    def _get_system_prompt(self) -> str:
        return TEACHER_BACKWARD_PROMPT + "\n\nIMPORTANT: Output MUST be wrapped in <BACKWARD_THOUGHT> tags. Focus on STRUCTURE."

    def _format_user_input(self, theorem: TheoremState, **kwargs) -> str:
        proof_code = kwargs.get('proof_code', '')
        if len(proof_code) > 4000:
            lines = proof_code.split('\n')
            if len(lines) > 60:
                truncated = '\n'.join(lines[:30] + ["\n...[Truncated]...\n"] + lines[-30:])
            else:
                truncated = proof_code[:4000] + "\n...[Truncated]..."
            proof_code = truncated
        return f"### Theorem:\n{theorem}\n\n### Reference Proof Code:\n{proof_code}"


class ForwardExplorer(Reasoner):
    def __init__(self, client, model_name):
        super().__init__(
            client, model_name, "forward", "FORWARD_THOUGHT", 
            max_tokens=3072, # 【关键修改】从 2048 提升到 3072，防止 Forward 思考太长被截断
            temperature=0.8  
        )

    def _get_system_prompt(self) -> str:
        return TEACHER_FORWARD_PROMPT + "\n\nIMPORTANT: Output MUST be wrapped in <FORWARD_THOUGHT> tags. BE CONCISE."

    def _format_user_input(self, theorem: TheoremState, **kwargs) -> str:
        return f"### Theorem:\n{theorem}"


class ConsensusJudge(Reasoner):
    def __init__(self, client, model_name):
        super().__init__(
            client, model_name, "consensus", "CONSENSUS_THOUGHT", 
            max_tokens=4096, 
            temperature=0.6
        )

    def _get_system_prompt(self) -> str:
        return TEACHER_CONSENSUS_PROMPT + "\n\nIMPORTANT: Analysis in <CONSENSUS_THOUGHT>. Skeleton in <SKELETON>."

    def _format_user_input(self, theorem: TheoremState, **kwargs) -> str:
        b_content = kwargs.get('backward_content', '')
        f_content = kwargs.get('forward_content', '')
        
        def simple_truncate(s, n=2500):
            return s if len(s) <= n else s[:n] + "...[Truncated]"
            
        return f"""### Theorem:
{theorem}

### Backward Analysis:
{simple_truncate(b_content)}

### Forward Exploration:
{simple_truncate(f_content)}"""