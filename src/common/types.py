# -------------------------------------------------------------
# 核心数据结构定义
# -------------------------------------------------------------
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

class ReasoningType(Enum):
    BACKWARD = "backward"
    FORWARD = "forward"
    CONSENSUS = "consensus"

@dataclass
class TheoremState:
    """封装定理状态"""
    hypothesis: str = "" # 虽然 Mathlib 数据可能没明确拆分，这里保留字段
    goal: str = ""       # 原始定理声明字符串
    metadata: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        # 如果只有 goal (theorem statement)，直接返回
        if not self.hypothesis:
            return self.goal
        return f"Hypothesis: {self.hypothesis}\nGoal: {self.goal}"

@dataclass
class ReasoningStep:
    """结构化的推理输出"""
    step_type: ReasoningType
    content: str
    raw_output: str  # 保留原始 LLM 输出以备查验
    
    # 【修复】新增 metadata 字段，用于存储重试次数、截断标记等调试信息
    # 使用 field(default_factory=dict) 确保默认值是一个空字典，而不是 None
    metadata: Dict[str, Any] = field(default_factory=dict)