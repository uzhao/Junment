from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_LLM_MODEL = "stepfun/step-3.5-flash:free"


@dataclass(slots=True)
class AppConfig:
    """应用配置。"""

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    default_model: str | None = None
    gate_model: str | None = None
    judge_model: str | None = None
    summary_model: str | None = None
    llm_timeout_seconds: int = 30
    llm_max_concurrency: int = 4
    max_candidates: int = 12
    score_threshold: int = 55
    top_k: int = 6
    max_excerpt_lines: int = 60
    planner_max_selected_files: int = 6
    max_file_lines_for_judge: int = 10000

    @classmethod
    def from_env(cls) -> "AppConfig":
        default_model = os.getenv("JUNMENT_LLM_MODEL") or DEFAULT_LLM_MODEL
        return cls(
            llm_base_url=os.getenv("JUNMENT_LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
            llm_api_key=os.getenv("JUNMENT_LLM_API_KEY"),
            default_model=default_model,
            gate_model=os.getenv("JUNMENT_GATE_MODEL") or default_model,
            judge_model=os.getenv("JUNMENT_JUDGE_MODEL") or default_model,
            summary_model=os.getenv("JUNMENT_SUMMARY_MODEL") or default_model,
            llm_timeout_seconds=int(os.getenv("JUNMENT_LLM_TIMEOUT_SECONDS", "30")),
            llm_max_concurrency=int(os.getenv("JUNMENT_LLM_MAX_CONCURRENCY", "4")),
            max_candidates=int(os.getenv("CONTEXT_AGENT_MAX_CANDIDATES", "12")),
            score_threshold=int(os.getenv("CONTEXT_AGENT_SCORE_THRESHOLD", "55")),
            top_k=int(os.getenv("CONTEXT_AGENT_TOP_K", "6")),
            max_excerpt_lines=int(os.getenv("CONTEXT_AGENT_MAX_EXCERPT_LINES", "60")),
            planner_max_selected_files=int(os.getenv("CONTEXT_AGENT_PLANNER_MAX_SELECTED_FILES", "6")),
            max_file_lines_for_judge=int(os.getenv("CONTEXT_AGENT_MAX_FILE_LINES_FOR_JUDGE", "10000")),
        )

    def has_provider_configuration(self) -> bool:
        """是否已配置可调用 provider 的必要信息。"""

        return bool(self.llm_base_url and self.llm_api_key)

    def has_explicit_model_triplet(self) -> bool:
        """是否已显式配置 gate/judge/summary 三个模型。"""

        return bool(self.gate_model and self.judge_model and self.summary_model)

    def has_complete_model_configuration(self) -> bool:
        """是否具备完整模型配置。"""

        return bool(self.default_model) or self.has_explicit_model_triplet()

    def is_llm_workflow_enabled(self) -> bool:
        """是否允许进入完整的 LLM 上下文构造流程。"""

        return self.has_provider_configuration() and self.has_complete_model_configuration()

    def disabled_reason(self) -> str:
        """返回当前禁用原因。"""

        if not self.has_provider_configuration():
            return "LLM provider 配置不完整，已跳过上下文注入。"
        if not self.has_complete_model_configuration():
            return "LLM model 配置不完整，已跳过上下文注入。"
        return ""