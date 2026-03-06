from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib import request

from context_agent.config import AppConfig
from context_agent.debug_log import append_hook_log


@dataclass(slots=True)
class OpenAICompatibleClient:
    """OpenAI 兼容接口客户端。"""

    default_model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    gate_model: str | None = None
    judge_model: str | None = None
    summary_model: str | None = None
    timeout_seconds: int = 30

    @classmethod
    def from_config(cls, config: AppConfig) -> "OpenAICompatibleClient":
        return cls(
            default_model=config.default_model,
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            gate_model=config.gate_model,
            judge_model=config.judge_model,
            summary_model=config.summary_model,
            timeout_seconds=config.llm_timeout_seconds,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def can_call(self, model: str | None) -> bool:
        return self.enabled and bool(model or self.default_model)

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 400,
    ) -> dict[str, Any]:
        resolved_model = model or self.default_model
        if not self.can_call(resolved_model):
            raise RuntimeError("OpenAI-compatible client is not configured.")
        return await asyncio.to_thread(
            self._complete_json_sync,
            system_prompt,
            user_prompt,
            resolved_model,
            temperature,
            max_tokens,
        )

    def _complete_json_sync(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request_url = self._build_chat_completions_url()
        request_data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        http_request = request.Request(request_url, data=request_data, headers=headers, method="POST")
        append_hook_log(
            "llm_request",
            {
                "model": model,
                "request_url": request_url,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        body = ""
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
            append_hook_log("llm_response", {"model": model, "response_body": body})
            response_json = json.loads(body)
            content = self._extract_message_content(response_json)
            parsed = self._extract_json_payload(content)
            append_hook_log(
                "llm_parsed_response",
                {"model": model, "message_content": content, "json_payload": parsed},
            )
            return parsed
        except Exception as exc:
            append_hook_log(
                "llm_error",
                {
                    "model": model,
                    "response_body": body,
                    "error": repr(exc),
                },
            )
            raise

    def _build_chat_completions_url(self) -> str:
        assert self.base_url is not None
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def _extract_message_content(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Missing choices in model response.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("Missing message in model response.")
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
            if texts:
                return "\n".join(texts)
        raise ValueError("Unsupported message content format.")

    def _extract_json_payload(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                stripped = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in model response.")
        parsed = json.loads(stripped[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("Model response JSON is not an object.")
        return parsed