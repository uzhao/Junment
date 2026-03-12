from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PlannedFile:
    """planner 选出的候选文件。"""

    path: str
    priority: int
    reason: str
    match_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchPlan:
    """文件选择计划。"""

    task_type: str
    prompt_summary: str
    selected_files: list[PlannedFile] = field(default_factory=list)
