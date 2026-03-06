from __future__ import annotations

from context_agent.schemas.candidate import CandidateItem
from context_agent.schemas.context_pack import ContextEntry, ContextPack
from context_agent.schemas.hook_io import HookInput
from context_agent.schemas.score import CandidateScore
from context_agent.schemas.search_plan import SearchPlan


class ContextPackBuilder:
    """把高分候选拼成结构化上下文。"""

    def build(
        self,
        hook_input: HookInput,
        plan: SearchPlan,
        scores: list[CandidateScore],
        candidates: list[CandidateItem],
    ) -> ContextPack:
        candidate_map = {item.path: item for item in candidates}
        entries: list[ContextEntry] = []
        for score in scores:
            candidate = candidate_map.get(score.path)
            excerpt = candidate.content if candidate else ""
            entries.append(
                ContextEntry(
                    path=score.path,
                    score=score.score,
                    relation_type=score.relation_type,
                    reason=score.reason,
                    excerpt=excerpt,
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
            if entry.excerpt:
                excerpt = entry.excerpt.splitlines()[:12]
                lines.append("  excerpt:")
                lines.extend([f"    {line}" for line in excerpt])
        if not entries:
            lines.append("- No high-confidence context found.")

        summary = f"Selected {len(entries)} relevant items for task {plan.task_type}."
        return ContextPack(
            task_type=plan.task_type,
            summary=summary,
            entries=entries,
            additional_context="\n".join(lines).strip(),
        )