from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from context_agent.app import build_app
from context_agent.cli import _build_parser, _configure_hook_logging, _shutdown_mcp_runtime
from context_agent.config import AppConfig
from context_agent.debug_log import DEFAULT_HOOK_LOG_PATH, get_hook_log_path, reset_hook_log_path
from context_agent.schemas.hook_io import HookInput
from context_agent.workflows.build_context import build_context


class CLIRuntimeCleanupTestCase(unittest.TestCase):
    def test_shutdown_mcp_runtime_clears_pending_background_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.py").write_text(
                "def run_demo():\n    return 'architecture demo'\n",
                encoding="utf-8",
            )

            hook_input = HookInput(
                prompt="请解释 sample.py 里的 run_demo 职责",
                cwd=str(root),
            )
            app = build_app(
                root,
                AppConfig(
                    llm_base_url="https://example.com/v1",
                    llm_api_key="test-key",
                    default_model="test-model",
                ),
            )

            async def run_case() -> None:
                current = asyncio.current_task()
                async with app.mcp_app.run():
                    await build_context(hook_input, app)

                await _shutdown_mcp_runtime()
                pending = []
                for _ in range(10):
                    await asyncio.sleep(0)
                    pending = [
                        task
                        for task in asyncio.all_tasks()
                        if task is not current and not task.done()
                    ]
                    if not pending:
                        break
                task_names = [getattr(task.get_coro(), "__qualname__", repr(task.get_coro())) for task in pending]
                self.assertEqual(task_names, [])

            asyncio.run(run_case())


class CLILogArgumentTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        reset_hook_log_path()

    def test_log_flag_uses_default_path(self) -> None:
        parser = _build_parser()

        args = parser.parse_args(["--log"])
        _configure_hook_logging(args.log)

        self.assertEqual(get_hook_log_path(), DEFAULT_HOOK_LOG_PATH)

    def test_log_flag_accepts_custom_path(self) -> None:
        parser = _build_parser()

        args = parser.parse_args(["--log", "/tmp/ya_hooks.log"])
        _configure_hook_logging(args.log)

        self.assertEqual(get_hook_log_path(), "/tmp/ya_hooks.log")


if __name__ == "__main__":
    unittest.main()