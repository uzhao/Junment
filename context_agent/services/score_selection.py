from __future__ import annotations

from context_agent.schemas.score import JudgeResult


class ScoreSelectionService:
    """阈值过滤、去重和排序。"""

    def __init__(self, threshold: int = 55, top_k: int = 6) -> None:
        self.threshold = threshold
        self.top_k = top_k

    def select(self, results: list[JudgeResult]) -> list[JudgeResult]:
        best_by_path: dict[str, JudgeResult] = {}
        for result in results:
            current = best_by_path.get(result.path)
            if current is None or result.score > current.score:
                best_by_path[result.path] = result
        filtered = [item for item in best_by_path.values() if item.score >= self.threshold]
        filtered.sort(key=lambda item: (-item.score, item.path))
        return filtered[: self.top_k]
