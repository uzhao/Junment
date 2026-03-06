from __future__ import annotations

from context_agent.schemas.score import CandidateScore


class ScoreSelectionService:
    """阈值过滤、去重和排序。"""

    def __init__(self, threshold: int = 55, top_k: int = 6) -> None:
        self.threshold = threshold
        self.top_k = top_k

    def select(self, scores: list[CandidateScore]) -> list[CandidateScore]:
        best_by_path: dict[str, CandidateScore] = {}
        for score in scores:
            current = best_by_path.get(score.path)
            if current is None or score.score > current.score:
                best_by_path[score.path] = score
        filtered = [item for item in best_by_path.values() if item.score >= self.threshold]
        filtered.sort(key=lambda item: (-item.score, item.path))
        return filtered[: self.top_k]