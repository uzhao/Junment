from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from context_agent.tools.file_reader import FileReader

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
_TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go"}


@dataclass(slots=True)
class GrepMatch:
    path: str
    matched_terms: list[str]


class GrepSearchTool:
    """基于文件系统的轻量搜索。"""

    def __init__(self, reader: FileReader | None = None) -> None:
        self.reader = reader or FileReader()

    def search_workspace(self, workspace_root: str | Path, terms: list[str], limit: int = 10) -> list[GrepMatch]:
        results: list[GrepMatch] = []
        root = Path(workspace_root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS and not name.startswith('.')]
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.suffix.lower() not in _TEXT_SUFFIXES:
                    continue
                matched = self.find_matched_terms(file_path, terms)
                if not self._is_strong_match(file_path, matched):
                    continue
                if not matched:
                    continue
                results.append(GrepMatch(path=str(file_path.relative_to(root)), matched_terms=matched))
        results.sort(key=lambda item: (-len(item.matched_terms), item.path))
        return results[:limit]

    def find_matched_terms(self, path: str | Path, terms: list[str], max_chars: int = 4000) -> list[str]:
        normalized_terms = [term.lower() for term in terms if term]
        file_path = Path(path)
        haystack = f"{file_path.name}\n{self.reader.read_text(file_path, max_chars=max_chars)}".lower()
        return [term for term in normalized_terms if term in haystack]

    def _is_strong_match(self, path: Path, matched_terms: list[str]) -> bool:
        if not matched_terms:
            return False
        if len(matched_terms) >= 2:
            return True
        path_lower = str(path).lower()
        only_term = matched_terms[0]
        return only_term in path_lower or len(only_term) >= 8