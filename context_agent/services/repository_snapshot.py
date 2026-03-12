from __future__ import annotations

import os
from pathlib import Path

from context_agent.schemas.candidate import RepositorySnapshot

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".tox", ".mypy_cache"}

_CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt"}
_DOC_SUFFIXES = {".md", ".rst", ".txt"}
_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml"}
_ALL_SUFFIXES = _CODE_SUFFIXES | _DOC_SUFFIXES | _CONFIG_SUFFIXES


class RepositorySnapshotService:
    """收集仓库文件树并基于 grep_hints 产生命中文件名列表。"""

    def collect(self, workspace_root: str | Path, grep_hints: list[str] | None = None) -> RepositorySnapshot:
        root = Path(workspace_root)
        file_paths: list[str] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.suffix.lower() not in _ALL_SUFFIXES:
                    continue
                rel_path = str(file_path.relative_to(root))
                file_paths.append(rel_path)

        file_paths.sort()
        file_tree = "\n".join(file_paths)

        grep_matched_files: list[str] = []
        if grep_hints:
            grep_matched_files = self._grep_hints_match(root, file_paths, grep_hints)

        return RepositorySnapshot(file_tree=file_tree, grep_matched_files=grep_matched_files)

    def _grep_hints_match(
        self, root: Path, file_paths: list[str], hints: list[str], max_chars: int = 4000
    ) -> list[str]:
        """对 grep_hints 做轻量 grep，只保留命中文件路径。"""

        lowered_hints = [h.lower() for h in hints if h]
        matched: list[str] = []
        seen: set[str] = set()

        for rel_path in file_paths:
            if rel_path in seen:
                continue
            # 先检查文件名是否命中
            name_lower = rel_path.lower()
            if any(h in name_lower for h in lowered_hints):
                matched.append(rel_path)
                seen.add(rel_path)
                continue
            # 再检查文件内容
            full_path = root / rel_path
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")[:max_chars].lower()
            except OSError:
                continue
            if any(h in content for h in lowered_hints):
                matched.append(rel_path)
                seen.add(rel_path)

        return matched
