from __future__ import annotations

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.schemas.candidate import FileView
from context_agent.schemas.score import JudgeResult, LineRange
from context_agent.schemas.search_plan import PlannedFile

_JUDGE_SYSTEM_PROMPT = """你负责对单个文件做独立相关性评分并裁出重点片段。

输入包含用户问题和单个完整文件或裁剪文件视图。

只输出 JSON，格式如下：
{"score": 88, "relation_type": "core implementation", "reason": "...", "spans": [{"start_line": 40, "end_line": 68}], "excerpt": "..."}

要求：
- score 为 0 到 100 的整数
- relation_type 只能从以下集合中选择：
  - error origin
  - core implementation
  - interface / entrypoint
  - config / rule
  - test
  - documentation
  - weakly related
- reason 用一句简短中文说明为什么相关或不相关
- spans 为该文件中与问题最相关的行范围列表，每个元素包含 start_line 和 end_line
- excerpt 为最关键的代码片段文本（最多 30 行），直接从文件内容中截取
"""


class Judge:
    """基于完整文件或裁剪视图做独立相关性判断、片段裁剪和打分。"""

    def __init__(self, model_client: OpenAICompatibleClient | None = None) -> None:
        self.model_client = model_client

    async def judge_file(
        self,
        prompt: str,
        planned_file: PlannedFile,
        file_view: FileView,
    ) -> JudgeResult:
        """对单个文件做相关性判断。优先 LLM，不可用时回退启发式。"""

        if self.model_client is None or not self.model_client.can_call(self.model_client.judge_model):
            return self._heuristic_judge(planned_file, file_view)

        user_prompt = self._build_user_prompt(prompt, planned_file, file_view)
        try:
            payload = await self.model_client.complete_json(
                system_prompt=_JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.model_client.judge_model,
                max_tokens=500,
            )
        except Exception:
            return self._heuristic_judge(planned_file, file_view)

        return self._parse_llm_response(payload, planned_file, file_view)

    def _build_user_prompt(
        self,
        prompt: str,
        planned_file: PlannedFile,
        file_view: FileView,
    ) -> str:
        lines = [
            f"用户问题：\n{prompt}\n",
            f"文件路径：{file_view.path}",
            f"总行数：{file_view.total_lines}",
            f"是否裁剪：{'是' if file_view.truncated else '否'}",
            f"选择理由：{planned_file.reason}",
            "",
            "文件内容：",
            file_view.content_with_line_numbers or "<empty>",
            "",
            "请只返回 JSON。",
        ]
        return "\n".join(lines)

    def _parse_llm_response(
        self,
        payload: dict,
        planned_file: PlannedFile,
        file_view: FileView,
    ) -> JudgeResult:
        score = self._coerce_score(payload.get("score"))
        relation_type = self._coerce_relation_type(payload.get("relation_type"))
        reason = str(payload.get("reason") or planned_file.reason)
        spans = self._parse_spans(payload.get("spans"), file_view.total_lines)
        excerpt = str(payload.get("excerpt") or "")
        # 限制 excerpt 最多 30 行
        excerpt_lines = excerpt.splitlines()
        if len(excerpt_lines) > 30:
            excerpt = "\n".join(excerpt_lines[:30])

        return JudgeResult(
            path=file_view.path,
            score=score,
            relation_type=relation_type,
            reason=reason,
            spans=spans,
            excerpt=excerpt,
            source="planner",
        )

    def _heuristic_judge(self, planned_file: PlannedFile, file_view: FileView) -> JudgeResult:
        """启发式评分回退。"""

        path_lower = file_view.path.lower()
        content_lower = file_view.content_with_line_numbers.lower()

        base_score = 40
        hit_count = sum(1 for t in planned_file.match_terms if t.lower() in content_lower)
        base_score += min(hit_count * 10, 30)
        if planned_file.priority <= 2:
            base_score += 15
        elif planned_file.priority <= 4:
            base_score += 8

        base_score = min(base_score, 100)
        relation_type = self._classify_by_path(path_lower)

        return JudgeResult(
            path=file_view.path,
            score=base_score,
            relation_type=relation_type,
            reason=planned_file.reason,
            spans=[],
            excerpt="",
            source="planner",
        )

    def _classify_by_path(self, path_lower: str) -> str:
        if "test" in path_lower:
            return "test"
        if any(t in path_lower for t in ["readme", "docs", "architecture", ".md"]):
            return "documentation"
        if any(t in path_lower for t in ["config", "settings", "toml", "yaml", "yml"]):
            return "config / rule"
        return "core implementation"

    def _coerce_score(self, value: object) -> int:
        try:
            score = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 50
        return max(0, min(score, 100))

    def _coerce_relation_type(self, value: object) -> str:
        allowed = {
            "error origin",
            "core implementation",
            "interface / entrypoint",
            "config / rule",
            "test",
            "documentation",
            "weakly related",
        }
        relation_type = str(value or "").strip()
        return relation_type if relation_type in allowed else "weakly related"

    def _parse_spans(self, raw_spans: object, total_lines: int) -> list[LineRange]:
        if not isinstance(raw_spans, list):
            return []
        spans: list[LineRange] = []
        for item in raw_spans:
            if not isinstance(item, dict):
                continue
            try:
                start = int(item.get("start_line", 0))  # type: ignore[arg-type]
                end = int(item.get("end_line", 0))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            start = max(1, start)
            end = min(total_lines, end) if total_lines > 0 else end
            if start <= end:
                spans.append(LineRange(start_line=start, end_line=end))
        return spans
