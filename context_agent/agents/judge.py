from __future__ import annotations

import re

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.schemas.candidate import CandidateItem
from context_agent.schemas.score import CandidateScore
from context_agent.tools.file_reader import FileReader

_JUDGE_SYSTEM_PROMPT = """你负责对单个候选文件做独立相关性评分。

只根据用户问题、候选来源、候选路径、候选摘录判断该候选是否值得注入 Claude Code 上下文。

只输出 JSON，格式如下：
{"score": 0, "relation_type": "core implementation", "reason": "..."}

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
"""


class Judge:
    """负责逐候选独立评分。"""

    def __init__(
        self,
        model_client: OpenAICompatibleClient | None = None,
        reader: FileReader | None = None,
    ) -> None:
        self.model_client = model_client
        self.reader = reader or FileReader()

    def score_candidate(self, prompt: str, candidate: CandidateItem) -> CandidateScore:
        """使用启发式规则给候选打分。"""

        prompt_terms = self._extract_prompt_terms(prompt)
        matched_terms = [term for term in candidate.matched_terms if term.lower() in prompt.lower()]
        path_lower = candidate.path.lower()
        content_lower = candidate.content.lower()
        content_overlap = [term for term in prompt_terms if len(term) >= 3 and term in content_lower]
        base_score = 18 if candidate.source == "doc" else 20
        base_score += min(len(matched_terms) * 12, 36)

        if candidate.source == "explicit_path":
            base_score += 35
        elif candidate.source == "lsp_symbol":
            base_score += 24
        elif candidate.source == "grep" and len(matched_terms) >= 2:
            base_score += 6
        if matched_terms and any(token in path_lower for token in ["readme", "docs", "architecture", "design", "rfc", "plan"]):
            base_score += 8
        if content_overlap:
            base_score += min(len(content_overlap) * 4, 12)
        if candidate.source == "doc" and not matched_terms:
            base_score = min(base_score, 24)

        base_score = min(base_score, 100)
        relation_type = self._classify_relation(candidate)
        if relation_type == "test" and not self._prompt_requests_tests(prompt.lower()):
            base_score = max(base_score - 20, 0)
        spans = ["1-40"] if candidate.content else []
        reason_terms = ", ".join(matched_terms[:4]) if matched_terms else candidate.reason
        reason = f"Matched by {candidate.source}: {reason_terms}".strip()
        return CandidateScore(
            path=candidate.path,
            score=base_score,
            relation_type=relation_type,
            reason=reason,
            recommended_spans=spans,
            source=candidate.source,
        )

    async def score_candidate_async(self, prompt: str, candidate: CandidateItem) -> CandidateScore:
        """优先使用 LLM 重排；不可用时回退到启发式评分。"""

        if self.model_client is None or not self.model_client.can_call(self.model_client.judge_model):
            return self.score_candidate(prompt, candidate)

        heuristic_score = self.score_candidate(prompt, candidate)
        user_prompt = self._build_user_prompt(prompt, candidate, heuristic_score)
        try:
            payload = await self.model_client.complete_json(
                system_prompt=_JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.model_client.judge_model,
                max_tokens=220,
            )
        except Exception:
            return heuristic_score

        score = self._coerce_score(payload.get("score"), heuristic_score.score)
        relation_type = self._coerce_relation_type(payload.get("relation_type"), heuristic_score.relation_type)
        reason = str(payload.get("reason") or heuristic_score.reason)
        return CandidateScore(
            path=candidate.path,
            score=score,
            relation_type=relation_type,
            reason=reason,
            recommended_spans=heuristic_score.recommended_spans,
            source=candidate.source,
        )

    def _classify_relation(self, candidate: CandidateItem) -> str:
        lowered = candidate.path.lower()
        if "test" in lowered:
            return "test"
        if any(token in lowered for token in ["readme", "docs", "architecture", ".md"]):
            return "documentation"
        if any(token in lowered for token in ["config", "settings", "toml", "yaml", "yml"]):
            return "config / rule"
        if candidate.source in {"explicit_path", "lsp_symbol"}:
            return "core implementation"
        return "weakly related"

    def _extract_prompt_terms(self, prompt: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9_./-]{3,}|[\u4e00-\u9fff]{2,}", prompt.lower())
        terms: list[str] = []
        for token in tokens:
            if token not in terms:
                terms.append(token)
        return terms[:16]

    def _prompt_requests_tests(self, lowered_prompt: str) -> bool:
        return any(token in lowered_prompt for token in ["test", "tests", "测试", "单测", "用例"])

    def _build_user_prompt(
        self,
        prompt: str,
        candidate: CandidateItem,
        heuristic_score: CandidateScore,
    ) -> str:
        excerpt = candidate.content.strip()
        if excerpt:
            excerpt = "\n".join(excerpt.splitlines()[:20])
        else:
            excerpt = "<empty>"
        return (
            f"用户问题：\n{prompt}\n\n"
            f"候选路径：{candidate.path}\n"
            f"候选来源：{candidate.source}\n"
            f"来源理由：{candidate.reason}\n"
            f"启发式参考分：{heuristic_score.score}\n"
            f"启发式关系：{heuristic_score.relation_type}\n"
            f"候选摘录：\n{excerpt}\n\n"
            "请只返回 JSON。"
        )

    def _coerce_score(self, value: object, fallback: int) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(0, min(score, 100))

    def _coerce_relation_type(self, value: object, fallback: str) -> str:
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
        return relation_type if relation_type in allowed else fallback