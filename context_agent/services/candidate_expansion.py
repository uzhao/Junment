from __future__ import annotations

from context_agent.schemas.candidate import CandidateItem
from context_agent.schemas.score import CandidateScore


class CandidateExpansionService:
    """高分候选扩展占位。"""

    def expand(
        self,
        scores: list[CandidateScore],
        candidates: list[CandidateItem],
    ) -> list[CandidateItem]:
        """第一版先保持空实现，后续只对高分项做有限扩展。"""

        _ = scores
        return candidates