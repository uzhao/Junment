from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HOOK_LOG_PATH = "/tmp/hooks.log"
_MAX_TEXT_LENGTH = 20000
_WRITE_LOCK = threading.Lock()
_UNSET = object()
_hook_log_path_override: object | str | None = _UNSET


def configure_hook_log_path(log_path: str | None) -> None:
    """设置当前进程内的 hook 日志路径。"""

    global _hook_log_path_override
    _hook_log_path_override = log_path


def reset_hook_log_path() -> None:
    """重置日志路径覆盖，恢复环境变量回退。"""

    global _hook_log_path_override
    _hook_log_path_override = _UNSET


def get_hook_log_path() -> str | None:
    """获取当前启用的 hook 日志路径。"""

    if _hook_log_path_override is not _UNSET:
        return _hook_log_path_override
    return os.environ.get("JUNMENT_HOOKS_LOG_PATH") or None


def append_hook_log(stage: str, payload: Any) -> None:
    """追加写入 hook 调试日志。"""

    log_path_value = get_hook_log_path()
    if not log_path_value:
        return

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "payload": _sanitize(payload),
    }
    try:
        log_path = Path(log_path_value)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            with log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry, ensure_ascii=False))
                file.write("\n")
    except Exception:
        return


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_sanitize(item) for item in value]
    return _truncate_text(repr(value))


def _truncate_text(text: str) -> str:
    if len(text) <= _MAX_TEXT_LENGTH:
        return text
    remaining = len(text) - _MAX_TEXT_LENGTH
    return f"{text[:_MAX_TEXT_LENGTH]}...(truncated {remaining} chars)"