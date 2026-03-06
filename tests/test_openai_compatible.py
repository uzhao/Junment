from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.config import AppConfig


class OpenAICompatibleClientTestCase(unittest.TestCase):
    def test_complete_json_sync_writes_hook_logs(self) -> None:
        class _FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = exc_type, exc, tb
                return False

            def read(self) -> bytes:
                return b'{"choices": [{"message": {"content": "{\\"score\\": 88}"}}]}'

        client = OpenAICompatibleClient(
            default_model="demo-model",
            base_url="https://example.com/v1",
            api_key="test-key",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "hooks.log")
            with mock.patch.dict(os.environ, {"JUNMENT_HOOKS_LOG_PATH": log_path}, clear=False):
                with mock.patch("context_agent.adapters.openai_compatible.request.urlopen", return_value=_FakeHTTPResponse()):
                    payload = client._complete_json_sync(
                        system_prompt="system prompt",
                        user_prompt="user prompt",
                        model="demo-model",
                        temperature=0.0,
                        max_tokens=200,
                    )

            self.assertEqual(payload["score"], 88)
            with open(log_path, "r", encoding="utf-8") as file:
                lines = [json.loads(line) for line in file if line.strip()]

        self.assertEqual(
            [line["stage"] for line in lines],
            ["llm_request", "llm_response", "llm_parsed_response"],
        )
        self.assertEqual(lines[0]["payload"]["model"], "demo-model")
        self.assertEqual(lines[0]["payload"]["system_prompt"], "system prompt")
        self.assertEqual(lines[0]["payload"]["user_prompt"], "user prompt")
        self.assertIn('\\"score\\": 88', lines[1]["payload"]["response_body"])

    def test_extract_json_payload_from_fenced_block(self) -> None:
        client = OpenAICompatibleClient()

        payload = client._extract_json_payload("```json\n{\"summary\": \"ok\"}\n```")

        self.assertEqual(payload["summary"], "ok")

    def test_extract_message_content_from_content_list(self) -> None:
        client = OpenAICompatibleClient()

        content = client._extract_message_content(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "{\"score\": 88}"},
                            ]
                        }
                    }
                ]
            }
        )

        self.assertEqual(content, '{"score": 88}')

    def test_from_config_does_not_fallback_to_openai_api_key(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "legacy-key"}, clear=True):
            client = OpenAICompatibleClient.from_config(
                AppConfig(
                    llm_base_url="https://example.com/v1",
                    default_model="demo-model",
                )
            )

        self.assertIsNone(client.api_key)


if __name__ == "__main__":
    unittest.main()