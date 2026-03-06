from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys

from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.logging.transport import AsyncEventBus

from context_agent.adapters.claude_hook import build_hook_output, dump_hook_output, parse_hook_payload
from context_agent.app import build_app
from context_agent.config import AppConfig
from context_agent.debug_log import append_hook_log
from context_agent.logging_config import configure_logging
from context_agent.workflows.build_context import build_context


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


async def async_main(argv: list[str] | None = None) -> int:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="Build context for Claude Code hooks.")
    parser.add_argument("--input", help="JSON 输入文件路径。")
    parser.add_argument("--cwd", help="覆盖工作目录。")
    parser.add_argument("--llm-base-url", help="覆盖 LLM base URL。")
    parser.add_argument("--llm-model", help="覆盖默认 model。")
    parser.add_argument("--gate-model", help="覆盖 gate model。")
    parser.add_argument("--judge-model", help="覆盖 judge model。")
    parser.add_argument("--summary-model", help="覆盖 summary model。")
    args = parser.parse_args(argv)

    configure_logging()
    raw_payload = _read_payload(args.input)
    append_hook_log("cli_input", {"input_path": args.input, "raw_payload": raw_payload})
    hook_input = parse_hook_payload(raw_payload, fallback_cwd=args.cwd)
    append_hook_log(
        "parsed_hook",
        {
            "prompt": hook_input.prompt,
            "cwd": hook_input.cwd,
            "event_name": hook_input.event_name,
            "session_id": hook_input.session_id,
        },
    )
    app = build_app(hook_input.cwd, _build_config(args))
    try:
        try:
            async with app.mcp_app.run():
                pack = await build_context(hook_input, app)
        finally:
            await _shutdown_mcp_runtime()
    except Exception as exc:
        append_hook_log("cli_error", {"error": repr(exc)})
        raise
    output = build_hook_output(pack)
    output_json = dump_hook_output(output)
    append_hook_log(
        "hook_output",
        {
            "task_type": pack.task_type,
            "summary": pack.summary,
            "entries": [
                {
                    "path": entry.path,
                    "score": entry.score,
                    "relation_type": entry.relation_type,
                    "reason": entry.reason,
                }
                for entry in pack.entries
            ],
            "additional_context": pack.additional_context,
            "output_json": output_json,
        },
    )
    sys.stdout.write(output_json)
    sys.stdout.write("\n")
    return 0


def _read_payload(input_path: str | None) -> str:
    if input_path:
        with open(input_path, "r", encoding="utf-8") as file:
            return file.read()
    return sys.stdin.read()


def _build_config(args: argparse.Namespace) -> AppConfig:
    """合并环境变量与命令行覆盖项。"""

    config = AppConfig.from_env()
    if args.llm_base_url:
        config.llm_base_url = args.llm_base_url
    if args.llm_model:
        config.default_model = args.llm_model
        config.gate_model = args.llm_model
        config.judge_model = args.llm_model
        config.summary_model = args.llm_model
    if args.gate_model:
        config.gate_model = args.gate_model
    if args.judge_model:
        config.judge_model = args.judge_model
    if args.summary_model:
        config.summary_model = args.summary_model
    return config


async def _shutdown_mcp_runtime() -> None:
    """显式清理 mcp-agent 遗留的日志后台任务。"""

    with contextlib.redirect_stdout(sys.stderr):
        try:
            await LoggingConfig.shutdown()
        finally:
            AsyncEventBus.reset()
            await _cancel_lingering_queue_get_tasks()


async def _cancel_lingering_queue_get_tasks() -> None:
    """取消 mcp-agent event bus 遗留的 Queue.get 挂起任务。"""

    current = asyncio.current_task()
    lingering_tasks = []
    for task in asyncio.all_tasks():
        if task is current or task.done():
            continue
        coro = task.get_coro()
        if getattr(coro, "__qualname__", "") == "Queue.get":
            lingering_tasks.append(task)

    for task in lingering_tasks:
        task.cancel()

    if lingering_tasks:
        await asyncio.gather(*lingering_tasks, return_exceptions=True)


if __name__ == "__main__":
    raise SystemExit(main())