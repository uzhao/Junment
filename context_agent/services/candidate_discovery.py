from __future__ import annotations

from pathlib import Path

from context_agent.schemas.candidate import CandidateItem
from context_agent.schemas.search_plan import SearchPlan
from context_agent.tools.doc_locator import DocLocator
from context_agent.tools.file_reader import FileReader
from context_agent.tools.grep_search import GrepSearchTool
from context_agent.tools.lsp_client import LSPClient


class CandidateDiscoveryService:
    """根据搜索计划发现候选文件。"""

    def __init__(
        self,
        reader: FileReader,
        grep_tool: GrepSearchTool,
        doc_locator: DocLocator,
        lsp_client: LSPClient,
        max_candidates: int = 12,
    ) -> None:
        self.reader = reader
        self.grep_tool = grep_tool
        self.doc_locator = doc_locator
        self.lsp_client = lsp_client
        self.max_candidates = max_candidates

    def discover(self, plan: SearchPlan, workspace_root: str | Path) -> list[CandidateItem]:
        root = Path(workspace_root)
        results: list[CandidateItem] = []
        seen: set[str] = set()

        for probable_path in plan.probable_paths:
            full_path = root / probable_path
            if not full_path.exists() or not full_path.is_file():
                continue
            rel_path = str(full_path.relative_to(root))
            results.append(
                CandidateItem(
                    path=rel_path,
                    source="explicit_path",
                    reason="Path mentioned in prompt",
                    content=self.reader.read_excerpt(full_path),
                    matched_terms=[probable_path],
                )
            )
            seen.add(rel_path)

        if plan.probable_symbols and len(results) < self.max_candidates:
            remaining_slots = self.max_candidates - len(results)
            lsp_matches = self.lsp_client.find_symbols(
                root,
                plan.probable_symbols,
                limit=max(remaining_slots * 3, remaining_slots),
            )
            lsp_terms_by_path: dict[str, list[str]] = {}
            for match in lsp_matches:
                if match.path in seen:
                    continue
                terms = lsp_terms_by_path.setdefault(match.path, [])
                if match.symbol_name not in terms:
                    terms.append(match.symbol_name)

            for path, matched_terms in lsp_terms_by_path.items():
                file_path = root / path
                if not file_path.exists() or not file_path.is_file():
                    continue
                reason = f"LSP matched symbols: {', '.join(matched_terms[:3])}"
                results.append(
                    CandidateItem(
                        path=path,
                        source="lsp_symbol",
                        reason=reason,
                        content=self.reader.read_excerpt(file_path),
                        matched_terms=matched_terms,
                    )
                )
                seen.add(path)
                if len(results) >= self.max_candidates:
                    return results

        for match in self.grep_tool.search_workspace(root, plan.search_terms, limit=self.max_candidates):
            if match.path in seen:
                continue
            file_path = root / match.path
            results.append(
                CandidateItem(
                    path=match.path,
                    source="grep",
                    reason="Matched search terms",
                    content=self.reader.read_excerpt(file_path),
                    matched_terms=match.matched_terms,
                )
            )
            seen.add(match.path)
            if len(results) >= self.max_candidates:
                return results

        if plan.include_docs:
            remaining_slots = max(self.max_candidates - len(results), 0)
            doc_matches = self.doc_locator.find_documents(
                root,
                search_terms=plan.search_terms,
                probable_paths=plan.probable_paths,
                limit=remaining_slots or self.max_candidates,
            )
            for doc_match in doc_matches:
                if doc_match.path in seen:
                    continue
                file_path = root / doc_match.path
                results.append(
                    CandidateItem(
                        path=doc_match.path,
                        source="doc",
                        reason=doc_match.reason,
                        content=self.reader.read_excerpt(file_path),
                        matched_terms=doc_match.matched_terms,
                    )
                )
                seen.add(doc_match.path)
                if len(results) >= self.max_candidates:
                    break

        return results[: self.max_candidates]