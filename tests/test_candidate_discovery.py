from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from context_agent.agents.judge import Judge
from context_agent.schemas.candidate import CandidateItem
from context_agent.schemas.search_plan import SearchPlan
from context_agent.services.candidate_discovery import CandidateDiscoveryService
from context_agent.tools.doc_locator import DocLocator
from context_agent.tools.file_reader import FileReader
from context_agent.tools.grep_search import GrepSearchTool
from context_agent.tools.lsp_client import LSPClient, LSPSymbolMatch


class FakeLSPClient(LSPClient):
    def __init__(self, matches: list[LSPSymbolMatch]) -> None:
        super().__init__(warmup_seconds=0.0)
        self.matches = matches

    def find_symbols(
        self,
        workspace_root: str | Path,
        symbols: list[str],
        limit: int = 8,
    ) -> list[LSPSymbolMatch]:
        filtered = [item for item in self.matches if item.symbol_name in symbols]
        return filtered[:limit]


class CandidateDiscoveryServiceTestCase(unittest.TestCase):
    def test_discover_skips_unrelated_markdown_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("项目总览，包含 architecture demo 设计说明。\n", encoding="utf-8")
            (root / "python-mcp-agent-architecture.md").write_text("这里记录 architecture demo 的详细设计。\n", encoding="utf-8")
            (root / "chat.md").write_text("这是聊天记录，与当前设计问题无关。\n", encoding="utf-8")

            service = CandidateDiscoveryService(
                reader=FileReader(),
                grep_tool=GrepSearchTool(),
                doc_locator=DocLocator(),
                lsp_client=LSPClient(),
                max_candidates=10,
            )
            plan = SearchPlan(
                task_type="explain",
                prompt_summary="architecture demo 设计",
                search_terms=["architecture", "demo", "设计"],
                include_docs=True,
            )

            candidates = service.discover(plan, root)
            paths = [item.path for item in candidates]

            self.assertIn("README.md", paths)
            self.assertIn("python-mcp-agent-architecture.md", paths)
            self.assertNotIn("chat.md", paths)

    def test_discover_includes_lsp_symbol_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "planner_impl.py").write_text("class Planner:\n    pass\n", encoding="utf-8")

            service = CandidateDiscoveryService(
                reader=FileReader(),
                grep_tool=GrepSearchTool(),
                doc_locator=DocLocator(),
                lsp_client=FakeLSPClient([
                    LSPSymbolMatch(path="planner_impl.py", symbol_name="Planner", kind="5"),
                    LSPSymbolMatch(path="planner_impl.py", symbol_name="create_plan", kind="12"),
                ]),
                max_candidates=10,
            )
            plan = SearchPlan(
                task_type="explain",
                prompt_summary="Planner 的职责",
                search_terms=["planner"],
                probable_symbols=["Planner", "create_plan"],
            )

            candidates = service.discover(plan, root)

            self.assertEqual(candidates[0].path, "planner_impl.py")
            self.assertEqual(candidates[0].source, "lsp_symbol")
            self.assertEqual(candidates[0].matched_terms, ["Planner", "create_plan"])

    def test_discover_includes_typescript_lsp_symbol_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "planner.ts").write_text("export function createPlan() {}\n", encoding="utf-8")

            service = CandidateDiscoveryService(
                reader=FileReader(),
                grep_tool=GrepSearchTool(),
                doc_locator=DocLocator(),
                lsp_client=FakeLSPClient([
                    LSPSymbolMatch(path="planner.ts", symbol_name="createPlan", kind="12"),
                ]),
                max_candidates=10,
            )
            plan = SearchPlan(
                task_type="explain",
                prompt_summary="createPlan 的职责",
                search_terms=["planner"],
                probable_symbols=["createPlan"],
            )

            candidates = service.discover(plan, root)

            self.assertEqual(candidates[0].path, "planner.ts")
            self.assertEqual(candidates[0].source, "lsp_symbol")
            self.assertEqual(candidates[0].matched_terms, ["createPlan"])


class JudgeTestCase(unittest.TestCase):
    def test_score_candidate_keeps_weak_doc_below_threshold(self) -> None:
        judge = Judge()
        candidate = CandidateItem(
            path="chat.md",
            source="doc",
            reason="document keyword",
            content="这是历史聊天摘录。",
            matched_terms=[],
        )

        score = judge.score_candidate("请分析 architecture demo 的设计", candidate)

        self.assertLess(score.score, 55)

    def test_score_candidate_deprioritizes_test_file_without_test_intent(self) -> None:
        judge = Judge()
        candidate = CandidateItem(
            path="tests/test_search_plan.py",
            source="grep",
            reason="Matched search terms",
            content="prompt = '请分析 src/demo.py 的报错，并结合架构设计说明原因。'",
            matched_terms=["请分析", "设计"],
        )

        score = judge.score_candidate("请分析 python-mcp-agent-architecture.md 的设计", candidate)

        self.assertLess(score.score, 55)


if __name__ == "__main__":
    unittest.main()