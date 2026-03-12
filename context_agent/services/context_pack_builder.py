from __future__ import annotations

from context_agent.schemas.context_pack import ContextEntry, ContextPack
from context_agent.schemas.hook_io import HookInput
from context_agent.schemas.score import JudgeResult
from context_agent.schemas.search_plan import SearchPlan


class ContextPackBuilder:
    """把 JudgeResult 列表装配成结构化上下文包。"""

    def build(
        self,
        hook_input: HookInput,
        plan: SearchPlan,
        judge_results: list[JudgeResult],
    ) -> ContextPack:
        entries: list[ContextEntry] = []
        for result in judge_results:
            entries.append(
                ContextEntry(
                    path=result.path,
                    score=result.score,
                    relation_type=result.relation_type,
                    reason=result.reason,
                    excerpt=result.excerpt,
                    spans=list(result.spans),
                )
            )

        lines = [
            "Context Agent Summary",
            f"Task type: {plan.task_type}",
            f"Workspace: {hook_input.cwd}",
            f"Prompt summary: {plan.prompt_summary}",
            "",
            "Relevant context:",
        ]
        for entry in entries:
            lines.extend(
                [
                    f"- {entry.path} [{entry.score}] ({entry.relation_type})",
                    f"  reason: {entry.reason}",
                ]
            )
            if entry.spans:
                span_strs = [f"{s.start_line}-{s.end_line}" for s in entry.spans]
                lines.append(f"  spans: {', '.join(span_strs)}")
            if entry.excerpt:
                excerpt_lines = entry.excerpt.splitlines()[:12]
                lines.append("  excerpt:")
                lines.extend([f"    {line}" for line in excerpt_lines])
        if not entries:
            lines.append("- No high-confidence context found.")

        summary = f"Selected {len(entries)} relevant items for task {plan.task_type}."
        return ContextPack(
            task_type=plan.task_type,
            summary=summary,
            entries=entries,
            additional_context="\n".join(lines).strip(),
        )
