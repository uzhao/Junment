from __future__ import annotations

import json
import unittest

from context_agent.adapters.claude_hook import parse_hook_payload


class ClaudeHookAdapterTestCase(unittest.TestCase):
    def test_parse_official_user_prompt_submit_payload(self) -> None:
        raw_payload = json.dumps(
            {
                "session_id": "abc123",
                "transcript_path": "/tmp/session.jsonl",
                "cwd": "/workspace/demo",
                "permission_mode": "default",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "请分析 README.md 的用途",
            },
            ensure_ascii=False,
        )

        hook_input = parse_hook_payload(raw_payload)

        self.assertEqual(hook_input.prompt, "请分析 README.md 的用途")
        self.assertEqual(hook_input.cwd, "/workspace/demo")
        self.assertEqual(hook_input.event_name, "UserPromptSubmit")
        self.assertEqual(hook_input.session_id, "abc123")


if __name__ == "__main__":
    unittest.main()