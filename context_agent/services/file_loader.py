from __future__ import annotations

from pathlib import Path

from context_agent.schemas.candidate import FileView
from context_agent.schemas.score import LineRange
from context_agent.schemas.search_plan import PlannedFile


class FileLoaderService:
    """读取 planner 选中的文件，并在超长文件场景下生成适合 judge 的裁剪视图。"""

    def __init__(self, max_lines: int = 10000) -> None:
        self.max_lines = max_lines

    def load(self, planned_file: PlannedFile, workspace_root: str | Path) -> FileView:
        """读取单个文件并返回 FileView。"""

        root = Path(workspace_root)
        full_path = root / planned_file.path
        try:
            raw = full_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return FileView(path=planned_file.path, total_lines=0, truncated=False)

        all_lines = raw.splitlines()
        total_lines = len(all_lines)

        if total_lines <= self.max_lines:
            content = self._add_line_numbers(all_lines, offset=1)
            return FileView(
                path=planned_file.path,
                total_lines=total_lines,
                truncated=False,
                retained_ranges=[LineRange(start_line=1, end_line=total_lines)],
                match_terms=planned_file.match_terms,
                content_with_line_numbers=content,
            )

        # 超长文件裁剪
        ranges = self._compute_ranges(all_lines, planned_file.match_terms, total_lines)
        content = self._build_truncated_view(all_lines, ranges)
        return FileView(
            path=planned_file.path,
            total_lines=total_lines,
            truncated=True,
            retained_ranges=ranges,
            match_terms=planned_file.match_terms,
            content_with_line_numbers=content,
        )

    def load_all(self, planned_files: list[PlannedFile], workspace_root: str | Path) -> list[FileView]:
        return [self.load(pf, workspace_root) for pf in planned_files]

    def _compute_ranges(
        self, lines: list[str], match_terms: list[str], total_lines: int
    ) -> list[LineRange]:
        """计算保留的行范围。"""

        hit_lines = self._find_hit_lines(lines, match_terms)

        if not hit_lines:
            return self._fallback_head_tail(total_lines)

        k = len(hit_lines)
        per_hit_budget = max(self.max_lines // k, 20)
        half_window = per_hit_budget // 2

        raw_ranges: list[LineRange] = []
        for hit_line in hit_lines:
            start = max(1, hit_line - half_window)
            end = min(total_lines, hit_line + half_window)
            raw_ranges.append(LineRange(start_line=start, end_line=end))

        merged = self._merge_ranges(raw_ranges)

        # 如果合并后仍超过总预算，按顺序截断
        total_retained = sum(r.end_line - r.start_line + 1 for r in merged)
        if total_retained > self.max_lines:
            merged = self._shrink_ranges(merged, self.max_lines)

        return merged

    def _find_hit_lines(self, lines: list[str], match_terms: list[str]) -> list[int]:
        """返回命中行号（1-based）。"""

        if not match_terms:
            return []
        lowered_terms = [t.lower() for t in match_terms]
        hits: list[int] = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(t in line_lower for t in lowered_terms):
                hits.append(i + 1)  # 1-based
        return hits

    def _fallback_head_tail(self, total_lines: int) -> list[LineRange]:
        """无命中时回退到头尾截断。"""

        head_lines = self.max_lines // 4
        tail_lines = self.max_lines - head_lines

        head_end = min(head_lines, total_lines)
        tail_start = max(total_lines - tail_lines + 1, head_end + 1)

        if tail_start <= head_end:
            return [LineRange(start_line=1, end_line=total_lines)]

        ranges = [LineRange(start_line=1, end_line=head_end)]
        if tail_start <= total_lines:
            ranges.append(LineRange(start_line=tail_start, end_line=total_lines))
        return ranges

    def _merge_ranges(self, ranges: list[LineRange]) -> list[LineRange]:
        """合并重叠或相邻的区间。"""

        if not ranges:
            return []
        sorted_ranges = sorted(ranges, key=lambda r: r.start_line)
        merged = [LineRange(start_line=sorted_ranges[0].start_line, end_line=sorted_ranges[0].end_line)]

        for r in sorted_ranges[1:]:
            last = merged[-1]
            if r.start_line <= last.end_line + 1:
                last.end_line = max(last.end_line, r.end_line)
            else:
                merged.append(LineRange(start_line=r.start_line, end_line=r.end_line))
        return merged

    def _shrink_ranges(self, ranges: list[LineRange], budget: int) -> list[LineRange]:
        """按顺序保留区间，直到预算用完。"""

        result: list[LineRange] = []
        remaining = budget
        for r in ranges:
            size = r.end_line - r.start_line + 1
            if size <= remaining:
                result.append(r)
                remaining -= size
            elif remaining > 0:
                result.append(LineRange(start_line=r.start_line, end_line=r.start_line + remaining - 1))
                break
            else:
                break
        return result

    def _add_line_numbers(self, lines: list[str], offset: int = 1) -> str:
        """给内容加行号。"""

        numbered = [f"{offset + i}| {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)

    def _build_truncated_view(self, lines: list[str], ranges: list[LineRange]) -> str:
        """生成带行号和省略标记的裁剪视图。"""

        parts: list[str] = []
        prev_end = 0

        for r in ranges:
            if prev_end > 0 and r.start_line > prev_end + 1:
                parts.append(f"\n===== omitted lines {prev_end + 1}-{r.start_line - 1} =====\n")

            parts.append(f"===== lines {r.start_line}-{r.end_line} =====")
            segment = lines[r.start_line - 1 : r.end_line]
            numbered = self._add_line_numbers(segment, offset=r.start_line)
            parts.append(numbered)
            prev_end = r.end_line

        return "\n".join(parts)
