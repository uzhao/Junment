from __future__ import annotations

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.schemas.candidate import RepositorySnapshot
from context_agent.schemas.search_plan import PlannedFile, SearchPlan

_PLANNER_SYSTEM_PROMPT = """你是 Claude Code 前置上下文编排器中的 planner。

你的任务是：根据用户问题、仓库文件树和 grep 命中的文件名列表，选出最相关的候选文件。

只输出 JSON，格式如下：
{"task_type": "explain", "prompt_summary": "...", "selected_files": [{"path": "...", "priority": 1, "reason": "...", "match_terms": ["..."]}]}

要求：
- task_type 只能从以下集合中选择：debug, implement, modify, refactor, explain
- prompt_summary 最多 120 个字，用中文简体概括用户问题
- selected_files 最多 6 个
- 只能从给定的文件树中选择文件路径
- 每个文件必须输出 reason（中文简体，简短说明为什么选这个文件）
- 建议输出 match_terms（后续用于超长文件裁剪的关键词列表）
- priority 为 1（最高优先）到 6（最低优先）的整数
- 优先选择与问题直接相关的核心实现文件
- grep 命中的文件名是弱信号辅助，不是硬约束
"""


class Planner:
    """基于 LLM 的文件选择器，从文件树中选出与用户问题最相关的文件。"""

    def __init__(
        self,
        model_client: OpenAICompatibleClient | None = None,
        max_selected_files: int = 6,
    ) -> None:
        self.model_client = model_client
        self.max_selected_files = max_selected_files

    async def create_plan(
        self,
        prompt: str,
        snapshot: RepositorySnapshot,
    ) -> SearchPlan:
        """使用 LLM 生成文件选择计划。"""

        if self.model_client is None or not self.model_client.can_call(self.model_client.default_model):
            raise RuntimeError("LLM planner 不可用，无法生成文件选择计划。")

        user_prompt = self._build_user_prompt(prompt, snapshot)
        payload = await self.model_client.complete_json(
            system_prompt=_PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=self.model_client.default_model,
            max_tokens=600,
        )
        return self._parse_llm_response(payload, prompt, snapshot)

    def _build_user_prompt(self, prompt: str, snapshot: RepositorySnapshot) -> str:
        lines = [f"用户问题：\n{prompt}\n"]
        lines.append(f"文件树：\n{snapshot.file_tree}\n")
        if snapshot.grep_matched_files:
            lines.append(f"grep 命中文件：\n{chr(10).join(snapshot.grep_matched_files)}\n")
        lines.append(f"最多选择 {self.max_selected_files} 个文件。只返回 JSON。")
        return "\n".join(lines)

    def _parse_llm_response(
        self,
        payload: dict,
        prompt: str,
        snapshot: RepositorySnapshot,
    ) -> SearchPlan:
        task_type = self._coerce_task_type(payload.get("task_type", ""))
        prompt_summary = str(payload.get("prompt_summary") or prompt[:120])
        raw_files = payload.get("selected_files") or []
        tree_paths = set(snapshot.file_tree.splitlines())

        selected_files: list[PlannedFile] = []
        for item in raw_files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            if path not in tree_paths:
                continue
            priority = self._coerce_priority(item.get("priority"))
            reason = str(item.get("reason") or "")
            match_terms = item.get("match_terms") or []
            if not isinstance(match_terms, list):
                match_terms = []
            match_terms = [str(t) for t in match_terms if t]
            selected_files.append(PlannedFile(path=path, priority=priority, reason=reason, match_terms=match_terms))

        selected_files.sort(key=lambda f: f.priority)
        selected_files = selected_files[: self.max_selected_files]
        return SearchPlan(task_type=task_type, prompt_summary=prompt_summary, selected_files=selected_files)

    def _coerce_task_type(self, value: object) -> str:
        allowed = {"debug", "implement", "modify", "refactor", "explain"}
        task_type = str(value or "").strip().lower()
        return task_type if task_type in allowed else "explain"

    def _coerce_priority(self, value: object) -> int:
        try:
            p = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 6
        return max(1, min(p, 6))
