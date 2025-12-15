from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BasePromptTemplate(ABC):
    """
    提示词模板基类。
    所有具体的提示词策略（如 Forward, Backward, Consensus）都应继承此类。
    """
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """返回 System Prompt (通常包含角色设定和输出格式约束)"""
        pass

    @abstractmethod
    def render_user_message(self, data: Dict[str, Any]) -> str:
        """
        根据输入数据渲染 User Message。
        
        Args:
            data: 包含题目信息的字典 (如 decl_name, statement 等)
        """
        pass

    @property
    def stop_tokens(self) -> List[str]:
        """(可选) 定义 LLM 生成的停止词"""
        return []

    def format_lean_statement(self, statement: str) -> str:
        """辅助函数：格式化 Lean 代码块"""
        return f"```lean\n{statement}\n```"

    def format_namespaces(self, namespaces: List[str]) -> str:
        """辅助函数：格式化命名空间"""
        if not namespaces:
            return ""
        return " ".join([f"open {ns}" for ns in namespaces])