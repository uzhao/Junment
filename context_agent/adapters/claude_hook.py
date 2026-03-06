from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from context_agent.schemas.context_pack import ContextPack
from context_agent.schemas.hook_io import HookInput, HookOutput


def parse_hook_payload(raw_payload: str, fallback_cwd: str | None = None) -> HookInput:
    """解析 Claude hook 输入。"""

    payload = raw_payload.strip()
    if not payload:
        return HookInput(prompt="", cwd=fallback_cwd or str(Path.cwd()))

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return HookInput(prompt=payload, cwd=fallback_cwd or str(Path.cwd()))

    prompt = _pick_prompt(data)
    cwd = data.get("cwd") or data.get("workspace") or fallback_cwd or str(Path.cwd())
    event_name = data.get("hookEventName") or data.get("hook_event_name") or data.get("event") or "UserPromptSubmit"
    session_id = data.get("sessionId") or data.get("session_id")
    metadata = data if isinstance(data, dict) else {"raw": data}
    return HookInput(
        prompt=prompt,
        cwd=str(cwd),
        event_name=str(event_name),
        session_id=session_id,
        metadata=metadata,
    )


def build_hook_output(pack: ContextPack) -> HookOutput:
    """构造 Claude hook 输出。"""

    return HookOutput(additional_context=pack.additional_context)


def dump_hook_output(output: HookOutput) -> str:
    """序列化 hook 输出。"""

    return json.dumps(output.to_dict(), ensure_ascii=False, indent=2)


def _pick_prompt(data: dict[str, Any]) -> str:
    prompt_fields = ["prompt", "userPrompt", "input", "text"]
    for field in prompt_fields:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value

    message = data.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""