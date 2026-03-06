from __future__ import annotations

import asyncio

from context_agent.app import ContextAgentApp
from context_agent.debug_log import append_hook_log
from context_agent.schemas.context_pack import ContextPack
from context_agent.schemas.hook_io import HookInput


async def build_context(hook_input: HookInput, app: ContextAgentApp) -> ContextPack:
    """执行一轮上下文构造流程。"""

    if not app.config.is_llm_workflow_enabled():
        reason = app.config.disabled_reason()
        append_hook_log("workflow_skip", {"reason": reason, "stage": "config"})
        return ContextPack(
            task_type="skip",
            summary=reason,
            entries=[],
            additional_context="",
        )

    gate_decision = await app.gate.decide(hook_input.prompt)
    append_hook_log(
        "workflow_gate",
        {
            "need_context": gate_decision.need_context,
            "reason": gate_decision.reason,
        },
    )
    if not gate_decision.need_context:
        return ContextPack(
            task_type="skip",
            summary=gate_decision.reason,
            entries=[],
            additional_context="",
        )

    plan = app.planner.create_plan(hook_input.prompt)
    append_hook_log(
        "workflow_plan",
        {
            "task_type": plan.task_type,
            "prompt_summary": plan.prompt_summary,
            "search_terms": plan.search_terms,
            "probable_paths": plan.probable_paths,
            "probable_symbols": plan.probable_symbols,
            "include_docs": plan.include_docs,
        },
    )
    candidates = app.discovery_service.discover(plan, hook_input.cwd)
    append_hook_log(
        "workflow_candidates",
        {
            "count": len(candidates),
            "items": [
                {
                    "path": candidate.path,
                    "source": candidate.source,
                    "reason": candidate.reason,
                    "matched_terms": candidate.matched_terms,
                }
                for candidate in candidates
            ],
        },
    )
    scores = await _score_candidates(hook_input, app, candidates)
    append_hook_log(
        "workflow_scores",
        {
            "count": len(scores),
            "items": [
                {
                    "path": score.path,
                    "score": score.score,
                    "relation_type": score.relation_type,
                    "reason": score.reason,
                    "source": score.source,
                    "recommended_spans": score.recommended_spans,
                }
                for score in scores
            ],
        },
    )
    selected = app.selection_service.select(scores)
    append_hook_log(
        "workflow_selected",
        {
            "count": len(selected),
            "items": [
                {
                    "path": score.path,
                    "score": score.score,
                    "relation_type": score.relation_type,
                    "reason": score.reason,
                }
                for score in selected
            ],
        },
    )
    pack = app.context_pack_builder.build(hook_input, plan, selected, candidates)
    final_pack = await app.summarizer.finalize(hook_input.prompt, pack)
    append_hook_log(
        "workflow_final_pack",
        {
            "task_type": final_pack.task_type,
            "summary": final_pack.summary,
            "entries": [
                {
                    "path": entry.path,
                    "score": entry.score,
                    "relation_type": entry.relation_type,
                    "reason": entry.reason,
                }
                for entry in final_pack.entries
            ],
            "additional_context": final_pack.additional_context,
        },
    )
    return final_pack


async def _score_candidates(hook_input: HookInput, app: ContextAgentApp, candidates: list) -> list:
    if not candidates:
        return []

    semaphore = asyncio.Semaphore(max(1, app.config.llm_max_concurrency))

    async def score_one(candidate) -> object:
        async with semaphore:
            return await app.judge.score_candidate_async(hook_input.prompt, candidate)

    return list(await asyncio.gather(*(score_one(candidate) for candidate in candidates)))