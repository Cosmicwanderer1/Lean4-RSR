"""
自适应难度阈值校准器

基于历史数据动态调整难度判断的阈值，支持：
1. 记录预测结果和实际结果
2. 根据历史数据自动校准阈值
3. 计算预测准确率并生成报告
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path


@dataclass
class CalibrationRecord:
    """单条校准记录"""
    theorem_name: str
    adjusted_score: float
    predicted_difficulty: str
    actual_difficulty: str  # 通过编译验证或人工标注
    forward_score: int
    backward_score: int
    timestamp: str = ""


class DifficultyCalibrator:
    """
    基于历史数据动态校准难度阈值

    使用方法：
    1. 初始化时加载历史记录
    2. 调用 record() 记录每次预测
    3. 定期调用 calibrate() 更新阈值
    4. 使用 get_thresholds() 获取当前阈值
    """

    def __init__(self, history_file: str = None):
        """
        初始化校准器

        Args:
            history_file: 历史记录文件路径（JSONL 格式）
        """
        # 默认阈值
        self.easy_threshold = 0.75
        self.medium_threshold = 0.50

        # 历史记录
        self.history: List[CalibrationRecord] = []
        self.history_file = history_file

        # 统计信息
        self.stats = {
            'total_records': 0,
            'correct_predictions': 0,
            'last_calibration': None
        }

        # 加载历史数据
        if history_file and os.path.exists(history_file):
            self._load_history(history_file)
            if len(self.history) >= 50:
                self.calibrate()

    def _load_history(self, filepath: str):
        """加载历史记录"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.history.append(CalibrationRecord(**data))
            print(f"[Calibrator] Loaded {len(self.history)} historical records")
        except Exception as e:
            print(f"[Calibrator] Error loading history: {e}")

    def _save_history(self):
        """保存历史记录"""
        if not self.history_file:
            return

        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                for record in self.history:
                    f.write(json.dumps(asdict(record), ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"[Calibrator] Error saving history: {e}")

    def record(
        self,
        theorem_name: str,
        adjusted_score: float,
        predicted_difficulty: str,
        actual_difficulty: str,
        forward_score: int = 0,
        backward_score: int = 0
    ):
        """
        记录一次预测结果

        Args:
            theorem_name: 定理名称
            adjusted_score: 调整后的分数 (0-1)
            predicted_difficulty: 预测的难度 (Easy/Medium/Hard)
            actual_difficulty: 实际难度（通过编译验证或标注）
            forward_score: Forward 评分
            backward_score: Backward 评分
        """
        from datetime import datetime

        record = CalibrationRecord(
            theorem_name=theorem_name,
            adjusted_score=adjusted_score,
            predicted_difficulty=predicted_difficulty.lower().replace(" (inferred)", "").replace(" (original)", ""),
            actual_difficulty=actual_difficulty.lower(),
            forward_score=forward_score,
            backward_score=backward_score,
            timestamp=datetime.now().isoformat()
        )

        self.history.append(record)
        self.stats['total_records'] += 1

        if record.predicted_difficulty == record.actual_difficulty:
            self.stats['correct_predictions'] += 1

        # 自动保存
        if self.history_file and len(self.history) % 10 == 0:
            self._save_history()

        # 定期校准（每 50 条记录）
        if len(self.history) % 50 == 0 and len(self.history) >= 50:
            self.calibrate()

    def calibrate(self) -> Tuple[float, float]:
        """
        根据历史数据校准阈值

        使用分位数方法：
        - Easy 阈值 = Easy 样本分数的 25% 分位数
        - Medium 阈值 = Hard 样本分数的 75% 分位数

        Returns:
            (easy_threshold, medium_threshold)
        """
        if len(self.history) < 50:
            print(f"[Calibrator] Not enough data ({len(self.history)}/50), using defaults")
            return self.easy_threshold, self.medium_threshold

        # 按实际难度分组
        easy_scores = [r.adjusted_score for r in self.history if r.actual_difficulty == 'easy']
        medium_scores = [r.adjusted_score for r in self.history if r.actual_difficulty == 'medium']
        hard_scores = [r.adjusted_score for r in self.history if r.actual_difficulty == 'hard']

        # 计算新阈值
        if easy_scores and hard_scores:
            # 使用分位数避免离群值影响
            easy_scores_sorted = sorted(easy_scores)
            hard_scores_sorted = sorted(hard_scores)

            # Easy 阈值：Easy 样本的下 25% 分位数（保守）
            easy_idx = max(0, int(len(easy_scores_sorted) * 0.25) - 1)
            new_easy_threshold = easy_scores_sorted[easy_idx]

            # Medium 阈值：Hard 样本的上 75% 分位数
            hard_idx = min(len(hard_scores_sorted) - 1, int(len(hard_scores_sorted) * 0.75))
            new_medium_threshold = hard_scores_sorted[hard_idx]

            # 确保 easy > medium
            if new_easy_threshold > new_medium_threshold + 0.1:
                old_easy, old_medium = self.easy_threshold, self.medium_threshold
                self.easy_threshold = new_easy_threshold
                self.medium_threshold = new_medium_threshold

                print(f"[Calibrator] Thresholds updated:")
                print(f"  Easy:   {old_easy:.3f} -> {self.easy_threshold:.3f}")
                print(f"  Medium: {old_medium:.3f} -> {self.medium_threshold:.3f}")
            else:
                print(f"[Calibrator] New thresholds invalid (easy={new_easy_threshold:.3f}, "
                      f"medium={new_medium_threshold:.3f}), keeping defaults")

        from datetime import datetime
        self.stats['last_calibration'] = datetime.now().isoformat()

        return self.easy_threshold, self.medium_threshold

    def get_thresholds(self) -> Tuple[float, float]:
        """获取当前阈值"""
        return self.easy_threshold, self.medium_threshold

    def get_accuracy(self) -> Dict[str, float]:
        """
        计算预测准确率

        Returns:
            {
                'overall': 总体准确率,
                'easy': Easy 准确率,
                'medium': Medium 准确率,
                'hard': Hard 准确率
            }
        """
        if not self.history:
            return {'overall': 0, 'easy': 0, 'medium': 0, 'hard': 0}

        results = {'easy': [0, 0], 'medium': [0, 0], 'hard': [0, 0]}  # [correct, total]

        for record in self.history:
            actual = record.actual_difficulty
            if actual in results:
                results[actual][1] += 1
                if record.predicted_difficulty == actual:
                    results[actual][0] += 1

        return {
            'overall': self.stats['correct_predictions'] / max(self.stats['total_records'], 1),
            'easy': results['easy'][0] / max(results['easy'][1], 1),
            'medium': results['medium'][0] / max(results['medium'][1], 1),
            'hard': results['hard'][0] / max(results['hard'][1], 1)
        }

    def generate_report(self) -> str:
        """生成校准报告"""
        accuracy = self.get_accuracy()

        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║              DIFFICULTY CALIBRATOR REPORT                        ║
╚══════════════════════════════════════════════════════════════════╝

📊 Current Thresholds:
   Easy   >= {self.easy_threshold:.3f}
   Medium >= {self.medium_threshold:.3f}
   Hard   <  {self.medium_threshold:.3f}

📈 Statistics:
   Total Records:       {self.stats['total_records']}
   Correct Predictions: {self.stats['correct_predictions']}
   Last Calibration:    {self.stats['last_calibration'] or 'Never'}

🎯 Accuracy:
   Overall: {accuracy['overall']:.1%}
   Easy:    {accuracy['easy']:.1%}
   Medium:  {accuracy['medium']:.1%}
   Hard:    {accuracy['hard']:.1%}

📉 Score Distribution:
"""
        # 添加分数分布
        if self.history:
            easy_scores = [r.adjusted_score for r in self.history if r.actual_difficulty == 'easy']
            medium_scores = [r.adjusted_score for r in self.history if r.actual_difficulty == 'medium']
            hard_scores = [r.adjusted_score for r in self.history if r.actual_difficulty == 'hard']

            if easy_scores:
                report += f"   Easy:   min={min(easy_scores):.3f}, max={max(easy_scores):.3f}, avg={sum(easy_scores)/len(easy_scores):.3f}\n"
            if medium_scores:
                report += f"   Medium: min={min(medium_scores):.3f}, max={max(medium_scores):.3f}, avg={sum(medium_scores)/len(medium_scores):.3f}\n"
            if hard_scores:
                report += f"   Hard:   min={min(hard_scores):.3f}, max={max(hard_scores):.3f}, avg={sum(hard_scores)/len(hard_scores):.3f}\n"

        return report


# 全局单例（可选）
_global_calibrator: Optional[DifficultyCalibrator] = None


def get_calibrator(history_file: str = None) -> DifficultyCalibrator:
    """获取全局校准器实例"""
    global _global_calibrator
    if _global_calibrator is None:
        _global_calibrator = DifficultyCalibrator(history_file)
    return _global_calibrator
