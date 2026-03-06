from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from context_agent.app import build_app
from context_agent.config import AppConfig
from context_agent.schemas.hook_io import HookInput
from context_agent.workflows.build_context import build_context


class _FakeGate:
    def __init__(self, need_context: bool, reason: str = "") -> None:
        self.need_context = need_context
        self.reason = reason

    async def decide(self, prompt: str):
        _ = prompt
        return type("GateDecision", (), {"need_context": self.need_context, "reason": self.reason})()


class BuildContextWorkflowTestCase(unittest.TestCase):
    def _enabled_config(self) -> AppConfig:
        return AppConfig(
            llm_base_url="https://example.com/v1",
            llm_api_key="test-key",
            default_model="test-model",
        )

    def test_build_context_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.py").write_text(
                "def run_demo():\n    return 'architecture demo'\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "# Demo\n\n这里描述 architecture demo 的背景。\n",
                encoding="utf-8",
            )

            hook_input = HookInput(
                prompt="请结合 architecture demo 说明 sample.py 的实现。",
                cwd=str(root),
            )
            app = build_app(root, self._enabled_config())
            app.gate = _FakeGate(True, "need context")

            pack = asyncio.run(build_context(hook_input, app))

            self.assertIn("sample.py", pack.additional_context)
            self.assertIn("README.md", pack.additional_context)
            self.assertGreaterEqual(len(pack.entries), 2)

    def test_build_context_returns_empty_when_gate_blocks_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.py").write_text("def run_demo():\n    return 'ok'\n", encoding="utf-8")

            hook_input = HookInput(prompt="commit", cwd=str(root))
            app = build_app(root, self._enabled_config())
            app.gate = _FakeGate(False, "这是简短操作指令，不需要额外仓库上下文。")

            pack = asyncio.run(build_context(hook_input, app))

            self.assertEqual(pack.additional_context, "")
            self.assertEqual(pack.summary, "这是简短操作指令，不需要额外仓库上下文。")
            self.assertEqual(pack.entries, [])

    def test_build_context_returns_empty_when_llm_configuration_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.py").write_text("def run_demo():\n    return 'ok'\n", encoding="utf-8")

            hook_input = HookInput(prompt="请解释 sample.py 的实现", cwd=str(root))
            app = build_app(
                root,
                AppConfig(
                    llm_base_url="https://example.com/v1",
                    llm_api_key="test-key",
                ),
            )

            pack = asyncio.run(build_context(hook_input, app))

            self.assertEqual(pack.additional_context, "")
            self.assertEqual(pack.entries, [])
            self.assertIn("配置不完整", pack.summary)


if __name__ == "__main__":
    unittest.main()