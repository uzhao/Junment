from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchPlan:
    """搜索计划。"""

    task_type: str
    prompt_summary: str
    search_terms: list[str] = field(default_factory=list)
    probable_paths: list[str] = field(default_factory=list)
    probable_symbols: list[str] = field(default_factory=list)
    include_docs: bool = False