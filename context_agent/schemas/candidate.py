from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CandidateItem:
    """候选项。"""

    path: str
    source: str
    reason: str
    content: str = ""
    matched_terms: list[str] = field(default_factory=list)