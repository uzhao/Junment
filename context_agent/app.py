from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mcp_agent.app import MCPApp
from mcp_agent.config import (
    LoggerSettings,
    OpenTelemetrySettings,
    Settings,
    UsageTelemetrySettings,
)

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.agents.gate import Gate
from context_agent.agents.judge import Judge
from context_agent.agents.planner import Planner
from context_agent.agents.summarizer import Summarizer
from context_agent.config import AppConfig
from context_agent.services.candidate_discovery import CandidateDiscoveryService
from context_agent.services.context_pack_builder import ContextPackBuilder
from context_agent.services.score_selection import ScoreSelectionService
from context_agent.tools.doc_locator import DocLocator
from context_agent.tools.file_reader import FileReader
from context_agent.tools.grep_search import GrepSearchTool
from context_agent.tools.lsp_client import LSPClient


@dataclass(slots=True)
class ContextAgentApp:
    """上下文增强应用容器。"""

    config: AppConfig
    mcp_app: MCPApp
    gate: Gate
    planner: Planner
    judge: Judge
    summarizer: Summarizer
    discovery_service: CandidateDiscoveryService
    selection_service: ScoreSelectionService
    context_pack_builder: ContextPackBuilder


def build_app(workspace_root: str | Path, config: AppConfig | None = None) -> ContextAgentApp:
    """构建最小可运行应用。"""

    _ = workspace_root
    app_config = config or AppConfig.from_env()
    reader = FileReader(max_excerpt_lines=app_config.max_excerpt_lines)
    docs = DocLocator(reader=reader)
    grep_tool = GrepSearchTool(reader=reader)
    lsp_client = LSPClient()
    model_client = OpenAICompatibleClient.from_config(app_config)
    mcp_app = _build_mcp_app()

    return ContextAgentApp(
        config=app_config,
        mcp_app=mcp_app,
        gate=Gate(model_client=model_client),
        planner=Planner(model_client=model_client),
        judge=Judge(model_client=model_client, reader=reader),
        summarizer=Summarizer(model_client=model_client),
        discovery_service=CandidateDiscoveryService(
            reader=reader,
            grep_tool=grep_tool,
            doc_locator=docs,
            lsp_client=lsp_client,
            max_candidates=app_config.max_candidates,
        ),
        selection_service=ScoreSelectionService(
            threshold=app_config.score_threshold,
            top_k=app_config.top_k,
        ),
        context_pack_builder=ContextPackBuilder(),
    )


def _build_mcp_app() -> MCPApp:
    """构建用于本地 hook 的静默 MCPApp。"""

    settings = Settings(
        name="junment-context-agent",
        logger=LoggerSettings(type="none", transports=["none"], progress_display=False),
        otel=OpenTelemetrySettings(enabled=False, exporters=[]),
        usage_telemetry=UsageTelemetrySettings(enabled=False),
    )
    return MCPApp(
        name="junment-context-agent",
        description="Local context builder for Claude Code hooks.",
        settings=settings,
    )