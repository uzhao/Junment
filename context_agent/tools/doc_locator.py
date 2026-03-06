from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from context_agent.tools.file_reader import FileReader

_DOC_KEYWORDS = ("readme", "architecture", "design", "rfc", "plan", "spec")


@dataclass(slots=True)
class DocMatch:
    path: str
    matched_terms: list[str]
    reason: str


class DocLocator:
    """定位 README 与设计文档。"""

    def __init__(self, reader: FileReader | None = None) -> None:
        self.reader = reader or FileReader()

    def find_documents(
        self,
        workspace_root: str | Path,
        search_terms: list[str] | None = None,
        probable_paths: list[str] | None = None,
        limit: int = 8,
    ) -> list[DocMatch]:
        root = Path(workspace_root)
        results: list[tuple[int, DocMatch]] = []
        nearby_dirs = self._build_nearby_dirs(probable_paths or [])
        normalized_terms = [term.lower() for term in (search_terms or []) if term]
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if not name.startswith('.')]
            for filename in filenames:
                lowered = filename.lower()
                if not lowered.endswith(".md"):
                    continue
                file_path = Path(dirpath) / filename
                rel_path = str(file_path.relative_to(root))
                rel_lower = rel_path.lower()
                matched_terms = self._find_matched_terms(file_path, normalized_terms)
                is_root_readme = rel_lower == "readme.md"
                has_doc_keyword = any(keyword in lowered for keyword in _DOC_KEYWORDS)
                is_nearby = self._is_nearby_doc(rel_path, nearby_dirs)
                if not (is_root_readme or has_doc_keyword or is_nearby or len(matched_terms) >= 2):
                    continue
                score = 0
                if is_root_readme:
                    score += 6
                if has_doc_keyword:
                    score += 4
                if is_nearby:
                    score += 3
                score += len(matched_terms) * 3
                results.append(
                    (
                        score,
                        DocMatch(
                            path=rel_path,
                            matched_terms=matched_terms,
                            reason=self._build_reason(is_root_readme, has_doc_keyword, is_nearby, matched_terms),
                        ),
                    )
                )
        results.sort(key=lambda item: (-item[0], item[1].path))
        return [item[1] for item in results[:limit]]

    def _build_nearby_dirs(self, probable_paths: list[str]) -> set[str]:
        nearby_dirs: set[str] = set()
        for probable_path in probable_paths:
            parent = str(Path(probable_path).parent)
            if parent and parent != ".":
                nearby_dirs.add(parent)
        return nearby_dirs

    def _is_nearby_doc(self, rel_path: str, nearby_dirs: set[str]) -> bool:
        if not nearby_dirs:
            return False
        return str(Path(rel_path).parent) in nearby_dirs

    def _find_matched_terms(self, path: Path, terms: list[str]) -> list[str]:
        haystack = f"{path.name}\n{self.reader.read_text(path, max_chars=4000)}".lower()
        return [term for term in terms if term in haystack]

    def _build_reason(
        self,
        is_root_readme: bool,
        has_doc_keyword: bool,
        is_nearby: bool,
        matched_terms: list[str],
    ) -> str:
        parts: list[str] = []
        if is_root_readme:
            parts.append("root README")
        if has_doc_keyword:
            parts.append("document keyword")
        if is_nearby:
            parts.append("near referenced path")
        if matched_terms:
            parts.append(f"matched terms: {', '.join(matched_terms[:4])}")
        if not parts:
            return "Relevant documentation candidate"
        return "; ".join(parts)