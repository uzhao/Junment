from __future__ import annotations

import asyncio
import unittest

from context_agent.agents.gate import Gate


class _FakeModelClient:
    def __init__(self, payload: dict, should_fail: bool = False, can_call_result: bool = True) -> None:
        self.payload = payload
        self.should_fail = should_fail
        self.can_call_result = can_call_result
        self.gate_model = "fake-gate"
        self.calls: list[dict] = []

    def can_call(self, model: str | None) -> bool:
        _ = model
        return self.can_call_result

    async def complete_json(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if self.should_fail:
            raise RuntimeError("boom")
        return self.payload


class GateTestCase(unittest.TestCase):
    def test_decide_uses_model_result(self) -> None:
        gate = Gate(model_client=_FakeModelClient({"need_context": False, "reason": "短指令"}))

        decision = asyncio.run(gate.decide("commit"))

        self.assertFalse(decision.need_context)
        self.assertEqual(decision.reason, "短指令")

    def test_decide_falls_back_to_need_context_on_failure(self) -> None:
        gate = Gate(model_client=_FakeModelClient({}, should_fail=True))

        decision = asyncio.run(gate.decide("请解释 Planner.create_plan 的职责"))

        self.assertFalse(decision.need_context)
        self.assertIn("跳过", decision.reason)

    def test_decide_returns_skip_when_gate_model_is_unavailable(self) -> None:
        gate = Gate(model_client=_FakeModelClient({}, can_call_result=False))

        decision = asyncio.run(gate.decide("请解释 Planner.create_plan 的职责"))

        self.assertFalse(decision.need_context)
        self.assertIn("不可用", decision.reason)

    def test_decide_uses_stricter_json_only_prompt(self) -> None:
        client = _FakeModelClient({"need_context": True, "reason": "需要上下文"})
        gate = Gate(model_client=client)

        decision = asyncio.run(gate.decide("请解释 Planner.create_plan 的职责"))

        self.assertTrue(decision.need_context)
        self.assertEqual(client.calls[0]["max_tokens"], 160)
        self.assertIn("禁止输出解释", client.calls[0]["system_prompt"])
        self.assertIn("只返回一行 JSON", client.calls[0]["user_prompt"])


if __name__ == "__main__":
    unittest.main()