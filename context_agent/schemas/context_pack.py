from __future__ import annotations

from dataclasses import dataclass, field

from context_agent.schemas.score import LineRange


@dataclass(slots=True)
class ContextEntry:
    """最终注入中的一条上下文。"""

    path: str
    score: int
    relation_type: str
    reason: str
    excerpt: str = ""
    spans: list[LineRange] = field(default_factory=list)


@dataclass(slots=True)
class ContextPack:
    """最终注入给 Claude 的上下文包。"""

    task_type: str
    summary: str
    entries: list[ContextEntry] = field(default_factory=list)
    additional_context: str = ""