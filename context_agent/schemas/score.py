from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CandidateScore:
    """候选评分。"""

    path: str
    score: int
    relation_type: str
    reason: str
    recommended_spans: list[str] = field(default_factory=list)
    source: str = ""