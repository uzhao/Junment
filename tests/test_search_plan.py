from __future__ import annotations

import unittest

from context_agent.agents.planner import Planner


class PlannerTestCase(unittest.TestCase):
    def test_create_plan_extracts_path_and_task_type(self) -> None:
        planner = Planner()
        prompt = "请分析 src/demo.py 的报错，并结合架构设计说明原因。"

        plan = planner.create_plan(prompt)

        self.assertEqual(plan.task_type, "debug")
        self.assertIn("src/demo.py", plan.probable_paths)
        self.assertTrue(plan.include_docs)
        self.assertIn("报错", plan.search_terms)

    def test_create_plan_extracts_snake_case_symbol(self) -> None:
        planner = Planner()

        plan = planner.create_plan("请解释 Planner.create_plan 的职责")

        self.assertIn("Planner", plan.probable_symbols)
        self.assertIn("create_plan", plan.probable_symbols)

    def test_create_plan_extracts_camel_case_symbol(self) -> None:
        planner = Planner()

        plan = planner.create_plan("请解释 createPlan 和 ProjectBuilder 的职责")

        self.assertIn("createPlan", plan.probable_symbols)
        self.assertIn("ProjectBuilder", plan.probable_symbols)


if __name__ == "__main__":
    unittest.main()