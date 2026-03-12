from __future__ import annotations

from dataclasses import dataclass, field

from context_agent.schemas.score import LineRange


@dataclass(slots=True)
class RepositorySnapshot:
    """仓库快照。"""

    file_tree: str
    grep_matched_files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileView:
    """送入 judge 的文件视图。"""

    path: str
    total_lines: int
    truncated: bool
    retained_ranges: list[LineRange] = field(default_factory=list)
    match_terms: list[str] = field(default_factory=list)
    content_with_line_numbers: str = ""
