from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_agent.tools.lsp_client import LSPBackend, LSPClient, LSPSymbolMatch


class FakeMultiBackendLSPClient(LSPClient):
    def __init__(self, backend_results: dict[str, list[LSPSymbolMatch]]) -> None:
        super().__init__(warmup_seconds=0.0)
        self.backend_results = backend_results

    def _resolve_backends(self, workspace_root: Path) -> list[LSPBackend]:
        _ = workspace_root
        return [LSPBackend(name=name, command=[name, "--stdio"]) for name in self.backend_results]

    def _find_symbols_from_backend(
        self,
        workspace_root: Path,
        symbols: list[str],
        backend: LSPBackend,
        limit: int,
    ) -> list[LSPSymbolMatch]:
        _ = workspace_root
        results: list[LSPSymbolMatch] = []
        for item in self.backend_results.get(backend.name, []):
            if item.symbol_name not in symbols:
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results


class LSPClientTestCase(unittest.TestCase):
    def test_find_symbols_aggregates_multiple_backends(self) -> None:
        client = FakeMultiBackendLSPClient(
            {
                "python": [
                    LSPSymbolMatch(path="planner.py", symbol_name="Planner", kind="5"),
                    LSPSymbolMatch(path="shared.py", symbol_name="SharedThing", kind="5"),
                ],
                "typescript": [
                    LSPSymbolMatch(path="planner.ts", symbol_name="createPlan", kind="12"),
                    LSPSymbolMatch(path="shared.py", symbol_name="SharedThing", kind="5"),
                ],
            }
        )

        matches = client.find_symbols(Path("/tmp/workspace"), ["Planner", "createPlan", "SharedThing"], limit=5)

        self.assertEqual(
            matches,
            [
                LSPSymbolMatch(path="planner.py", symbol_name="Planner", kind="5"),
                LSPSymbolMatch(path="shared.py", symbol_name="SharedThing", kind="5"),
                LSPSymbolMatch(path="planner.ts", symbol_name="createPlan", kind="12"),
            ],
        )

    def test_resolve_backends_supports_workspace_local_typescript_server(self) -> None:
        client = LSPClient(warmup_seconds=0.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            typescript_server = root / "node_modules" / ".bin" / "typescript-language-server"
            typescript_server.parent.mkdir(parents=True)
            typescript_server.write_text("", encoding="utf-8")

            def fake_which(name: str) -> str | None:
                if name == "basedpyright-langserver":
                    return "/usr/bin/basedpyright-langserver"
                return None

            with patch("context_agent.tools.lsp_client.shutil.which", side_effect=fake_which):
                backends = client._resolve_backends(root)

        self.assertEqual(
            backends,
            [
                LSPBackend(name="python", command=["/usr/bin/basedpyright-langserver", "--stdio"]),
                LSPBackend(name="typescript", command=[str(typescript_server), "--stdio"]),
            ],
        )


if __name__ == "__main__":
    unittest.main()