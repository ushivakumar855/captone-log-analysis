# utils/metrics.py  —  shared evaluation metrics
# Used by evaluate_model.py and benchmark_pipeline.py — no duplication.

from dataclasses import dataclass, field
from typing import List

@dataclass
class ConfusionMatrix:
    TP: int = 0
    TN: int = 0
    FP: int = 0
    FN: int = 0

    def update(self, actual_evil: int, predicted_evil: bool):
        if actual_evil == 1:
            if predicted_evil: self.TP += 1
            else:              self.FN += 1
        else:
            if predicted_evil: self.FP += 1
            else:              self.TN += 1

    @property
    def total(self):
        return self.TP + self.TN + self.FP + self.FN

    @property
    def precision(self):
        return self.TP / (self.TP + self.FP) if (self.TP + self.FP) else 0.0

    @property
    def recall(self):
        return self.TP / (self.TP + self.FN) if (self.TP + self.FN) else 0.0

    @property
    def f1(self):
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def accuracy(self):
        return (self.TP + self.TN) / self.total if self.total else 0.0

    def summary(self) -> dict:
        return {
            "accuracy":  round(self.accuracy  * 100, 2),
            "precision": round(self.precision * 100, 2),
            "recall":    round(self.recall    * 100, 2),
            "f1":        round(self.f1        * 100, 2),
            "TP": self.TP, "TN": self.TN,
            "FP": self.FP, "FN": self.FN,
        }
