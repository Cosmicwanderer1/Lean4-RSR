from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

class DeductionType(str, Enum):
    TYPE_INFERENCE = "type_inference"
    DEFINITION_UNFOLD = "definition_unfold"
    LEMMA_APPLICATION = "lemma_application"
    SET_THEORY = "set_theory"
    ALGEBRAIC = "algebraic"
    LOGICAL = "logical"

@dataclass
class Hypothesis:
    name: str
    type: str
    meaning: str
    is_premise: bool = True
    
    def to_dict(self) -> Dict:
        return self.__dict__

@dataclass
class Definition:
    concept: str
    unfolding: str
    properties: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return self.__dict__

@dataclass
class LemmaSuggestion:
    name: str
    reason: str
    confidence: float
    applicability: str
    category: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return self.__dict__

@dataclass
class Deduction:
    statement: str
    proof: str
    type: DeductionType
    confidence: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            "statement": self.statement,
            "proof": self.proof,
            "type": self.type.value,
            "confidence": self.confidence
        }

@dataclass
class ForwardAnalysis:
    """正向分析的最终产物容器"""
    hypotheses: List[Hypothesis]
    definitions: List[Definition]
    lemmas: List[LemmaSuggestion]
    deductions: List[Deduction]
    raw_json: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "definitions": [d.to_dict() for d in self.definitions],
            "lemmas": [l.to_dict() for l in self.lemmas],
            "deductions": [d.to_dict() for d in self.deductions]
        }