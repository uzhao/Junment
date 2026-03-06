from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from context_agent.debug_log import append_hook_log


class DebugLogTestCase(unittest.TestCase):
    def test_append_hook_log_writes_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "hooks.log")
            with mock.patch.dict(os.environ, {"JUNMENT_HOOKS_LOG_PATH": log_path}, clear=False):
                append_hook_log("test_stage", {"message": "hello"})

            with open(log_path, "r", encoding="utf-8") as file:
                entry = json.loads(file.read().strip())

        self.assertEqual(entry["stage"], "test_stage")
        self.assertEqual(entry["payload"]["message"], "hello")


if __name__ == "__main__":
    unittest.main()