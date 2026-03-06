from __future__ import annotations

from context_agent.adapters.openai_compatible import OpenAICompatibleClient
from context_agent.schemas.context_pack import ContextPack

_SUMMARY_SYSTEM_PROMPT = """你负责把已经选出的高相关候选压缩成简洁摘要。

只输出 JSON，格式如下：
{"summary": "..."}

要求：
- summary 使用中文简体
- 最多 120 个字
- 优先说明当前问题应重点看哪些文件以及原因
- 不要重复输出大段摘录
"""


class Summarizer:
    """对最终上下文包做摘要压缩。"""

    def __init__(self, model_client: OpenAICompatibleClient | None = None) -> None:
        self.model_client = model_client

    async def finalize(self, prompt: str, pack: ContextPack) -> ContextPack:
        if not pack.entries:
            return pack
        if self.model_client is None or not self.model_client.can_call(self.model_client.summary_model):
            return pack

        user_prompt = self._build_user_prompt(prompt, pack)
        try:
            payload = await self.model_client.complete_json(
                system_prompt=_SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.model_client.summary_model,
                max_tokens=180,
            )
        except Exception:
            return pack

        summary = str(payload.get("summary") or "").strip()
        if not summary:
            return pack
        pack.summary = summary
        pack.additional_context = f"Condensed summary: {summary}\n\n{pack.additional_context}".strip()
        return pack

    def _build_user_prompt(self, prompt: str, pack: ContextPack) -> str:
        entry_lines: list[str] = []
        for entry in pack.entries[:6]:
            excerpt = "\\n".join(entry.excerpt.splitlines()[:6]) if entry.excerpt else "<empty>"
            entry_lines.extend(
                [
                    f"路径：{entry.path}",
                    f"分数：{entry.score}",
                    f"关系：{entry.relation_type}",
                    f"原因：{entry.reason}",
                    f"摘录：{excerpt}",
                    "",
                ]
            )
        joined_entries = "\n".join(entry_lines).strip()
        return f"用户问题：\n{prompt}\n\n已选候选：\n{joined_entries}\n\n请只返回 JSON。"