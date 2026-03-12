from __future__ import annotations

import asyncio

from context_agent.app import ContextAgentApp
from context_agent.debug_log import append_hook_log
from context_agent.schemas.candidate import FileView
from context_agent.schemas.context_pack import ContextPack
from context_agent.schemas.hook_io import HookInput
from context_agent.schemas.score import JudgeResult
from context_agent.schemas.search_plan import PlannedFile


async def build_context(hook_input: HookInput, app: ContextAgentApp) -> ContextPack:
    """执行一轮上下文构造流程。

    新流程：gate -> repository snapshot -> planner -> file loader -> judge -> selection -> builder -> summarizer
    """

    if not app.config.is_llm_workflow_enabled():
        reason = app.config.disabled_reason()
        append_hook_log("workflow_skip", {"reason": reason, "stage": "config"})
        return ContextPack(
            task_type="skip",
            summary=reason,
            entries=[],
            additional_context="",
        )

    # 1. Gate
    gate_decision = await app.gate.decide(hook_input.prompt)
    append_hook_log(
        "workflow_gate",
        {
            "need_context": gate_decision.need_context,
            "reason": gate_decision.reason,
            "grep_hints": gate_decision.grep_hints,
        },
    )
    if not gate_decision.need_context:
        return ContextPack(
            task_type="skip",
            summary=gate_decision.reason,
            entries=[],
            additional_context="",
        )

    # 2. Repository Snapshot
    snapshot = app.snapshot_service.collect(hook_input.cwd, gate_decision.grep_hints)
    append_hook_log(
        "workflow_snapshot",
        {
            "file_tree_count": len(snapshot.file_tree.splitlines()),
            "grep_matched_count": len(snapshot.grep_matched_files),
        },
    )

    # 3. Planner
    plan = await app.planner.create_plan(hook_input.prompt, snapshot)
    append_hook_log(
        "workflow_plan",
        {
            "task_type": plan.task_type,
            "prompt_summary": plan.prompt_summary,
            "selected_files": [
                {
                    "path": f.path,
                    "priority": f.priority,
                    "reason": f.reason,
                    "match_terms": f.match_terms,
                }
                for f in plan.selected_files
            ],
        },
    )

    # 4. File Loader
    file_views = app.file_loader_service.load_all(plan.selected_files, hook_input.cwd)
    append_hook_log(
        "workflow_file_views",
        {
            "count": len(file_views),
            "items": [
                {
                    "path": fv.path,
                    "total_lines": fv.total_lines,
                    "truncated": fv.truncated,
                    "retained_ranges": [
                        {"start_line": r.start_line, "end_line": r.end_line}
                        for r in fv.retained_ranges
                    ],
                }
                for fv in file_views
            ],
        },
    )

    # 5. Judge
    judge_results = await _judge_files(hook_input, app, plan.selected_files, file_views)
    append_hook_log(
        "workflow_judge_results",
        {
            "count": len(judge_results),
            "items": [
                {
                    "path": r.path,
                    "score": r.score,
                    "relation_type": r.relation_type,
                    "reason": r.reason,
                    "spans": [
                        {"start_line": s.start_line, "end_line": s.end_line}
                        for s in r.spans
                    ],
                }
                for r in judge_results
            ],
        },
    )

    # 6. Selection
    selected = app.selection_service.select(judge_results)
    append_hook_log(
        "workflow_selected",
        {
            "count": len(selected),
            "items": [
                {
                    "path": r.path,
                    "score": r.score,
                    "relation_type": r.relation_type,
                    "reason": r.reason,
                }
                for r in selected
            ],
        },
    )

    # 7. Context Pack Builder
    pack = app.context_pack_builder.build(hook_input, plan, selected)

    # 8. Summarizer
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


async def _judge_files(
    hook_input: HookInput,
    app: ContextAgentApp,
    planned_files: list[PlannedFile],
    file_views: list[FileView],
) -> list[JudgeResult]:
    """并发评判所有文件。"""

    if not planned_files:
        return []

    semaphore = asyncio.Semaphore(max(1, app.config.llm_max_concurrency))

    async def judge_one(planned_file: PlannedFile, file_view: FileView) -> JudgeResult:
        async with semaphore:
            return await app.judge.judge_file(hook_input.prompt, planned_file, file_view)

    return list(
        await asyncio.gather(
            *(judge_one(pf, fv) for pf, fv in zip(planned_files, file_views))
        )
    )
