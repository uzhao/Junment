from __future__ import annotations

import os
import unittest
from unittest import mock

from context_agent.config import AppConfig, DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL


class AppConfigTestCase(unittest.TestCase):
    def test_from_env_reads_only_junment_variables(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "JUNMENT_LLM_BASE_URL": "https://example.com/v1",
                "JUNMENT_LLM_API_KEY": "new-key",
                "JUNMENT_LLM_MODEL": "new-model",
                "CONTEXT_AGENT_BASE_URL": "https://legacy.example.com/v1",
                "OPENAI_API_KEY": "legacy-key",
                "CONTEXT_AGENT_MODEL": "legacy-model",
            },
            clear=True,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.llm_base_url, "https://example.com/v1")
        self.assertEqual(config.llm_api_key, "new-key")
        self.assertEqual(config.default_model, "new-model")

    def test_from_env_uses_openrouter_defaults_when_only_key_is_provided(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "JUNMENT_LLM_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.llm_base_url, DEFAULT_LLM_BASE_URL)
        self.assertEqual(config.default_model, DEFAULT_LLM_MODEL)
        self.assertEqual(config.gate_model, DEFAULT_LLM_MODEL)
        self.assertEqual(config.judge_model, DEFAULT_LLM_MODEL)
        self.assertEqual(config.summary_model, DEFAULT_LLM_MODEL)
        self.assertTrue(config.is_llm_workflow_enabled())

    def test_from_env_allows_explicit_junment_values_to_override_defaults(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "JUNMENT_LLM_API_KEY": "test-key",
                "JUNMENT_LLM_BASE_URL": "https://example.com/v1",
                "JUNMENT_LLM_MODEL": "custom-model",
            },
            clear=True,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.llm_base_url, "https://example.com/v1")
        self.assertEqual(config.default_model, "custom-model")
        self.assertEqual(config.gate_model, "custom-model")

    def test_llm_workflow_enabled_with_default_model(self) -> None:
        config = AppConfig(
            llm_base_url="https://example.com/v1",
            llm_api_key="test-key",
            default_model="demo-model",
        )

        self.assertTrue(config.is_llm_workflow_enabled())

    def test_llm_workflow_enabled_with_explicit_model_triplet(self) -> None:
        config = AppConfig(
            llm_base_url="https://example.com/v1",
            llm_api_key="test-key",
            gate_model="gate-model",
            judge_model="judge-model",
            summary_model="summary-model",
        )

        self.assertTrue(config.is_llm_workflow_enabled())

    def test_llm_workflow_disabled_with_partial_models_and_no_default(self) -> None:
        config = AppConfig(
            llm_base_url="https://example.com/v1",
            llm_api_key="test-key",
            gate_model="gate-model",
        )

        self.assertFalse(config.is_llm_workflow_enabled())
        self.assertIn("model", config.disabled_reason())


if __name__ == "__main__":
    unittest.main()