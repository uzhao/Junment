from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LineRange:
    """行范围。"""

    start_line: int
    end_line: int


@dataclass(slots=True)
class JudgeResult:
    """judge 对单个文件的评判结果。"""

    path: str
    score: int
    relation_type: str
    reason: str
    spans: list[LineRange] = field(default_factory=list)
    excerpt: str = ""
    source: str = "planner"
