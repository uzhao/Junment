from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HookInput:
    """Claude hook 输入。"""

    prompt: str
    cwd: str
    event_name: str = "UserPromptSubmit"
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HookOutput:
    """Claude hook 输出。"""

    additional_context: str
    continue_: bool = True
    suppress_output: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "continue": self.continue_,
            "suppressOutput": self.suppress_output,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": self.additional_context,
            },
        }