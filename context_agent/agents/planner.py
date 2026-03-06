from __future__ import annotations

import re

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.schemas.search_plan import SearchPlan

_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about",
    "then", "good", "these", "those", "我们", "你们", "这个", "那个", "一个",
    "需要", "可以", "一下", "还有", "进行", "以及", "内容", "好的", "完成",
}

_KEYWORD_HINTS = [
    "报错", "错误", "异常", "失败", "架构", "设计", "实现", "修改", "测试", "说明",
    "readme", "docs", "hook", "prompt", "context",
]


class Planner:
    """负责把原始问题转成搜索计划。"""

    def __init__(self, model_client: OpenAICompatibleClient | None = None) -> None:
        self.model_client = model_client

    def create_plan(self, prompt: str) -> SearchPlan:
        """生成轻量搜索计划。"""

        normalized = prompt.strip()
        probable_paths = self._extract_paths(normalized)
        probable_symbols = self._extract_symbols(normalized)
        search_terms = self._extract_terms(normalized)
        include_docs = any(term in normalized.lower() for term in ["readme", "docs", "架构", "设计", "方案"])
        task_type = self._detect_task_type(normalized)
        summary = normalized[:120]
        return SearchPlan(
            task_type=task_type,
            prompt_summary=summary,
            search_terms=search_terms,
            probable_paths=probable_paths,
            probable_symbols=probable_symbols,
            include_docs=include_docs,
        )

    def _detect_task_type(self, prompt: str) -> str:
        lowered = prompt.lower()
        if any(term in lowered for term in ["error", "traceback", "报错", "异常", "失败"]):
            return "debug"
        if any(term in lowered for term in ["实现", "新增", "create", "add", "支持"]):
            return "implement"
        if any(term in lowered for term in ["修改", "调整", "fix", "patch"]):
            return "modify"
        if any(term in lowered for term in ["重构", "refactor"]):
            return "refactor"
        return "explain"

    def _extract_paths(self, prompt: str) -> list[str]:
        matches = re.findall(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+", prompt)
        return list(dict.fromkeys(matches))[:8]

    def _extract_symbols(self, prompt: str) -> list[str]:
        matches = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`|\b([A-Z][A-Za-z0-9_]{2,})\b", prompt)
        symbols: list[str] = []
        for left, right in matches:
            value = left or right
            if value and value not in symbols:
                symbols.append(value)
        snake_case_matches = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b", prompt)
        for value in snake_case_matches:
            if value not in symbols:
                symbols.append(value)
        camel_case_matches = re.findall(r"\b([a-z]+[A-Z][A-Za-z0-9_]*)\b", prompt)
        for value in camel_case_matches:
            if value not in symbols:
                symbols.append(value)
        return symbols[:8]

    def _extract_terms(self, prompt: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9_\-/]{3,}|[\u4e00-\u9fff]{2,}", prompt)
        terms: list[str] = []
        for token in tokens:
            lowered = token.lower()
            if lowered in _STOP_WORDS:
                continue
            if lowered not in terms:
                terms.append(lowered)
        prompt_lower = prompt.lower()
        for hint in _KEYWORD_HINTS:
            if hint in prompt_lower and hint not in terms:
                terms.append(hint)
        return terms[:12]