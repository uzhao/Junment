from __future__ import annotations

from dataclasses import dataclass

from context_agent.adapters.openai_compatible import OpenAICompatibleClient


_GATE_SYSTEM_PROMPT = """你是 Claude Code 前置上下文编排器里的 gate。

你的唯一任务是判断：当前用户问题是否需要额外的仓库上下文，才能更好地回答。

禁止输出解释、前言、代码块或思考过程。

只输出一行 JSON，格式如下：
{"need_context": true, "reason": "..."}

示例 1：
用户问题：commit
输出：{"need_context": false, "reason": "这是简短操作指令，不需要额外仓库上下文。"}

示例 2：
用户问题：错误xx发生在xx文件xx行函数xx
输出：{"need_context": true, "reason": "问题明确依赖代码位置与实现细节，需要补充仓库上下文。"}
"""


@dataclass(slots=True)
class GateDecision:
    need_context: bool
    reason: str = ""


class Gate:
    """判断当前问题是否需要补充上下文。"""

    def __init__(self, model_client: OpenAICompatibleClient | None = None) -> None:
        self.model_client = model_client

    async def decide(self, prompt: str) -> GateDecision:
        if self.model_client is None or not self.model_client.can_call(self.model_client.gate_model):
            return GateDecision(need_context=False, reason="LLM gate 不可用，已跳过上下文注入。")

        user_prompt = f"用户问题：{prompt}\n\n只返回一行 JSON，不要输出任何额外文本。"
        try:
            payload = await self.model_client.complete_json(
                system_prompt=_GATE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.model_client.gate_model,
                max_tokens=160,
            )
        except Exception:
            return GateDecision(need_context=False, reason="LLM gate 调用失败，已跳过上下文注入。")

        need_context = bool(payload.get("need_context", False))
        reason = str(payload.get("reason") or "")
        return GateDecision(need_context=need_context, reason=reason)