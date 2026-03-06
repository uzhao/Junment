from __future__ import annotations

from pathlib import Path


class FileReader:
    """读取文本文件和片段。"""

    def __init__(self, max_excerpt_lines: int = 60) -> None:
        self.max_excerpt_lines = max_excerpt_lines

    def read_text(self, path: str | Path, max_chars: int = 4000) -> str:
        file_path = Path(path)
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars]

    def read_excerpt(self, path: str | Path, max_lines: int | None = None) -> str:
        file_path = Path(path)
        limit = max_lines or self.max_excerpt_lines
        text = self.read_text(file_path, max_chars=12000)
        lines = text.splitlines()
        return "\n".join(lines[:limit])