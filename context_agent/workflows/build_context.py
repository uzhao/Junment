from __future__ import annotations

import asyncio

from context_agent.app import ContextAgentApp
from context_agent.schemas.context_pack import ContextPack
from context_agent.schemas.hook_io import HookInput


async def build_context(hook_input: HookInput, app: ContextAgentApp) -> ContextPack:
    """执行一轮上下文构造流程。"""

    if not app.config.is_llm_workflow_enabled():
        return ContextPack(
            task_type="skip",
            summary=app.config.disabled_reason(),
            entries=[],
            additional_context="",
        )

    gate_decision = await app.gate.decide(hook_input.prompt)
    if not gate_decision.need_context:
        return ContextPack(
            task_type="skip",
            summary=gate_decision.reason,
            entries=[],
            additional_context="",
        )

    plan = app.planner.create_plan(hook_input.prompt)
    candidates = app.discovery_service.discover(plan, hook_input.cwd)
    scores = await _score_candidates(hook_input, app, candidates)
    selected = app.selection_service.select(scores)
    pack = app.context_pack_builder.build(hook_input, plan, selected, candidates)
    return await app.summarizer.finalize(hook_input.prompt, pack)


async def _score_candidates(hook_input: HookInput, app: ContextAgentApp, candidates: list) -> list:
    if not candidates:
        return []

    semaphore = asyncio.Semaphore(max(1, app.config.llm_max_concurrency))

    async def score_one(candidate) -> object:
        async with semaphore:
            return await app.judge.score_candidate_async(hook_input.prompt, candidate)

    return list(await asyncio.gather(*(score_one(candidate) for candidate in candidates)))