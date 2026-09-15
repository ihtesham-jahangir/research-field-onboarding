from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "field-onboarding"
    / "scripts"
    / "knowledge_state.py"
)
SPEC = importlib.util.spec_from_file_location("knowledge_state", SCRIPT)
assert SPEC and SPEC.loader
state_runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state_runtime)


class KnowledgeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = state_runtime.initial_state(
            "session-1", "topological photonics", "read-paper", language="zh-CN"
        )

    def add(
        self,
        concept_id: str,
        self_report: str,
        prerequisites: list[str] | None = None,
    ) -> None:
        state_runtime.add_concept(
            self.state,
            concept_id,
            concept_id.replace("-", " "),
            self_report,
            prerequisites or [],
        )

    def test_initial_state_is_valid(self) -> None:
        state_runtime.validate(self.state)
        self.assertEqual("unknown", self.state["field_status"])

    def test_used_anchor_is_covered_but_untested(self) -> None:
        self.add("berry-phase", "used")
        concept = self.state["concepts"]["berry-phase"]
        self.assertEqual("covered", concept["progress"])
        self.assertEqual("untested", concept["evidence"])

    def test_ready_concepts_follow_dependencies(self) -> None:
        self.add("berry-phase", "new")
        self.add("berry-curvature", "new", ["berry-phase"])
        self.assertEqual(["berry-phase"], state_runtime.ready_concepts(self.state))
        state_runtime.activate(self.state, "berry-phase")
        state_runtime.record_checkpoint(self.state, "berry-phase", "pass", [])
        self.assertEqual(
            ["berry-curvature"], state_runtime.ready_concepts(self.state)
        )

    def test_failed_checkpoint_overrides_used_anchor(self) -> None:
        self.add("berry-phase", "used")
        self.add("berry-curvature", "new", ["berry-phase"])
        self.assertEqual(
            ["berry-curvature"], state_runtime.ready_concepts(self.state)
        )
        state_runtime.record_checkpoint(
            self.state, "berry-phase", "fail", ["confuses two phases"]
        )
        self.assertEqual([], state_runtime.ready_concepts(self.state))
        self.assertEqual("berry-phase", self.state["current_concept"])

    def test_blocked_concept_cannot_be_activated(self) -> None:
        self.add("a", "new")
        self.add("b", "new", ["a"])
        with self.assertRaisesRegex(state_runtime.StateError, "blocked"):
            state_runtime.activate(self.state, "b")

    def test_dependency_cycles_are_rejected(self) -> None:
        self.add("a", "new")
        self.add("b", "new", ["a"])
        before = self.state.copy()
        before["concepts"] = {
            key: value.copy() for key, value in self.state["concepts"].items()
        }
        with self.assertRaisesRegex(state_runtime.StateError, "cycle"):
            state_runtime.add_concept(self.state, "a", "A", "new", ["b"])
        self.assertEqual(before, self.state)

    def test_atomic_round_trip(self) -> None:
        self.add("berry-phase", "learned")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            state_runtime.save(self.state, path)
            self.assertEqual(self.state, state_runtime.load(path))


if __name__ == "__main__":
    unittest.main()
