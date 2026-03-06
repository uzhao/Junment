from __future__ import annotations

import os
import unittest
from unittest import mock

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.config import AppConfig


class OpenAICompatibleClientTestCase(unittest.TestCase):
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