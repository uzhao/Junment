from __future__ import annotations

import unittest

from context_agent.schemas.score import CandidateScore
from context_agent.services.score_selection import ScoreSelectionService


class ScoreSelectionServiceTestCase(unittest.TestCase):
    def test_select_deduplicates_and_sorts(self) -> None:
        service = ScoreSelectionService(threshold=60, top_k=2)
        scores = [
            CandidateScore(path="a.py", score=61, relation_type="core", reason="x"),
            CandidateScore(path="a.py", score=70, relation_type="core", reason="y"),
            CandidateScore(path="b.py", score=90, relation_type="doc", reason="z"),
            CandidateScore(path="c.py", score=50, relation_type="test", reason="w"),
        ]

        selected = service.select(scores)

        self.assertEqual([item.path for item in selected], ["b.py", "a.py"])
        self.assertEqual(selected[1].score, 70)


if __name__ == "__main__":
    unittest.main()